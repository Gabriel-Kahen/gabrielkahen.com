import json
import sqlite3
from uuid import uuid4

import pytest
from plot_queue import Queue
from plot_path import strokes_for,counts,PARK,checked,LIFT_Z,CONTACT_Z
from printer_worker import Printer


def insert(path, strokes=None, version=2):
    identifier=str(uuid4())
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO drawings(submission_id,vector_json) VALUES (?,?)',
                   (identifier,json.dumps({'version':version,'strokes':strokes or [[[0,0],[200,200]]]})))
    return identifier


@pytest.fixture
def queue(tmp_path):
    path=tmp_path/'drawings.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE drawings(submission_id TEXT PRIMARY KEY,vector_json TEXT)')
    return Queue(path)


def test_cutoff_claim_and_restart(queue):
    old=insert(queue.path)
    queue.arm()
    assert queue.claim() is None
    assert queue.receipt_status(old) is None
    new=insert(queue.path)
    assert queue.receipt_status(new)=='queued'
    job=queue.claim()
    assert job['submission_id']==new
    assert queue.claim() is None
    assert queue.receipt_status(new)=='printing'
    queue.arm()  # interrupted job must never restart; existing pending rows excluded too
    assert queue.receipt_status(new)=='interrupted'
    assert queue.claim() is None


def test_fifo_done_and_offline(queue):
    queue.arm()
    a,b=insert(queue.path),insert(queue.path)
    assert queue.claim()['submission_id']==a
    queue.finish(a,'done')
    assert queue.receipt_status(a)=='done'
    assert queue.claim()['submission_id']==b
    assert queue.claim() is None
    c=insert(queue.path)
    queue.heartbeat(False)
    assert queue.receipt_status(c)=='printer_offline'
    assert queue.claim() is None


def job(strokes,version=2):
    return {'submission_id':str(uuid4()),'vector_json':json.dumps({'version':version,'strokes':strokes})}


def test_bounds_mapping_dedup_and_legacy():
    paths=strokes_for(job([[[0,0],[200,0],[200,200],[0,200],[0,0]],[[100,100],[100.001,100]]]))
    assert paths[0]==[(-173,100,-2.6),(-33,100,-2.6),(-33,-40,-2.6),(-173,-40,-2.6),(-173,100,-2.6)]
    assert paths[1]==[(-103,30,-2.6)]
    legacy=strokes_for(job([[[0,0],[215.9,279.4]]],1))[0]
    assert legacy[0][1]==100 and legacy[1][1]==-40
    assert legacy[0][0]>-173 and legacy[1][0]<-33


@pytest.mark.parametrize('stroke',[[[-1,0]],[[201,0]],[[float('nan'),0]],[[True,0]],[[0,0],[200,200]]*6])
def test_reject_before_motion(stroke):
    with pytest.raises(ValueError):
        strokes_for(job([stroke]))


class FakePrinter(Printer):
    def __init__(self):
        self.expected=counts(PARK)
        self.commands=[]
        self.physical=self.expected
        self.restore=[]
    def command(self,line):
        self.commands.append(line)
        if line.startswith('G1 '):
            values={p[0]:float(p[1:]) for p in line.split()[1:]}
            old=self.physical
            new=counts((values['X'],values['Y'],values['Z']))
            # No diagonal descent or pen-down travel between disconnected strokes.
            if old[2]!=new[2]:
                assert old[:2]==new[:2]
            self.physical=new
        return 'ok'
    def position(self):
        return self.physical


def test_continuous_strokes_lifts_and_park():
    printer=FakePrinter()
    paths=strokes_for(job([[[80,80],[90,80],[100,90]],[[110,110]]]))
    assert printer.draw(paths,lambda:False)
    assert printer.physical==counts(PARK)
    assert printer.commands.count('M400')==3  # per stroke + final park, never per segment
    assert 'G4 P100' in printer.commands
    assert not any(c.startswith(('G28','G92','M500')) for c in printer.commands)
    assert printer.commands[-1]=='M211 S1'


def test_cancel_before_first_stroke():
    printer=FakePrinter()
    assert not printer.draw(strokes_for(job([[[0,0]]])),lambda:True)
    assert printer.physical==counts(PARK)
    assert not any(c.startswith('G1') for c in printer.commands)


def test_presentation_area_only_allows_lifted_travel():
    assert checked(PARK,travel=True)==PARK
    for point in (PARK,(-3,130,CONTACT_Z),(-32,100,CONTACT_Z)):
        with pytest.raises(ValueError):
            checked(point)
    printer=FakePrinter()
    with pytest.raises(ValueError):
        printer.move((-3,130,CONTACT_Z),30)
    with pytest.raises(ValueError,match='vertical'):
        printer.move((-88,30,CONTACT_Z),30)
    with pytest.raises(ValueError):
        printer.move((-3,131,LIFT_Z),1200)
    assert not printer.commands


def test_consecutive_drawings_return_to_presentation_position():
    printer=FakePrinter()
    for _ in range(2):
        assert printer.draw(strokes_for(job([[[0,0],[200,200]]])),lambda:False)
        assert printer.physical==counts((-3,130,LIFT_Z))
        assert printer.commands[-4].startswith('G1 X-3.0000 Y130.0000 Z0.0000')


def test_real_api_to_queue_to_mock_printer(tmp_path):
    from app import Settings,create_app
    from fastapi.testclient import TestClient
    path=tmp_path/'api.sqlite3'
    queue=Queue(path)
    with TestClient(create_app(Settings(db_path=str(path)))) as client:
        old={'version':2,'submission_id':str(uuid4()),'strokes':[[[1,1],[2,2]]]}
        assert client.post('/drawings',json=old).status_code==201
        queue.arm()
        assert queue.claim() is None
        new={**old,'submission_id':str(uuid4())}
        assert client.post('/drawings',json=new).json()['status']=='queued'
        assert client.post('/drawings',json=new).status_code==200
        claimed=queue.claim()
        printer=FakePrinter()
        assert printer.draw(strokes_for(claimed),lambda:False)
        queue.finish(new['submission_id'],'done')
        assert client.post('/drawings',json=new).json()['status']=='done'
        assert queue.claim() is None
        assert client.post('/drawings',json=old).json()['status']=='pending_calibration'
        assert queue.claim() is None


def test_failed_preflight_never_moves_or_arms(queue,monkeypatch):
    import printer_worker as worker
    class BadPrinter:
        def __init__(self,*_): self.closed=False; self.cleaned=False
        def prepare(self): raise RuntimeError('Position mismatch')
        def close(self): self.closed=True
        def cleanup(self): self.cleaned=True
    printer=BadPrinter()
    monkeypatch.setattr(worker,'Printer',lambda *_:printer)
    monkeypatch.setattr('sys.argv',['worker','--db',queue.path,'--arm-new-only'])
    monkeypatch.setattr(worker.signal,'signal',lambda *_:None)
    with pytest.raises(RuntimeError,match='Position mismatch'):
        worker.main()
    assert printer.closed and not printer.cleaned
    with sqlite3.connect(queue.path) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='plot_session'").fetchone()


def test_wakeup_before_wait_and_missing_listener(tmp_path):
    from plot_notify import Wakeup,notify
    import time
    path=tmp_path/'queue.sqlite3'
    notify(path)  # Offline worker never blocks submission.
    wake=Wakeup(path)
    try:
        notify(path)  # Notification in claim-to-wait gap must not be lost.
        start=time.monotonic()
        wake.wait(timeout=1)
        assert time.monotonic()-start<0.1
        for _ in range(1000):
            notify(path)  # Saturation coalesces; never blocks API.
        wake.wait(timeout=1)
    finally:
        wake.close()
    assert not (tmp_path/'plotter-wakeup.sock').exists()


def test_notification_after_commit_and_not_on_retry(tmp_path,monkeypatch):
    from app import Settings,create_app
    from fastapi.testclient import TestClient
    import app as module
    path=tmp_path/'commit.sqlite3'
    seen=[]
    def notified(db_path):
        with sqlite3.connect(db_path) as db:
            seen.append(db.execute('SELECT count(*) FROM drawings').fetchone()[0])
    monkeypatch.setattr(module,'notify',notified)
    with TestClient(create_app(Settings(db_path=str(path)))) as client:
        payload={'version':2,'submission_id':str(uuid4()),'strokes':[[[100,100],[101,100]]]}
        assert client.post('/drawings',json=payload).status_code==201
        assert seen==[1]
        assert client.post('/drawings',json=payload).status_code==200
        assert seen==[1]

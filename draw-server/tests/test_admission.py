from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from app import Settings,create_app
from drawing import PrinterConfig,validate_drawing
from plot_queue import Queue
from storage import Store,AdmissionLimited


def payload():
    return {'version':2,'submission_id':str(uuid4()),'strokes':[[[100,100],[101,100]]]}


def test_persistent_limits_expiry_and_idempotent_retry(tmp_path):
    settings=Settings(db_path=str(tmp_path/'quota.sqlite3'),new_drawings_per_minute=2,new_drawings_per_hour=3)
    a,b,c=payload(),payload(),payload()
    with TestClient(create_app(settings)) as client:
        assert client.post('/drawings',json=a).status_code==201
        assert client.post('/drawings',json=b).status_code==201
        denied=client.post('/drawings',json=c)
        assert denied.status_code==429 and 1<=int(denied.headers['retry-after'])<=60
        assert client.post('/drawings',json=a).status_code==200
    with TestClient(create_app(settings)) as restarted:
        assert restarted.post('/drawings',json=c,headers={'X-Forwarded-For':'192.0.2.1'}).status_code==429
        earlier=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat().replace('+00:00','Z')
        with sqlite3.connect(settings.db_path) as db:
            db.execute('UPDATE drawings SET created_at=?',(earlier,))
        assert restarted.post('/drawings',json=c).status_code==201
        denied=restarted.post('/drawings',json=payload())
        assert denied.status_code==429 and 3500<int(denied.headers['retry-after'])<=3600
        assert restarted.post('/drawings',json=c).status_code==200


def test_queue_cap_counts_queued_and_printing_but_not_history(tmp_path):
    settings=Settings(db_path=str(tmp_path/'queue.sqlite3'))
    queue=Queue(settings.db_path)
    with TestClient(create_app(settings)) as client:
        old=payload()
        assert client.post('/drawings',json=old).status_code==201
        queue.arm()  # Old archived submissions do not occupy current job slots.
        accepted=[payload() for _ in range(3)]
        for data in accepted:
            assert client.post('/drawings',json=data).status_code==201
        job=queue.claim()
        queue.heartbeat(False)  # Pausing the printer must not bypass the backlog cap.
        denied=client.post('/drawings',json=payload())
        assert denied.status_code==429 and 'offline' in denied.json()['error']
        assert client.post('/drawings',json=accepted[0]).status_code==200
        queue.finish(job['submission_id'],'done')
        queue.heartbeat()
        assert client.post('/drawings',json=payload()).status_code==201


def test_offline_plotter_rejects_new_drawings_but_keeps_retries(tmp_path):
    settings=Settings(db_path=str(tmp_path/'offline.sqlite3'))
    queue=Queue(settings.db_path)
    with TestClient(create_app(settings)) as client:
        existing=payload()
        assert client.post('/drawings',json=existing).status_code==201
        queue.arm()
        queue.heartbeat(False)
        denied=client.post('/drawings',json=payload())
        assert denied.status_code==429 and denied.headers['retry-after']=='15'
        assert client.post('/drawings',json=existing).status_code==200


def test_concurrent_acceptance_cannot_overfill_queue(tmp_path):
    store=Store(tmp_path/'race.sqlite3',134217728,10000,new_per_minute=100,new_per_hour=100,max_pending=3)
    store.initialize()
    Queue(store.path).arm()
    def save(_):
        identifier,strokes,length,canonical=validate_drawing(payload())
        try:
            return store.save(identifier,strokes,length,canonical,PrinterConfig())[1]
        except AdmissionLimited:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(save,range(8)))==3
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT count(*) FROM drawings').fetchone()[0]==3


def test_rejected_submission_does_not_generate_archive_gcode(tmp_path,monkeypatch):
    import storage
    settings=Settings(db_path=str(tmp_path/'early.sqlite3'),new_drawings_per_minute=1,new_drawings_per_hour=1)
    with TestClient(create_app(settings)) as client:
        original=payload()
        assert client.post('/drawings',json=original).status_code==201
        def unexpected(*_):
            raise AssertionError('No generation for rejected requests or identical retries')
        monkeypatch.setattr(storage,'generate_gcode',unexpected)
        assert client.post('/drawings',json=payload()).status_code==429
        assert client.post('/drawings',json=original).status_code==200

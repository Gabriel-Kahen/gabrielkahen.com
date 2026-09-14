"""Isolated local HTTP→durable queue→validated path benchmark. Never opens serial."""
import argparse
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from uuid import uuid4

from plot_notify import Wakeup
from plot_path import strokes_for
from plot_queue import Queue


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,help='Directory for a disposable benchmark database')
    parser.add_argument('--port',type=int,default=18012)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dispatch-benchmark-',dir=args.root) as directory:
        db_path=str(Path(directory)/'benchmark.sqlite3')
        env={**os.environ,'DRAW_DB_PATH':db_path,'DRAW_NEW_PER_MINUTE':'100',
             'DRAW_NEW_PER_HOUR':'100','DRAW_REQUESTS_PER_MINUTE':'100'}
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(args.port)],
                                cwd=Path(__file__).parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url=f'http://127.0.0.1:{args.port}'
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+'/health',timeout=1): break
                except OSError:
                    if server.poll() is not None: raise RuntimeError('Benchmark server failed')
                    time.sleep(0.05)
            else: raise RuntimeError('Benchmark server not ready')
            random.seed(4)
            for mode,n in [('poll-1s',10),('notification',20)]:
                queue=Queue(db_path)
                queue.arm()
                wake=Wakeup(db_path) if mode=='notification' else None
                stop=threading.Event()
                ready=threading.Event()
                times=[]
                def consume():
                    while not stop.is_set():
                        job=queue.claim()
                        if job:
                            strokes_for(job)
                            times.append(time.perf_counter())
                            queue.finish(job['submission_id'],'done')
                            ready.set()
                        elif wake:
                            wake.wait()
                        else:
                            stop.wait(1)
                thread=threading.Thread(target=consume)
                thread.start()
                samples=[]
                try:
                    for _ in range(n):
                        time.sleep(random.uniform(.05,.8) if not wake else random.uniform(.005,.03))
                        ready.clear()
                        body=json.dumps({'version':2,'submission_id':str(uuid4()),'strokes':[[[80,80],[100,90],[120,80]]]}).encode()
                        request=urllib.request.Request(url+'/drawings',data=body,headers={'Content-Type':'application/json'})
                        begin=time.perf_counter()
                        with urllib.request.urlopen(request,timeout=5) as response:
                            assert response.status==201
                        if not ready.wait(5): raise RuntimeError('Consumer timed out')
                        samples.append((times[-1]-begin)*1000)
                    print(json.dumps({'mode':mode,'samples':n,'median_ms':round(statistics.median(samples),3),
                                      'max_ms':round(max(samples),3),'min_ms':round(min(samples),3)}),flush=True)
                finally:
                    stop.set()
                    thread.join(timeout=2)
                    if thread.is_alive(): raise RuntimeError('Consumer did not stop')
                    if wake: wake.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__=='__main__':
    main()

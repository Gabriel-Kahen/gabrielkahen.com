"""Explicitly armed, single-session website pen plotter. Never resumes after failure."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import re
import signal
import time
from pathlib import Path

from plot_path import CONTACT_Z,LIFT_Z,PARK,STEPS,DRAW_FEED,TRAVEL_FEED,Z_FEED,checked,counts,strokes_for
from plot_queue import Queue
from plot_notify import Wakeup


class Printer:
    def __init__(self, port, log_path):
        import serial
        self.log = logging.getLogger('printer.serial')
        self.log.setLevel(logging.INFO)
        self.handler=RotatingFileHandler(log_path,maxBytes=10*1024*1024,backupCount=2)
        self.log.addHandler(self.handler)
        self.serial = serial.Serial(port=None,baudrate=115200,timeout=0.2,write_timeout=5,exclusive=True)
        self.serial.dtr = self.serial.rts = False
        self.serial.port=port
        self.serial.open()
        self.restore=[]
        self.expected=counts(PARK)
        self.tick=lambda: None
        self.reset=False
        time.sleep(2)
        startup=self.serial.read_all().decode(errors='replace')
        if startup.strip():
            self.close()
            raise RuntimeError('Unexpected serial startup; calibration must be checked')

    def command(self, line):
        self.log.info(json.dumps({'time':time.time(),'send':line}))
        self.serial.write((line+'\n').encode('ascii'))
        deadline=time.monotonic()+240
        reply=[]
        while time.monotonic()<deadline:
            self.tick()
            text=self.serial.readline().decode(errors='replace').strip()
            if not text:
                continue
            self.log.info(json.dumps({'receive':text}))
            if text.startswith(('start','echo:Marlin')):
                self.reset=True
                raise RuntimeError('Printer reset; session calibration lost')
            if text.startswith(('Error','!!','Resend')) or 'Unknown command' in text:
                raise RuntimeError(text)
            reply.append(text)
            if text.startswith('ok'):
                return '\n'.join(reply)
        raise TimeoutError(line)

    def position(self):
        text=self.command('M114')
        match=re.search(r'Count X:(-?\d+) Y:(-?\d+) Z:(-?\d+)',text)
        if not match:
            raise RuntimeError('Missing motor counts')
        motor=tuple(map(int,match.groups()))
        logical=re.search(r'X:([-\d.]+) Y:([-\d.]+) Z:([-\d.]+)',text)
        if not logical or any(abs(float(v)-c/s)>0.011 for v,c,s in zip(logical.groups(),motor,STEPS)):
            raise RuntimeError('Coordinate offset changed; calibration must be checked')
        return motor

    def verify(self):
        if self.position()!=self.expected:
            raise RuntimeError('Position changed outside the worker; disarming')
        if 'TRIGGERED' in self.command('M119'):
            raise RuntimeError('Endstop triggered')

    def prepare(self):
        self.verify()
        settings=self.command('M503')
        step_config=re.search(r'M92 X([\d.]+) Y([\d.]+) Z([\d.]+)',settings)
        if not step_config or tuple(map(float,step_config.groups()))!=STEPS:
            raise RuntimeError('Unexpected steps per mm')
        for code in ('M204','M205'):
            m=re.search(r'(?m)^echo:\s*('+code+r' [^\r\n]+)',settings)
            if not m:
                raise RuntimeError('Missing '+code)
            self.restore.append(m.group(1))
        for line in ('G21','G90','M104 S0','M140 S0','M107','M17','M84 S0','M204 P100 T100','M205 X1 Y1'):
            self.command(line)
        # Existing tested firmware/session has no active bed mesh. Do not home/reset origin.
        self.command('M211 S0')

    def move(self, point, feed):
        target=checked(point,travel=point[2]==LIFT_Z)
        target_counts=counts(target)
        if target_counts[2]!=self.expected[2] and target_counts[:2]!=self.expected[:2]:
            raise ValueError('Z moves must be vertical')
        if target_counts!=self.expected:
            x,y,z=target
            self.command(f'G1 X{x:.4f} Y{y:.4f} Z{z:.4f} F{feed}')
            self.expected=target_counts

    def finish_motion(self):
        self.command('M400')
        self.verify()

    def lift(self):
        x,y,_=(v/s for v,s in zip(self.expected,STEPS))
        self.move((x,y,LIFT_Z),Z_FEED)

    def draw(self, paths, stopping):
        self.verify()
        self.command('M211 S0')
        for path in paths:
            if stopping():
                return False
            self.lift()
            x,y,_=path[0]
            self.move((x,y,LIFT_Z),TRAVEL_FEED)
            self.move((x,y,CONTACT_Z),Z_FEED)
            for target in path[1:]:
                self.move(target,DRAW_FEED)
            if len(path)==1:
                self.command('G4 P100')
            self.lift()
            self.finish_motion()
        self.move(PARK,TRAVEL_FEED)
        self.finish_motion()
        self.command('M211 S1')
        return True

    def cleanup(self):
        self.command('M211 S0')
        self.lift()
        self.finish_motion()
        self.command('G90')
        self.command('M211 S1')
        for line in self.restore:
            self.command(line)

    def close(self):
        self.serial.close()
        self.handler.close()
        self.log.removeHandler(self.handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',required=True)
    parser.add_argument('--port',default='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
    parser.add_argument('--arm-new-only',action='store_true',required=True)
    args=parser.parse_args()
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    queue=Queue(args.db)
    printer=Printer(args.port,Path(args.db).with_name('printer-stream.jsonl'))
    armed=False
    failed=False
    current=None
    wakeup=None
    last_idle_check=0.
    try:
        printer.prepare()
        wakeup=Wakeup(args.db)
        cutoff=queue.arm()
        armed=True
        last_beat=0.
        def heartbeat():
            nonlocal last_beat
            now=time.monotonic()
            if now-last_beat>5:
                queue.heartbeat()
                last_beat=now
        printer.tick=heartbeat
        print(f'ARMED: skipping all existing rows through {cutoff}; Z={CONTACT_Z:.2f}; drawing={DRAW_FEED}mm/min; travel={TRAVEL_FEED}mm/min; area=140x140',flush=True)
        printer.command('M211 S1')
        while not stopping:
            heartbeat()
            current=queue.claim()
            if current:
                paths=strokes_for(current)  # Validate the complete job before moving.
                print('DRAWING',current['submission_id'],flush=True)
                done=printer.draw(paths,lambda: stopping)
                queue.finish(current['submission_id'],'done' if done else 'interrupted')
                print('DONE' if done else 'INTERRUPTED',current['submission_id'],flush=True)
                current=None
            else:
                if time.monotonic()-last_idle_check>5:
                    printer.verify()
                    last_idle_check=time.monotonic()
                wakeup.wait()
    except BaseException as error:
        failed=True
        if current:
            queue.finish(current['submission_id'],'failed',str(error)[:500])
        raise
    finally:
        printer.tick=lambda: None
        try:
            if armed:
                queue.heartbeat(False)
            if armed and not failed:
                printer.cleanup()
            # On transport/position errors do not send recovery moves or reconnect.
        finally:
            if wakeup:
                wakeup.close()
            printer.close()


if __name__=='__main__':
    main()

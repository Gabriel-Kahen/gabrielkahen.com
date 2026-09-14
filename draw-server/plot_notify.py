"""Best-effort instant wakeups; SQLite remains the authoritative durable queue."""
from pathlib import Path
import socket


def socket_path(db_path):
    return str(Path(db_path).expanduser().resolve().with_name('plotter-wakeup.sock'))


def notify(db_path):
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sender:
        sender.setblocking(False)
        try:
            sender.sendto(b'new',socket_path(db_path))
        except OSError:
            pass  # Offline worker/full socket: bounded polling still finds committed rows.


class Wakeup:
    def __init__(self,db_path):
        self.path=Path(socket_path(db_path))
        self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        self.path.unlink(missing_ok=True)  # Caller must already own the exclusive serial lock.
        self.socket.bind(str(self.path))
        self.path.chmod(0o600)

    def wait(self,timeout=0.25):
        self.socket.settimeout(timeout)
        try:
            self.socket.recv(64)
            self.socket.setblocking(False)
            while True:
                self.socket.recv(64)
        except (TimeoutError,BlockingIOError):
            pass

    def close(self):
        self.socket.close()
        self.path.unlink(missing_ok=True)

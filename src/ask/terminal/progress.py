import threading
from itertools import cycle

FRAMES = ("Generating.  ", "Generating.. ", "Generating...")


class Progress:
    def __init__(self, tty_path: str, interval: float = 0.25) -> None:
        self._tty_path = tty_path
        self._interval = interval
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stopped.set()
        self._thread.join()
        try:
            with open(self._tty_path, "ab", buffering=0) as tty:
                tty.write(b"\r\x1b[2K")
        except OSError:
            pass

    def _run(self) -> None:
        try:
            with open(self._tty_path, "ab", buffering=0) as tty:
                for frame in cycle(FRAMES):
                    tty.write(f"\r\x1b[38;5;245m{frame}\x1b[0m".encode())
                    if self._stopped.wait(self._interval):
                        return
        except OSError:
            return

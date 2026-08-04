from __future__ import annotations

import termios


def present(tty_path: str, comment: str, command: str) -> str:
    with open(tty_path, "r+b", buffering=0) as tty:
        tty.write(f"{comment}\n\x1b[38;5;245m> {command}\x1b[39m\n".encode())
        tty.write(b"\x1b[32menter\x1b[39m run  \x1b[33mtab\x1b[39m edit  \x1b[31mesc\x1b[39m cancel")
        attrs = termios.tcgetattr(tty.fileno())

        raw = list(attrs)
        raw[6] = list(attrs[6])
        raw[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)
        raw[6][termios.VMIN] = 1
        raw[6][termios.VTIME] = 0

        termios.tcsetattr(tty.fileno(), termios.TCSANOW, raw)

        try:
            key = tty.read(1)
        finally:
            termios.tcsetattr(tty.fileno(), termios.TCSANOW, attrs)
        tty.write(b"\n")

    return "run\n" + command if key in {b"\n", b"\r"} else "edit\n" + command if key == b"\t" else "cancel"

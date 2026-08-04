import tempfile
import time
import unittest

from ask.terminal.progress import Progress


class ProgressTests(unittest.TestCase):
    def test_progress_renders_and_clears_its_terminal_line(self):
        with tempfile.NamedTemporaryFile() as tty:
            progress = Progress(tty.name, interval=0.001)
            progress.start()
            time.sleep(0.01)
            progress.stop()

            tty.seek(0)
            output = tty.read()

        self.assertIn(b"Generating", output)
        self.assertNotIn(b"ask:", output)
        self.assertTrue(output.endswith(b"\r\x1b[2K"))

    def test_progress_ignores_tty_write_failures(self):
        progress = Progress("/does-not-exist", interval=0.001)

        progress.start()
        time.sleep(0.01)
        progress.stop()

import unittest
from contextlib import redirect_stderr
from io import StringIO

from ask.cli import parser


class CliTests(unittest.TestCase):
    def test_snapshot_is_not_a_cli_command(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            parser().parse_args(["snapshot"])
        self.assertEqual(error.exception.code, 2)

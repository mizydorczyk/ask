import unittest

from ask.cli import intercept_script


class ShellTests(unittest.TestCase):
    def test_zsh_integration_calls_the_installed_executable(self):
        script = intercept_script()

        self.assertIn('command ask "$@"', script)
        self.assertNotIn("uv run", script)
        self.assertNotIn("_ASK_DISPATCHING", script)
        self.assertNotIn("(snapshot)", script)

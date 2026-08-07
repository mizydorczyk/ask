import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "ask.plugin.zsh"


class ShellTests(unittest.TestCase):
    def test_plugin_registers_the_shell_integration_without_running_ask(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "ask"
            invoked = Path(directory) / "invoked"
            executable.write_text(f"#!/bin/sh\ntouch {invoked}\n")
            executable.chmod(0o755)
            environment = os.environ | {"PATH": f"{directory}:{os.environ['PATH']}"}
            result = subprocess.run(
                [
                    "zsh",
                    "-dfc",
                    (
                        f"source {PLUGIN}; "
                        "print -r -- ${+functions[ask]}:${+aliases[?]}:"
                        "${preexec_functions[(Ie)_ask_record_command]}:"
                        "${precmd_functions[(Ie)_ask_dispatch_pending]}"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(result.stdout.strip(), "1:1:1:1")
            self.assertFalse(invoked.exists())

    def test_plugin_uses_the_installed_executable_for_requests(self):
        script = PLUGIN.read_text()

        self.assertIn('command ask "$@"', script)
        self.assertNotIn("uv run", script)
        self.assertNotIn("python", script)
        self.assertNotIn("_ASK_DISPATCHING", script)
        self.assertIn("(snapshot)", script)
        self.assertIn('_ask_with_context "$previous_status" snapshot "$@"', script)

    def test_zle_wraps_accept_line_to_preserve_other_plugins(self):
        script = PLUGIN.read_text()

        self.assertIn("_ask_accept_line()", script)
        self.assertIn("bindkey -M emacs '?' self-insert", script)
        self.assertIn("zle -D _ask_start", script)
        self.assertIn("_ask_dispatch_pending()", script)
        self.assertIn('print -s -- "? $request"', script)
        self.assertIn('_ask_record_command "? $request"', script)
        self.assertIn("add-zsh-hook precmd _ask_dispatch_pending", script)
        self.assertIn("zle .send-break", script)
        self.assertIn("zle -N accept-line _ask_accept_line", script)
        self.assertIn("zle _ask_original_accept_line", script)
        self.assertNotIn("_ask_submit()", script)

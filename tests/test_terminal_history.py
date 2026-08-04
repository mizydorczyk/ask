import unittest

from ask.terminal.transcript import reviewed_execution


class TerminalHistoryTests(unittest.TestCase):
    def test_reviewed_command_becomes_a_shell_execution(self):
        output = 'Prints a greeting.\n> printf "Hello\\n"\nenter run  tab edit  esc cancel\nHello'

        self.assertEqual(
            reviewed_execution(output, 'printf "Hello\\n"'),
            ("Prints a greeting.", 'printf "Hello\\n"', "Hello"),
        )

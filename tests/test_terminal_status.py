import tempfile
import unittest
from pathlib import Path

from config import Config, set_config
from utils.terminal_status import TerminalStatus


class TerminalStatusErrorLoggingTest(unittest.TestCase):
    def test_capture_target_error_writes_traceback_to_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_config(Config(output_dir=tmpdir))
            status = TerminalStatus()

            try:
                raise RuntimeError("boom")
            except RuntimeError as exc:
                status._capture_target_error(exc)

            log_path = Path(tmpdir) / "tui_error.log"
            self.assertEqual(status._target_error_log_path, log_path)
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("RuntimeError: boom", content)
            self.assertIn("Traceback (most recent call last):", content)


if __name__ == "__main__":
    unittest.main()

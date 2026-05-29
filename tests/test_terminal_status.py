import tempfile
import unittest
import sys
import time
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from config import Config, set_config
from utils.terminal_status import AuditRichLog, AuditStatusApp, TerminalStatus, _TuiStream


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


class TerminalStatusWebRuntimeTest(unittest.TestCase):
    def test_run_with_starts_web_ui_and_tees_command_line_output(self):
        status = TerminalStatus()
        fake_server = Mock()
        fake_server.start.return_value = "http://127.0.0.1:8765/"

        stdout = StringIO()
        stderr = StringIO()

        def target():
            print("hello stdout")
            print("hello stderr", file=sys.stderr)

        with patch("utils.terminal_status.RuntimeStatusServer", return_value=fake_server):
            with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                status.run_with(target)

        fake_server.start.assert_called_once_with()
        self.assertIn("[Web UI] 实时状态页面: http://127.0.0.1:8765/", stderr.getvalue())
        self.assertIn("hello stdout", stdout.getvalue())
        self.assertIn("hello stderr", stderr.getvalue())
        logs = "\n".join(item["line"] for item in status.snapshot()["logs"])
        self.assertIn("hello stdout", logs)
        self.assertIn("hello stderr", logs)

    def test_web_runtime_enables_permission_prompt_without_textual_app(self):
        status = TerminalStatus()
        status.web_server = Mock()
        request = {"id": "per_1", "permission": "write", "patterns": ["*.py"]}
        result = {}

        def ask():
            result["reply"] = status.ask_permission(request, session_id="ses_1")

        import threading

        thread = threading.Thread(target=ask)
        thread.start()
        deadline = time.time() + 1
        while status.permission_request is None and time.time() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(status.permission_request)
        status._reply_permission_from_tui("once")
        thread.join(timeout=1)

        self.assertEqual(result["reply"], "once")
        self.assertIsNone(status.permission_request)

    def test_snapshot_contains_status_functions_and_logs(self):
        status = TerminalStatus()
        status.set_runtime("opencode", session_id="ses_123")
        status.set_stage("Audit", function_name="handle_login", audit_type="command_injection")
        status.set_functions([SimpleNamespace(func_name="handle_login", file_path="main.c")])
        status.start_function("handle_login", "main.c")
        status.log("line one", stream="stderr")

        snapshot = status.snapshot()

        self.assertEqual(snapshot["stage"], "Audit")
        self.assertEqual(snapshot["runtime"], "opencode")
        self.assertEqual(snapshot["session_id"], "ses_123")
        self.assertEqual(snapshot["functions"][0]["name"], "handle_login")
        self.assertEqual(snapshot["functions"][0]["status"], "running")
        self.assertEqual(snapshot["logs"][0]["line"], "line one")
        self.assertEqual(snapshot["logs"][0]["stream"], "stderr")

class AuditStatusAppFocusTest(unittest.TestCase):
    def test_toggle_functions_focuses_table_when_open_and_log_when_closed(self):
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.functions_visible = False

        table = Mock()
        log = Mock()

        def query_one(selector, *_args):
            if selector == "#functions":
                return table
            if selector == "#log":
                return log
            raise AssertionError(f"unexpected selector: {selector}")

        app.query_one = query_one

        app.action_toggle_functions()

        self.assertTrue(app.functions_visible)
        self.assertTrue(table.display)
        table.focus.assert_called_once_with()
        log.focus.assert_not_called()

        app.action_toggle_functions()

        self.assertFalse(app.functions_visible)
        self.assertFalse(table.display)
        log.focus.assert_called_once_with()

    def test_confirmation_actions_reply_to_owner(self):
        owner = Mock()
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.owner = owner

        app.action_confirm_yes()
        app.action_confirm_no()

        owner._reply_confirmation_from_tui.assert_any_call(True)
        owner._reply_confirmation_from_tui.assert_any_call(False)


class AuditStatusAppLogFollowTest(unittest.TestCase):
    def test_user_log_scroll_disables_auto_scroll(self):
        app = Mock()
        log = AuditRichLog.__new__(AuditRichLog)

        with patch.object(AuditRichLog, "app", new_callable=PropertyMock, return_value=app):
            log._pause_auto_scroll_for_user_scroll()

        app.pause_log_auto_scroll.assert_called_once_with()

    def test_follow_log_enables_auto_scroll_and_scrolls_to_end(self):
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.owner = SimpleNamespace(
            stage="-",
            function_name="-",
            audit_type="-",
            runtime="-",
            session_id="-",
            tui_exit_hint="运行中按 q 不退出",
        )
        log = Mock()
        log.auto_scroll = False
        status = Mock()

        def query_one(selector, *_args):
            if selector == "#log":
                return log
            if selector == "#status":
                return status
            raise AssertionError(f"unexpected selector: {selector}")

        app.query_one = query_one

        app.action_follow_log()

        self.assertTrue(log.auto_scroll)
        log.scroll_end.assert_called_once_with(animate=False)
        log.focus.assert_called_once_with()


class TerminalStatusConfirmationTest(unittest.TestCase):
    def test_confirmation_reply_sets_waiting_event(self):
        status = TerminalStatus()
        status.confirmation_prompt = "continue?"
        status._confirmation_reply = False
        status._confirmation_event.clear()

        status._reply_confirmation_from_tui(True)

        self.assertTrue(status._confirmation_reply)
        self.assertTrue(status._confirmation_event.is_set())

    def test_confirmation_panel_has_priority_over_permission_panel(self):
        owner = SimpleNamespace(
            confirmation_prompt="继续 prompt JSON fallback?",
            permission_request={"id": "per_test"},
            permission_session_id="ses_test",
        )
        panel = Mock()
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.owner = owner
        app.query_one = Mock(return_value=panel)

        app._refresh_permission()

        self.assertTrue(panel.display)
        panel.update.assert_called_once()
        rendered = panel.update.call_args.args[0]
        self.assertIn("需要确认", rendered)
        self.assertIn("按 y=继续", rendered)


class AuditStatusAppLifecycleTest(unittest.TestCase):
    def test_target_completion_keeps_tui_open_until_user_quits(self):
        owner = Mock()
        owner.log = Mock()
        owner.mark_tui_finished = Mock()
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.owner = owner
        app.target = Mock()
        app.call_from_thread = Mock()

        app._run_target()

        owner.mark_tui_finished.assert_called_once_with(error=False)
        app.call_from_thread.assert_not_called()

    def test_q_exits_only_after_target_finished(self):
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.target_finished = False
        app.notify = Mock()
        app.exit = Mock()

        app.action_noop()

        app.exit.assert_not_called()
        app.notify.assert_called_once()

        app.target_finished = True
        app.action_noop()

        app.exit.assert_called_once_with()

    def test_target_error_logs_traceback_to_tui(self):
        owner = Mock()
        owner._capture_target_error.return_value = Path("/tmp/tui_error.log")
        app = AuditStatusApp.__new__(AuditStatusApp)
        app.owner = owner
        app.target = Mock(side_effect=RuntimeError("boom"))
        app.call_from_thread = Mock()

        app._run_target()

        logged = "\n".join(call.args[0] for call in owner.log.call_args_list)
        self.assertIn("运行失败", logged)
        self.assertIn("RuntimeError: boom", logged)
        self.assertIn("Traceback (most recent call last):", logged)
        owner.mark_tui_finished.assert_called_once_with(error=True)
        app.call_from_thread.assert_not_called()


class TuiStreamTest(unittest.TestCase):
    def test_stderr_stream_writes_styled_lines_to_tui_log(self):
        owner = Mock()
        original = Mock()
        stream = _TuiStream(owner, original, style="red")

        stream.write("stderr line\n")

        owner.log.assert_called_once_with("[red]stderr line[/red]")


if __name__ == "__main__":
    unittest.main()

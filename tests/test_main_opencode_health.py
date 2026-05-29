import unittest
from unittest.mock import Mock, patch

from config import Config
from main import initialize_runtime_output_format


class MainOpenCodeHealthCheckTest(unittest.TestCase):
    def test_opencode_health_check_runs_even_when_mode_is_configured(self):
        config = Config(
            agent_runtime="opencode",
            opencode_structured_output_mode="json_schema",
            opencode_base_url="http://127.0.0.1:4096",
        )
        client = Mock()

        with patch("agents.runtime_clients.opencode.OpenCodeRuntimeClient", return_value=client):
            initialize_runtime_output_format(config)

        client.health_check.assert_called_once_with(config)
        client.probe_structured_output.assert_not_called()

    def test_opencode_health_check_failure_aborts_before_audit_loop(self):
        config = Config(
            agent_runtime="opencode",
            opencode_structured_output_mode="prompt",
            opencode_base_url="http://127.0.0.1:4096",
        )
        client = Mock()
        client.health_check.side_effect = RuntimeError("connection refused")

        with patch("agents.runtime_clients.opencode.OpenCodeRuntimeClient", return_value=client):
            with self.assertRaises(SystemExit) as raised:
                initialize_runtime_output_format(config)

        message = str(raised.exception)
        self.assertIn("serve 不可用", message)
        self.assertIn("未进入函数循环", message)
        client.probe_structured_output.assert_not_called()


if __name__ == "__main__":
    unittest.main()

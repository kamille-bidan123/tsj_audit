import tempfile
import unittest
from pathlib import Path

from config import find_env_file, init_settings


class ConfigFileTest(unittest.TestCase):
    def test_init_settings_loads_explicit_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "custom.env"
            config_path.write_text(
                "agent_runtime=opencode\n"
                "output_dir=custom_output\n"
                "audit_types=[\"command_injection\", \"path_traversal\"]\n",
                encoding="utf-8",
            )

            config = init_settings({"config": str(config_path)})

            self.assertEqual(config.agent_runtime, "opencode")
            self.assertEqual(config.output_dir, "custom_output")
            self.assertEqual(config.audit_types, ["command_injection", "path_traversal"])

    def test_cli_values_override_explicit_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "custom.env"
            config_path.write_text(
                "agent_runtime=opencode\n"
                "output_dir=custom_output\n",
                encoding="utf-8",
            )

            config = init_settings({"config": str(config_path), "output_dir": "cli_output"})

            self.assertEqual(config.agent_runtime, "opencode")
            self.assertEqual(config.output_dir, "cli_output")

    def test_missing_explicit_config_file_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.env"

            with self.assertRaises(FileNotFoundError):
                find_env_file(missing_path)


if __name__ == "__main__":
    unittest.main()

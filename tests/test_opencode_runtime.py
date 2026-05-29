import unittest

from agents.runtime_clients.opencode import OpenCodeRuntimeClient


class OpenCodeRuntimeClientEventStreamTest(unittest.TestCase):
    def test_timed_out_object_error_is_treated_as_event_stream_timeout(self):
        client = OpenCodeRuntimeClient(project_path=".", debug=False)

        self.assertTrue(client._is_event_stream_timeout(OSError("cannot read from timed out object")))
        self.assertFalse(client._is_event_stream_timeout(OSError("connection reset by peer")))


if __name__ == "__main__":
    unittest.main()

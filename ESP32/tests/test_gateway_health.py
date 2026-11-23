import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_gateway import status_failures


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.status = dict(ethernet_link=True, wifi_online=True, clock_ready=True, api_key_configured=True)

    def test_ready(self):
        self.assertEqual(status_failures(self.status), [])

    def test_fault_reasons(self):
        for field, code in [("ethernet_link", 21), ("wifi_online", 22), ("clock_ready", 23), ("api_key_configured", 24)]:
            with self.subTest(field=field):
                failed = dict(self.status, **{field: False})
                self.assertEqual([v[0] for v in status_failures(failed)], [code])

    def test_unknown_is_not_pass(self):
        self.assertEqual([v[0] for v in status_failures({})], [21, 22, 23, 24])


if __name__ == "__main__":
    unittest.main()

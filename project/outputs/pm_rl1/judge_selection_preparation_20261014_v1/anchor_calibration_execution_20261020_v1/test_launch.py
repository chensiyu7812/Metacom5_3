import copy
import unittest
from unittest.mock import patch
import launch as live


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.protocol, _ = live.a.load()
        self.auth = live.s.read(live.HERE / "APPROVED.json")

    def test_scope_is_exact_and_receipt_must_be_real(self):
        live.approve_scope(self.protocol, self.auth)
        with self.assertRaises(ValueError):
            live.a.approve(self.protocol, self.auth)
        for field, value in [("max_calls", 25), ("stage_cap_usd", "2"),
                             ("exact_synthetic_examples_authorized", False),
                             ("old_stops_released", True)]:
            auth = dict(self.auth, **{field: value})
            with self.assertRaises(ValueError):
                live.approve_scope(self.protocol, auth)

    def test_ledger_prefix_and_study_only_append(self):
        old = b'{"old":1}\n'
        live.check_append_only(old, old + b'{"reservation_id":"allowed"}\n', {"allowed"})
        for data in (b'{"old":2}\n', old + b'{"reservation_id":"foreign"}\n'):
            with self.assertRaises(ValueError):
                live.check_append_only(old, data, {"allowed"})

    def test_bad_approval_precedes_credentials_and_network(self):
        auth = copy.deepcopy(self.auth)
        auth["max_calls"] = 25
        original = live.s.read
        def reader(path):
            return auth if str(path).endswith("/APPROVED.json") else original(path)
        with patch.object(live.s, "read", side_effect=reader), \
                patch.object(live, "read_key") as key, \
                patch.object(live, "management_once") as management, \
                patch.object(live, "public_service_check") as public:
            with self.assertRaises(ValueError):
                live.launch()
            key.assert_not_called()
            management.assert_not_called()
            public.assert_not_called()


if __name__ == "__main__":
    unittest.main()

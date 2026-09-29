from __future__ import annotations

import unittest

from ..formal_path_policy import FormalPathPolicy, shell_spec_for_scenario
from ..path_policy import NavigationBlocked


class FormalPathPolicyTests(unittest.TestCase):
    def test_verified_shell_ports_match_paired_runner(self) -> None:
        expected = {
            "public39": (18226, 18326),
            "business47": (18216, 18316),
            "environment35": (18233, 18333),
            "health19": (18237, 18337),
        }
        for key, (official, clean) in expected.items():
            spec = shell_spec_for_scenario(key)
            self.assertEqual(spec.port("official"), official)
            self.assertEqual(spec.port("clean"), clean)

    def test_only_assigned_task_workflow_is_visible(self) -> None:
        policy = FormalPathPolicy.from_base_url(
            "http://127.0.0.1:18233",
            "environment_climate_water_energy",
            "official",
            "env001",
        )
        allowed = (
            "http://127.0.0.1:18233/task/env001",
            "http://127.0.0.1:18233/task/env001/dashboard",
            "http://127.0.0.1:18233/task/env001/form",
            "http://127.0.0.1:18233/task/env001/confirmation",
            "http://127.0.0.1:18233/task/env001/chart",
        )
        for url in allowed:
            self.assertTrue(policy.is_allowed_document_url(url), url)

        forbidden = (
            "http://127.0.0.1:18233/",
            "http://127.0.0.1:18233/review",
            "http://127.0.0.1:18233/review/task/env001",
            "http://127.0.0.1:18233/admin",
            "http://127.0.0.1:18233/task/env001/misleading_chart",
            "http://127.0.0.1:18233/task/env002",
            "http://127.0.0.1:18333/task/env001",
            "https://example.test/task/env001",
        )
        for url in forbidden:
            self.assertFalse(policy.is_allowed_document_url(url), url)
        with self.assertRaises(NavigationBlocked):
            policy.assert_document_url(forbidden[0])

    def test_submit_is_request_only_and_asset_is_task_scoped(self) -> None:
        policy = FormalPathPolicy.from_base_url(
            "http://127.0.0.1:18226",
            "public39",
            "official",
            "pub001",
        )
        submit = "http://127.0.0.1:18226/task/pub001/submit"
        self.assertTrue(policy.is_allowed_request(submit, "document"))
        self.assertFalse(policy.is_allowed_document_url(submit))
        self.assertTrue(
            policy.is_allowed_request(
                "http://127.0.0.1:18226/task/pub001/chart", "image"
            )
        )
        self.assertFalse(
            policy.is_allowed_request(
                "http://127.0.0.1:18226/task/pub002/chart", "image"
            )
        )


if __name__ == "__main__":
    unittest.main()

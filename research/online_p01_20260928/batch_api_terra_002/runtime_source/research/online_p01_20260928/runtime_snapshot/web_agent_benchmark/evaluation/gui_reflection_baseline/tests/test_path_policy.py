from __future__ import annotations

import unittest

from ..path_policy import NavigationBlocked, TravelPathPolicy


class TravelPathPolicyTests(unittest.TestCase):
    def test_misleading_arm_allows_only_its_document_prefix(self) -> None:
        policy = TravelPathPolicy.from_start_url(
            "http://127.0.0.1:8137/travel/", "misleading"
        )
        self.assertTrue(
            policy.is_allowed_document_url("http://127.0.0.1:8137/travel/dashboard")
        )
        self.assertTrue(
            policy.is_allowed_document_url(
                "http://127.0.0.1:8137/travel/confirm/IL/champaign"
            )
        )
        for forbidden in (
            "http://127.0.0.1:8137/",
            "http://127.0.0.1:8137/review",
            "http://127.0.0.1:8137/travel-clean/",
            "https://127.0.0.1:8137/travel/",
            "http://example.test/travel/",
        ):
            self.assertFalse(policy.is_allowed_document_url(forbidden), forbidden)

    def test_clean_prefix_does_not_match_misleading_prefix(self) -> None:
        policy = TravelPathPolicy.from_start_url(
            "http://localhost:8137/travel-clean/", "clean"
        )
        self.assertTrue(
            policy.is_allowed_document_url("http://localhost:8137/travel-clean/state/KS")
        )
        self.assertFalse(
            policy.is_allowed_document_url("http://localhost:8137/travel/state/KS")
        )

    def test_request_policy_allows_chart_asset_but_not_review_document(self) -> None:
        policy = TravelPathPolicy.from_start_url(
            "http://127.0.0.1:8137/travel/", "misleading"
        )
        self.assertTrue(
            policy.is_allowed_request(
                "http://127.0.0.1:8137/assets/travel_safety_map.jpeg", "image"
            )
        )
        self.assertFalse(
            policy.is_allowed_request(
                "http://127.0.0.1:8137/assets/travel_safety_map_clean.png", "image"
            )
        )
        self.assertFalse(
            policy.is_allowed_request(
                "http://127.0.0.1:8137/assets/unrelated.png", "image"
            )
        )
        self.assertFalse(
            policy.is_allowed_request("http://127.0.0.1:8137/review", "document")
        )
        with self.assertRaises(NavigationBlocked):
            policy.assert_document_url("http://127.0.0.1:8137/")


if __name__ == "__main__":
    unittest.main()

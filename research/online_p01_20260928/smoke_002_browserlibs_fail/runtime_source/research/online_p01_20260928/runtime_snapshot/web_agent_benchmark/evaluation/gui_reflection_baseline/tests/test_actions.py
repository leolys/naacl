from __future__ import annotations

import unittest

from ..actions import (
    ActionParseError,
    ParsedAction,
    action_from_server,
    parse_official_action,
    parse_strict_final_action,
    scale_coordinate,
    scale_coordinates,
)
from ..browser_executor import PlaywrightExecutor, UnsupportedWebAction
from ..path_policy import TravelPathPolicy


class ActionParserTests(unittest.TestCase):
    def test_click_parser_scales_normalized_coordinates(self) -> None:
        action = parse_official_action(
            ": inspect\n: click the state\n: CLICK[[250, 750]]", 1280, 960
        )
        self.assertEqual(action.action_type, "CLICK")
        self.assertEqual(action.normalized_coordinates, (250, 750))
        self.assertEqual(action.parameters, (320, 720))

    def test_parser_uses_final_action_token(self) -> None:
        action = parse_official_action(
            "I considered PRESS_BACK.\n: choose the field\n: CLICK[[500, 500]]",
            1000,
            800,
        )
        self.assertEqual(action.action_type, "CLICK")
        self.assertEqual(action.parameters, (500, 400))

    def test_scroll_and_type(self) -> None:
        scroll = parse_official_action("SCROLL[[500, 800, 500, 200]]", 1200, 1000)
        self.assertEqual(scroll.parameters, (600, 800, 600, 200))
        typed = parse_official_action("TYPE[KS]", 1200, 1000)
        self.assertEqual(typed.action_type, "TYPE")
        self.assertEqual(typed.parameters, ("KS",))

    def test_coordinate_boundary_is_in_bounds(self) -> None:
        self.assertEqual(scale_coordinate(0, 1280), 0)
        self.assertEqual(scale_coordinate(999, 1280), 1278)
        self.assertEqual(scale_coordinates((999, 999), 1280, 960), (1278, 959))
        with self.assertRaises(ActionParseError):
            scale_coordinate(1000, 1280)

    def test_invalid_coordinate_and_missing_action_fail(self) -> None:
        with self.assertRaises(ActionParseError):
            parse_official_action("CLICK[[1001, 0]]", 1280, 960)
        with self.assertRaises(ActionParseError):
            parse_official_action("No action", 1280, 960)

    def test_strict_final_action_requires_one_complete_action_field(self) -> None:
        action = parse_strict_final_action(
            "<THOUGHT>: inspect\n<ACTION>: CLICK[[500, 500]]", 1000, 800
        )
        self.assertEqual(action.action_type, "CLICK")
        self.assertEqual(action.parameters, (500, 400))
        for raw in (
            "I should PRESS_BACK.",
            "<ACTION>: I should PRESS_BACK.",
            "<ACTION>: PRESS_BACK CLICK[[500, 500]]",
            "<ACTION>:",
        ):
            with self.subTest(raw=raw), self.assertRaises(ActionParseError):
                parse_strict_final_action(raw, 1000, 800)

    def test_server_pixels_are_validated_and_raw_normalized_is_retained(self) -> None:
        action = action_from_server(
            {"action_type": "CLICK", "parameters": [320, 720]},
            ": CLICK[[250, 750]]",
            1280,
            960,
        )
        self.assertEqual(action.pixel_coordinates, (320, 720))
        self.assertEqual(action.normalized_coordinates, (250, 750))

    def test_server_coordinate_equal_to_dimension_is_rejected(self) -> None:
        with self.assertRaises(ActionParseError):
            action_from_server(
                {"action_type": "CLICK", "parameters": [1280, 10]},
                ": CLICK[[1000, 10]]",
                1280,
                960,
            )

    def test_valid_non_web_action_is_a_policy_failure(self) -> None:
        policy = TravelPathPolicy.from_start_url(
            "http://127.0.0.1:8137/travel/", "misleading"
        )
        executor = PlaywrightExecutor(policy)
        executor._page = object()
        action = ParsedAction("ANSWER", ("done",), "ANSWER[done]")
        with self.assertRaises(UnsupportedWebAction):
            executor.execute(action)


if __name__ == "__main__":
    unittest.main()

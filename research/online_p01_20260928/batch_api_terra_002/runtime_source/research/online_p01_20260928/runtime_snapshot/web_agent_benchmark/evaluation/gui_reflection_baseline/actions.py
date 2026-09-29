"""Parse GUI-Reflection actions without exposing a semantic DOM action space."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


COORDINATE_ACTIONS = {"CLICK", "LONG_PRESS", "SCROLL"}
TEXT_ACTIONS = {"TYPE", "ANSWER", "MEMORIZE", "OPEN_APP"}
NO_PARAMETER_ACTIONS = {
    "PRESS_HOME",
    "PRESS_BACK",
    "PRESS_ENTER",
    "WAIT",
    "TASK_COMPLETE",
    "TASK_IMPOSSIBLE",
}
KNOWN_ACTIONS = COORDINATE_ACTIONS | TEXT_ACTIONS | NO_PARAMETER_ACTIONS
BROWSER_ACTIONS = {
    "CLICK",
    "LONG_PRESS",
    "SCROLL",
    "TYPE",
    "PRESS_BACK",
    "PRESS_ENTER",
    "WAIT",
    "MEMORIZE",
    "TASK_COMPLETE",
    "TASK_IMPOSSIBLE",
}


class ActionParseError(ValueError):
    """The model output does not contain a valid GUI-Reflection action."""


@dataclass(frozen=True)
class ParsedAction:
    action_type: str
    parameters: tuple[Any, ...]
    raw: str
    normalized_coordinates: tuple[int, ...] | None = None

    @property
    def pixel_coordinates(self) -> tuple[int, ...] | None:
        if self.action_type in COORDINATE_ACTIONS:
            return tuple(int(value) for value in self.parameters)
        return None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action_type": self.action_type,
            "parameters": list(self.parameters),
        }
        if self.normalized_coordinates is not None:
            result["normalized_coordinates"] = list(self.normalized_coordinates)
        if self.pixel_coordinates is not None:
            result["pixel_coordinates"] = list(self.pixel_coordinates)
        return result


_POINT_RE = re.compile(
    r"(?P<action>CLICK|LONG_PRESS)\s*\[\[\s*"
    r"(?P<x>\d{1,4})\s*,\s*(?P<y>\d{1,4})\s*\]\]"
)
_SCROLL_RE = re.compile(
    r"SCROLL\s*\[\[\s*(?P<x1>\d{1,4})\s*,\s*(?P<y1>\d{1,4})\s*,\s*"
    r"(?P<x2>\d{1,4})\s*,\s*(?P<y2>\d{1,4})\s*\]\]"
)
_TEXT_RE = re.compile(
    r"(?P<action>TYPE|ANSWER|MEMORIZE|OPEN_APP)\s*\[(?P<text>.*?)\]",
    re.DOTALL,
)
_NO_PARAMETER_RE = re.compile(
    r"\b(?P<action>PRESS_HOME|PRESS_BACK|PRESS_ENTER|WAIT|TASK_COMPLETE|TASK_IMPOSSIBLE)\b"
)


def scale_coordinate(value: int, size: int) -> int:
    """Scale an official 0..1000 coordinate into a valid 0-indexed pixel."""

    if size <= 0:
        raise ValueError("viewport dimensions must be positive")
    if not 0 <= value < 1000:
        raise ActionParseError(f"normalized coordinate {value} is outside 0..999")
    return int(value / 1000 * size)


def scale_coordinates(
    values: Iterable[int], viewport_width: int, viewport_height: int
) -> tuple[int, ...]:
    numbers = tuple(values)
    if len(numbers) not in (2, 4):
        raise ValueError("coordinate actions require two or four values")
    scaled: list[int] = []
    for index, value in enumerate(numbers):
        size = viewport_width if index % 2 == 0 else viewport_height
        scaled.append(scale_coordinate(int(value), size))
    return tuple(scaled)


def parse_official_action(
    output: str, viewport_width: int, viewport_height: int
) -> ParsedAction:
    """Parse the final action token in a raw GUI-Reflection model response.

    The long-running official-model service normally returns the official
    parser's pixel action directly. This parser is used for protocol checking
    and gives useful failures if a compatible service returns raw text only.
    """

    candidates: list[tuple[int, str, tuple[Any, ...], tuple[int, ...] | None]] = []
    for match in _POINT_RE.finditer(output):
        normalized = (int(match.group("x")), int(match.group("y")))
        pixels = scale_coordinates(normalized, viewport_width, viewport_height)
        candidates.append((match.start(), match.group("action"), pixels, normalized))
    for match in _SCROLL_RE.finditer(output):
        normalized = tuple(int(match.group(name)) for name in ("x1", "y1", "x2", "y2"))
        pixels = scale_coordinates(normalized, viewport_width, viewport_height)
        candidates.append((match.start(), "SCROLL", pixels, normalized))
    for match in _TEXT_RE.finditer(output):
        candidates.append(
            (match.start(), match.group("action"), (match.group("text"),), None)
        )
    for match in _NO_PARAMETER_RE.finditer(output):
        candidates.append((match.start(), match.group("action"), (), None))
    if not candidates:
        raise ActionParseError("model output contains no recognized GUI-Reflection action")
    _position, action_type, parameters, normalized = max(candidates, key=lambda item: item[0])
    return ParsedAction(action_type, tuple(parameters), output, normalized)


def parse_strict_final_action(
    output: str, viewport_width: int, viewport_height: int
) -> ParsedAction:
    """Parse one action from the final ``<ACTION>:`` field only.

    The official agent is prompted to put its executable action in this field.
    Requiring the field to contain only one complete action prevents prose or a
    second action candidate from silently becoming executable. Callers that
    also have the official parser result should additionally require agreement
    with it, because the upstream parser resolves multi-action text by action
    type order rather than by the final textual occurrence.
    """

    marker = "<ACTION>:"
    if marker not in output:
        raise ActionParseError("model output has no final <ACTION> field")
    final_field = output.rsplit(marker, 1)[1].strip()
    if not final_field:
        raise ActionParseError("model output has an empty final <ACTION> field")

    matches: list[tuple[str, re.Match[str]]] = []
    for name, pattern in (
        ("point", _POINT_RE),
        ("scroll", _SCROLL_RE),
        ("text", _TEXT_RE),
        ("no_parameter", _NO_PARAMETER_RE),
    ):
        match = pattern.fullmatch(final_field)
        if match is not None:
            matches.append((name, match))
    if len(matches) != 1:
        raise ActionParseError(
            "final <ACTION> field must contain exactly one complete recognized action"
        )
    return parse_official_action(final_field, viewport_width, viewport_height)


def action_from_server(
    payload: Mapping[str, Any],
    raw: str,
    viewport_width: int,
    viewport_height: int,
) -> ParsedAction:
    """Validate the official agent's already pixel-scaled parsed action."""

    action_type = str(payload.get("action_type", ""))
    if action_type not in KNOWN_ACTIONS:
        raise ActionParseError(f"unsupported or invalid action type: {action_type!r}")
    parameters_value = payload.get("parameters", [])
    if not isinstance(parameters_value, list):
        raise ActionParseError("action parameters must be a JSON list")
    parameters = tuple(parameters_value)
    expected = 4 if action_type == "SCROLL" else 2 if action_type in {"CLICK", "LONG_PRESS"} else 1 if action_type in TEXT_ACTIONS else 0
    if len(parameters) != expected:
        raise ActionParseError(
            f"{action_type} expected {expected} parameters, received {len(parameters)}"
        )
    if action_type in COORDINATE_ACTIONS:
        try:
            parameters = tuple(int(value) for value in parameters)
        except (TypeError, ValueError) as exc:
            raise ActionParseError("coordinate parameters must be integers") from exc
        for index, value in enumerate(parameters):
            bound = viewport_width if index % 2 == 0 else viewport_height
            if value < 0 or value >= bound:
                raise ActionParseError(
                    f"pixel coordinate {value} is outside the viewport bound {bound}"
                )
    normalized: tuple[int, ...] | None = None
    try:
        raw_parsed = parse_official_action(raw, viewport_width, viewport_height)
    except ActionParseError:
        raw_parsed = None
    if raw_parsed is not None and raw_parsed.action_type == action_type:
        normalized = raw_parsed.normalized_coordinates
    return ParsedAction(action_type, parameters, raw, normalized)

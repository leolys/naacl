"""Network/navigation containment for the paired travel sample."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


class NavigationBlocked(RuntimeError):
    """A browser document tried to leave its assigned paired condition."""


def _normalized_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"expected an absolute HTTP(S) URL, received {url!r}")
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port


def _is_path_below(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


@dataclass(frozen=True)
class TravelPathPolicy:
    origin: tuple[str, str, int | None]
    condition: str
    allowed_prefix: str
    allowed_asset_path: str

    @classmethod
    def from_start_url(cls, start_url: str, condition: str) -> "TravelPathPolicy":
        prefixes = {"misleading": "/travel", "clean": "/travel-clean"}
        if condition not in prefixes:
            raise ValueError("condition must be 'misleading' or 'clean'")
        assets = {
            "misleading": "/assets/travel_safety_map.jpeg",
            "clean": "/assets/travel_safety_map_clean.png",
        }
        policy = cls(
            _normalized_origin(start_url),
            condition,
            prefixes[condition],
            assets[condition],
        )
        policy.assert_document_url(start_url)
        return policy

    def is_allowed_document_url(self, url: str) -> bool:
        try:
            if _normalized_origin(url) != self.origin:
                return False
        except (TypeError, ValueError):
            return False
        path = urlsplit(url).path or "/"
        return _is_path_below(path, self.allowed_prefix)

    def assert_document_url(self, url: str) -> None:
        if not self.is_allowed_document_url(url):
            raise NavigationBlocked(
                f"document navigation blocked for {self.condition} condition: {url}"
            )

    def is_allowed_request(self, url: str, resource_type: str) -> bool:
        """Allow assigned documents and only same-origin sample subresources."""

        try:
            if _normalized_origin(url) != self.origin:
                return False
        except (TypeError, ValueError):
            return False
        path = urlsplit(url).path or "/"
        if resource_type == "document":
            return _is_path_below(path, self.allowed_prefix)
        # The paired sample is self-contained; its only external page resource
        # is a chart under /assets. Condition pages are also allowed for any
        # future same-prefix styles/scripts, without allowing / or /review.
        return path == self.allowed_asset_path or _is_path_below(path, self.allowed_prefix)

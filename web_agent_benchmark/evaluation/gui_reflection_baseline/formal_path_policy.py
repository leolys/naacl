"""Task-scoped navigation containment for the four formal benchmark shells.

The route and port table below mirrors the existing paired runner and the
actual Flask routes.  It is intentionally task scoped: a browser assigned to
one task cannot inspect another task, a review page, or the paired arm.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .path_policy import NavigationBlocked


REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2_open"

ARMS = ("official", "clean")
ARM_SPLITS = MappingProxyType(
    {"official": "official140", "clean": "clean140"}
)


@dataclass(frozen=True)
class FormalShellSpec:
    """Verified shell configuration for one canonical scenario."""

    key: str
    dataset_scenario: str
    task_filename: str
    task_count: int
    module_name: str
    health_count_field: str
    official_port: int
    clean_port: int
    slug_pattern: str
    sanitize_chips: bool = False

    def tasks_path(
        self, arm: str, dataset_root: Path = DATASET_ROOT
    ) -> Path:
        try:
            split = ARM_SPLITS[arm]
        except KeyError as exc:
            raise ValueError(f"unknown paired arm: {arm!r}") from exc
        return dataset_root / "splits" / split / self.task_filename

    def port(self, arm: str, offset: int = 0) -> int:
        if arm == "official":
            return self.official_port + offset
        if arm == "clean":
            return self.clean_port + offset
        raise ValueError(f"unknown paired arm: {arm!r}")

    def base_url(self, arm: str, offset: int = 0) -> str:
        return f"http://127.0.0.1:{self.port(arm, offset)}"

    def validate_slug(self, slug: str) -> None:
        if re.fullmatch(self.slug_pattern, slug) is None:
            raise ValueError(
                f"slug {slug!r} does not match scenario {self.key!r}"
            )


# Ports and filenames are the values used by evaluation/run_pair_benchmarks.py.
# Module names and health fields are from each scenario's Flask shell.
FORMAL_SHELL_SPECS = (
    FormalShellSpec(
        key="public39",
        dataset_scenario="public_statistics",
        task_filename="public39_tasks.jsonl",
        task_count=39,
        module_name="web_agent_benchmark.public_benchmark.public_benchmark_shell_app",
        health_count_field="public_tasks",
        official_port=18226,
        clean_port=18326,
        slug_pattern=r"pub\d{3}",
    ),
    FormalShellSpec(
        key="business47",
        dataset_scenario="business_operations",
        task_filename="business47_tasks.jsonl",
        task_count=47,
        module_name="web_agent_benchmark.business_shell.business_shell_app",
        health_count_field="business_tasks",
        official_port=18216,
        clean_port=18316,
        slug_pattern=r"b\d{3}",
    ),
    FormalShellSpec(
        key="environment35",
        dataset_scenario="environment_climate_water_energy",
        task_filename="environment35_tasks.jsonl",
        task_count=35,
        module_name="web_agent_benchmark.environment_energy_shell.environment_shell_app",
        health_count_field="environment_tasks",
        official_port=18233,
        clean_port=18333,
        slug_pattern=r"env\d{3}",
        sanitize_chips=True,
    ),
    FormalShellSpec(
        key="health19",
        dataset_scenario="health",
        task_filename="health19_tasks.jsonl",
        task_count=19,
        module_name="web_agent_benchmark.health_shell.health_shell_app",
        health_count_field="health_tasks",
        official_port=18237,
        clean_port=18337,
        slug_pattern=r"health\d{3}",
        sanitize_chips=True,
    ),
)

SHELL_BY_KEY: Mapping[str, FormalShellSpec] = MappingProxyType(
    {spec.key: spec for spec in FORMAL_SHELL_SPECS}
)
SHELL_BY_DATASET_SCENARIO: Mapping[str, FormalShellSpec] = MappingProxyType(
    {spec.dataset_scenario: spec for spec in FORMAL_SHELL_SPECS}
)


def shell_spec_for_scenario(scenario: str) -> FormalShellSpec:
    """Resolve either the canonical dataset scenario or runner scenario key."""

    spec = SHELL_BY_DATASET_SCENARIO.get(scenario) or SHELL_BY_KEY.get(scenario)
    if spec is None:
        raise ValueError(f"unsupported formal benchmark scenario: {scenario!r}")
    return spec


def _normalized_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"expected an absolute HTTP(S) URL, received {url!r}")
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port


@dataclass(frozen=True)
class FormalPathPolicy:
    """Allow only one task's real shell workflow and chart asset."""

    origin: tuple[str, str, int | None]
    scenario_key: str
    arm: str
    task_slug: str
    sanitize_chips: bool

    @classmethod
    def from_base_url(
        cls,
        base_url: str,
        scenario: str,
        arm: str,
        task_slug: str,
    ) -> "FormalPathPolicy":
        spec = shell_spec_for_scenario(scenario)
        if arm not in ARMS:
            raise ValueError(f"unknown paired arm: {arm!r}")
        spec.validate_slug(task_slug)
        parsed = urlsplit(base_url)
        if (parsed.path or "/") != "/" or parsed.query or parsed.fragment:
            raise ValueError("formal shell base_url must contain only an origin")
        return cls(
            origin=_normalized_origin(base_url),
            scenario_key=spec.key,
            arm=arm,
            task_slug=task_slug,
            sanitize_chips=spec.sanitize_chips,
        )

    @property
    def task_prefix(self) -> str:
        return f"/task/{self.task_slug}"

    @property
    def start_path(self) -> str:
        return self.task_prefix

    @property
    def start_url(self) -> str:
        scheme, host, port = self.origin
        authority = host if port is None else f"{host}:{port}"
        return f"{scheme}://{authority}{self.start_path}"

    @property
    def chart_path(self) -> str:
        return f"{self.task_prefix}/chart"

    @property
    def confirmation_path(self) -> str:
        return f"{self.task_prefix}/confirmation"

    @property
    def submit_path(self) -> str:
        return f"{self.task_prefix}/submit"

    def _same_origin_path(self, url: str) -> str | None:
        try:
            if _normalized_origin(url) != self.origin:
                return None
        except (TypeError, ValueError):
            return None
        return urlsplit(url).path or "/"

    def is_allowed_document_url(self, url: str) -> bool:
        path = self._same_origin_path(url)
        if path is None:
            return False
        return path in {
            self.task_prefix,
            f"{self.task_prefix}/dashboard",
            f"{self.task_prefix}/form",
            self.confirmation_path,
            self.chart_path,
        }

    def is_confirmation_url(self, url: str) -> bool:
        return self._same_origin_path(url) == self.confirmation_path

    def assert_document_url(self, url: str) -> None:
        if not self.is_allowed_document_url(url):
            raise NavigationBlocked(
                "formal task navigation blocked for "
                f"{self.arm}/{self.scenario_key}/{self.task_slug}: {url}"
            )

    def is_allowed_request(self, url: str, resource_type: str) -> bool:
        path = self._same_origin_path(url)
        if path is None:
            return False
        if resource_type == "document":
            # /submit is a POST navigation whose immediate Flask redirect lands
            # on /confirmation.  It is allowed as a request but never as a
            # screenshot-visible document URL.
            return self.is_allowed_document_url(url) or path == self.submit_path
        # All four shells are self-contained and inline their styles.  The only
        # page subresource is the chart for the assigned task.
        return path == self.chart_path

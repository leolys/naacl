"""Coordinate-only browser executors for GUI-Reflection actions."""

from __future__ import annotations

from dataclasses import dataclass
import os
import struct
import time
from typing import Any, Protocol

from .actions import BROWSER_ACTIONS, ParsedAction
from .path_policy import NavigationBlocked, TravelPathPolicy


class BrowserExecutionError(RuntimeError):
    """A screenshot-only browser action could not be executed safely."""


class UnsupportedWebAction(BrowserExecutionError):
    """The agent selected a valid GUI-Reflection action with no web meaning."""


@dataclass(frozen=True)
class ScreenshotFrame:
    png: bytes
    width: int
    height: int
    url: str


@dataclass(frozen=True)
class ExecutionResult:
    from_url: str
    to_url: str
    terminal: str | None
    executed_coordinates: tuple[int, ...] | None
    blocked_requests: tuple[str, ...]


class BrowserExecutor(Protocol):
    def start(self, start_url: str) -> None: ...

    def screenshot(self) -> ScreenshotFrame: ...

    def execute(self, action: ParsedAction) -> ExecutionResult: ...

    def reload(self) -> None: ...

    def close(self) -> None: ...


def png_dimensions(png: bytes) -> tuple[int, int]:
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise BrowserExecutionError("browser screenshot is not a valid PNG")
    width, height = struct.unpack(">II", png[16:24])
    if width <= 0 or height <= 0:
        raise BrowserExecutionError("browser screenshot has invalid dimensions")
    return width, height


def _bounded_coordinates(
    coordinates: tuple[int, ...] | None, width: int, height: int
) -> tuple[int, ...] | None:
    if coordinates is None:
        return None
    bounded: list[int] = []
    for index, value in enumerate(coordinates):
        bound = width if index % 2 == 0 else height
        bounded.append(min(bound - 1, max(0, int(value))))
    return tuple(bounded)


def ensure_local_no_proxy() -> None:
    """Keep WebDriver and the offline sample off configured HTTP proxies."""

    required = ("localhost", "127.0.0.1", "::1")
    for name in ("NO_PROXY", "no_proxy"):
        existing = [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]
        lowered = {part.lower() for part in existing}
        existing.extend(part for part in required if part.lower() not in lowered)
        os.environ[name] = ",".join(existing)


class PlaywrightExecutor:
    """Primary backend: fixed viewport, PNG pixels in, coordinates out."""

    def __init__(
        self,
        policy: TravelPathPolicy,
        *,
        viewport_width: int = 1280,
        viewport_height: int = 960,
        headed: bool = False,
        browser_executable: str | None = None,
        action_wait_ms: int = 700,
        long_press_ms: int = 800,
    ) -> None:
        self.policy = policy
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.headed = headed
        self.browser_executable = browser_executable
        self.action_wait_ms = action_wait_ms
        self.long_press_ms = long_press_ms
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._blocked_requests: list[str] = []

    def start(self, start_url: str) -> None:
        ensure_local_no_proxy()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserExecutionError(
                "Playwright is not installed; install playwright and a browser, or use "
                "--browser-backend selenium-firefox"
            ) from exc
        self.policy.assert_document_url(start_url)
        self._playwright = sync_playwright().start()
        launch_args: dict[str, Any] = {"headless": not self.headed}
        if self.browser_executable:
            launch_args["executable_path"] = self.browser_executable
        self._browser = self._playwright.chromium.launch(**launch_args)
        self._context = self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            device_scale_factor=1,
        )

        def route_request(route: Any) -> None:
            request = route.request
            if self.policy.is_allowed_request(request.url, request.resource_type):
                route.continue_()
            else:
                self._blocked_requests.append(request.url)
                route.abort("blockedbyclient")

        self._context.route("**/*", route_request)
        self._page = self._context.new_page()
        self._page.goto(start_url, wait_until="domcontentloaded")
        self.policy.assert_document_url(self._page.url)

    def screenshot(self) -> ScreenshotFrame:
        if self._page is None:
            raise BrowserExecutionError("browser has not been started")
        # This check is deliberately before screenshot capture: a forbidden
        # review/index/paired-condition page never enters the model history.
        self.policy.assert_document_url(self._page.url)
        png = self._page.screenshot(type="png", full_page=False)
        width, height = png_dimensions(png)
        return ScreenshotFrame(png, width, height, self._page.url)

    def execute(self, action: ParsedAction) -> ExecutionResult:
        if self._page is None:
            raise BrowserExecutionError("browser has not been started")
        if action.action_type not in BROWSER_ACTIONS:
            raise UnsupportedWebAction(
                f"{action.action_type} is outside the supported web action subset"
            )
        from_url = self._page.url
        blocked_index = len(self._blocked_requests)
        coordinates = _bounded_coordinates(
            action.pixel_coordinates, self.viewport_width, self.viewport_height
        )
        terminal: str | None = None
        if action.action_type == "CLICK":
            assert coordinates is not None
            self._page.mouse.click(coordinates[0], coordinates[1])
        elif action.action_type == "LONG_PRESS":
            assert coordinates is not None
            self._page.mouse.move(coordinates[0], coordinates[1])
            self._page.mouse.down()
            self._page.wait_for_timeout(self.long_press_ms)
            self._page.mouse.up()
        elif action.action_type == "SCROLL":
            assert coordinates is not None
            x1, y1, x2, y2 = coordinates
            self._page.mouse.move(x1, y1)
            self._page.mouse.wheel(x1 - x2, y1 - y2)
        elif action.action_type == "TYPE":
            self._page.keyboard.insert_text(str(action.parameters[0]))
        elif action.action_type == "PRESS_BACK":
            self._page.go_back(wait_until="domcontentloaded")
        elif action.action_type == "PRESS_ENTER":
            self._page.keyboard.press("Enter")
        elif action.action_type == "WAIT":
            pass
        elif action.action_type == "MEMORIZE":
            # The official agent updated its own memory bank in step().
            pass
        elif action.action_type in {"TASK_COMPLETE", "TASK_IMPOSSIBLE"}:
            terminal = action.action_type
        self._page.wait_for_timeout(self.action_wait_ms)
        to_url = self._page.url
        # Defense in depth if a browser navigation did not pass through route().
        self.policy.assert_document_url(to_url)
        return ExecutionResult(
            from_url,
            to_url,
            terminal,
            coordinates,
            tuple(self._blocked_requests[blocked_index:]),
        )

    def reload(self) -> None:
        """Re-render the current allowlisted document after runner-side setup."""

        if self._page is None:
            raise BrowserExecutionError("browser has not been started")
        self.policy.assert_document_url(self._page.url)
        self._page.reload(wait_until="domcontentloaded")
        self.policy.assert_document_url(self._page.url)
        self._page.wait_for_timeout(self.action_wait_ms)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None


class SeleniumFirefoxExecutor:
    """Fallback for environments where Playwright browser downloads are blocked.

    Selenium cannot abort a Firefox navigation before the network request without
    adding an interception proxy. It therefore enforces the same allowlist after
    every coordinate action and *before* the next screenshot. An escaped page is
    terminated and is never shown to the model.
    """

    def __init__(
        self,
        policy: TravelPathPolicy,
        *,
        viewport_width: int = 1280,
        viewport_height: int = 960,
        headed: bool = False,
        firefox_binary: str | None = None,
        geckodriver: str | None = None,
        firefox_library_path: str | None = None,
        action_wait_ms: int = 700,
        long_press_ms: int = 800,
    ) -> None:
        self.policy = policy
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.headed = headed
        self.firefox_binary = firefox_binary
        self.geckodriver = geckodriver
        self.firefox_library_path = firefox_library_path
        self.action_wait_ms = action_wait_ms
        self.long_press_ms = long_press_ms
        self._driver: Any = None
        self._keys: Any = None
        self._action_chains: Any = None

    def start(self, start_url: str) -> None:
        ensure_local_no_proxy()
        if self.firefox_library_path:
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = (
                self.firefox_library_path
                if not existing
                else self.firefox_library_path + os.pathsep + existing
            )
        try:
            from selenium import webdriver
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.firefox.options import Options
            from selenium.webdriver.firefox.service import Service
        except ImportError as exc:
            raise BrowserExecutionError(
                "Selenium is not installed; add its directory to PYTHONPATH or use Playwright"
            ) from exc
        self.policy.assert_document_url(start_url)
        options = Options()
        if not self.headed:
            options.add_argument("-headless")
        if self.firefox_binary:
            options.binary_location = self.firefox_binary
        options.set_preference("network.proxy.no_proxies_on", "localhost, 127.0.0.1, ::1")
        service = Service(executable_path=self.geckodriver) if self.geckodriver else Service()
        self._driver = webdriver.Firefox(service=service, options=options)
        self._keys = Keys
        self._action_chains = ActionChains
        self._set_fixed_viewport()
        self._driver.get(start_url)
        self.policy.assert_document_url(self._driver.current_url)

    def _set_fixed_viewport(self) -> None:
        # execute_script is used only for window geometry, never for DOM content
        # or element selection. All task actions remain physical coordinates.
        self._driver.set_window_rect(width=self.viewport_width, height=self.viewport_height)
        for _attempt in range(3):
            inner_width, inner_height = self._driver.execute_script(
                "return [window.innerWidth, window.innerHeight]"
            )
            delta_width = self.viewport_width - int(inner_width)
            delta_height = self.viewport_height - int(inner_height)
            if delta_width == 0 and delta_height == 0:
                break
            rect = self._driver.get_window_rect()
            self._driver.set_window_rect(
                width=int(rect["width"]) + delta_width,
                height=int(rect["height"]) + delta_height,
            )

    def _perform_w3c_actions(self, sources: list[dict[str, Any]]) -> None:
        # Raw W3C pointer/wheel actions keep the executor coordinate-only.
        self._driver.execute("actions", {"actions": sources})

    def screenshot(self) -> ScreenshotFrame:
        if self._driver is None:
            raise BrowserExecutionError("browser has not been started")
        self.policy.assert_document_url(self._driver.current_url)
        png = self._driver.get_screenshot_as_png()
        width, height = png_dimensions(png)
        return ScreenshotFrame(png, width, height, self._driver.current_url)

    def execute(self, action: ParsedAction) -> ExecutionResult:
        if self._driver is None:
            raise BrowserExecutionError("browser has not been started")
        if action.action_type not in BROWSER_ACTIONS:
            raise UnsupportedWebAction(
                f"{action.action_type} is outside the supported web action subset"
            )
        from_url = self._driver.current_url
        coordinates = _bounded_coordinates(
            action.pixel_coordinates, self.viewport_width, self.viewport_height
        )
        terminal: str | None = None
        if action.action_type in {"CLICK", "LONG_PRESS"}:
            assert coordinates is not None
            actions: list[dict[str, Any]] = [
                {
                    "type": "pointerMove",
                    "duration": 0,
                    "x": coordinates[0],
                    "y": coordinates[1],
                    "origin": "viewport",
                },
                {"type": "pointerDown", "button": 0},
            ]
            if action.action_type == "LONG_PRESS":
                actions.append({"type": "pause", "duration": self.long_press_ms})
            actions.append({"type": "pointerUp", "button": 0})
            self._perform_w3c_actions(
                [
                    {
                        "type": "pointer",
                        "id": "gui-reflection-mouse",
                        "parameters": {"pointerType": "mouse"},
                        "actions": actions,
                    }
                ]
            )
        elif action.action_type == "SCROLL":
            assert coordinates is not None
            x1, y1, x2, y2 = coordinates
            self._perform_w3c_actions(
                [
                    {
                        "type": "wheel",
                        "id": "gui-reflection-wheel",
                        "actions": [
                            {
                                "type": "scroll",
                                "x": x1,
                                "y": y1,
                                "deltaX": x1 - x2,
                                "deltaY": y1 - y2,
                                "duration": 250,
                                "origin": "viewport",
                            }
                        ],
                    }
                ]
            )
        elif action.action_type == "TYPE":
            self._action_chains(self._driver).send_keys(str(action.parameters[0])).perform()
        elif action.action_type == "PRESS_BACK":
            self._driver.back()
        elif action.action_type == "PRESS_ENTER":
            self._action_chains(self._driver).send_keys(self._keys.ENTER).perform()
        elif action.action_type == "WAIT":
            pass
        elif action.action_type == "MEMORIZE":
            pass
        elif action.action_type in {"TASK_COMPLETE", "TASK_IMPOSSIBLE"}:
            terminal = action.action_type
        time.sleep(self.action_wait_ms / 1000)
        to_url = self._driver.current_url
        # If this raises, the runner logs the escape and exits. It must not call
        # screenshot() again, so /, /review, and the paired arm cannot leak.
        self.policy.assert_document_url(to_url)
        return ExecutionResult(from_url, to_url, terminal, coordinates, ())

    def reload(self) -> None:
        """Re-render the current allowlisted document after runner-side setup."""

        if self._driver is None:
            raise BrowserExecutionError("browser has not been started")
        self.policy.assert_document_url(self._driver.current_url)
        self._driver.refresh()
        time.sleep(self.action_wait_ms / 1000)
        self.policy.assert_document_url(self._driver.current_url)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.quit()
        self._driver = None

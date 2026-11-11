"""Intelligent test runner & Playwright proxy that enables automatic runtime selector self-healing."""

import time
import traceback
from typing import Optional, List, Dict, Any
from pathlib import Path
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from autoheal.core.models import (
    TestCaseResult,
    HealingEvent,
    SelectorMetadata,
)
from autoheal.core.healer import SelfHealingEngine
from autoheal.core.rca import RootCauseAnalyzer


class SmartPage:
    """Wrapper around Playwright's Page object with self-healing interceptors and telemetry."""

    def __init__(
        self,
        page: Page,
        test_id: str,
        artifacts_dir: str = "artifacts",
        healer: Optional[SelfHealingEngine] = None,
        rca_analyzer: Optional[RootCauseAnalyzer] = None
    ):
        self.page = page
        self.test_id = test_id
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.healer = healer or SelfHealingEngine()
        self.rca_analyzer = rca_analyzer or RootCauseAnalyzer()

        # Telemetry collectors
        self.console_logs: List[str] = []
        self.network_calls: List[Dict[str, Any]] = []
        self.healing_events: List[HealingEvent] = []

        self.steps_total = 0
        self.steps_passed = 0
        self.steps_healed = 0
        self.start_time = time.perf_counter()

        self._attach_listeners()

    def _attach_listeners(self):
        """Monitor console messages and network requests for root-cause diagnosis."""
        def handle_console(msg):
            self.console_logs.append(f"[{msg.type.upper()}] {msg.text}")

        def handle_response(response):
            try:
                self.network_calls.append({
                    "url": response.url,
                    "status": response.status,
                    "method": response.request.method,
                })
            except Exception:
                pass

        self.page.on("console", handle_console)
        self.page.on("response", handle_response)

    def goto(self, url: str, **kwargs):
        """Navigate to URL with automatic telemetry tracking."""
        return self.page.goto(url, **kwargs)

    def smart_click(
        self,
        selector: str,
        metadata: Optional[SelectorMetadata] = None,
        step_name: Optional[str] = None,
        timeout_ms: int = 2500
    ):
        """Click an element, automatically healing the selector if the target is moved or changed."""
        self.steps_total += 1
        effective_step = step_name or f"Click '{selector}'"

        try:
            # 1. Try standard click
            self.page.click(selector, timeout=timeout_ms)
            self.steps_passed += 1
            return True
        except (PlaywrightTimeoutError, Exception) as original_err:
            # 2. Trigger self-healing interceptor
            dom_html = self.page.content()
            healed_selector, event = self.healer.heal_selector(
                broken_selector=selector,
                dom_html=dom_html,
                metadata=metadata,
                test_id=self.test_id,
                step_name=effective_step
            )

            if healed_selector:
                try:
                    # 3. Retry with healed selector
                    self.page.click(healed_selector, timeout=timeout_ms)
                    self.steps_healed += 1
                    self.steps_passed += 1
                    if event:
                        self.healing_events.append(event)
                    return True
                except Exception as retry_err:
                    pass

            # 4. If healing failed, diagnose via RCA
            screenshot_path = str(self.artifacts_dir / f"{self.test_id}_failure.png")
            try:
                self.page.screenshot(path=screenshot_path)
            except Exception:
                screenshot_path = None

            rca = self.rca_analyzer.diagnose_failure(
                test_id=self.test_id,
                error=original_err,
                stack_trace=traceback.format_exc(),
                current_url=self.page.url,
                console_logs=self.console_logs,
                network_calls=self.network_calls,
                dom_snapshot=dom_html,
                screenshot_path=screenshot_path
            )
            raise AssertionError(f"Step '{effective_step}' failed. RCA: {rca.root_cause_summary}") from original_err

    def smart_fill(
        self,
        selector: str,
        text: str,
        metadata: Optional[SelectorMetadata] = None,
        step_name: Optional[str] = None,
        timeout_ms: int = 2500
    ):
        """Fill an input field, automatically healing locator if broken."""
        self.steps_total += 1
        effective_step = step_name or f"Fill '{selector}' with text"

        try:
            self.page.fill(selector, text, timeout=timeout_ms)
            self.steps_passed += 1
            return True
        except (PlaywrightTimeoutError, Exception) as original_err:
            dom_html = self.page.content()
            healed_selector, event = self.healer.heal_selector(
                broken_selector=selector,
                dom_html=dom_html,
                metadata=metadata,
                test_id=self.test_id,
                step_name=effective_step
            )

            if healed_selector:
                try:
                    self.page.fill(healed_selector, text, timeout=timeout_ms)
                    self.steps_healed += 1
                    self.steps_passed += 1
                    if event:
                        self.healing_events.append(event)
                    return True
                except Exception:
                    pass

            screenshot_path = str(self.artifacts_dir / f"{self.test_id}_failure.png")
            try:
                self.page.screenshot(path=screenshot_path)
            except Exception:
                screenshot_path = None

            rca = self.rca_analyzer.diagnose_failure(
                test_id=self.test_id,
                error=original_err,
                stack_trace=traceback.format_exc(),
                current_url=self.page.url,
                console_logs=self.console_logs,
                network_calls=self.network_calls,
                dom_snapshot=dom_html,
                screenshot_path=screenshot_path
            )
            raise AssertionError(f"Step '{effective_step}' failed. RCA: {rca.root_cause_summary}") from original_err

    def finish_test(self, test_name: str, status: Optional[str] = None) -> TestCaseResult:
        """Finalize test telemetry and calculate metrics."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        if status is None:
            if self.steps_healed > 0:
                status = "PASSED_WITH_HEALING"
            else:
                status = "PASSED"

        return TestCaseResult(
            test_id=self.test_id,
            name=test_name,
            status=status,
            duration_ms=round(duration_ms, 2),
            steps_total=self.steps_total,
            steps_passed=self.steps_passed,
            steps_healed=self.steps_healed,
            healing_events=self.healing_events
        )

"""Pytest integration suite for AutoHeal-AI runtime self-healing and RCA."""

import pytest
import threading
import time
import uvicorn
from playwright.sync_api import sync_playwright

from autoheal.core.runner import SmartPage
from autoheal.core.models import SelectorMetadata
from autoheal.demo_app.app import demo_app


@pytest.fixture(scope="session")
def demo_server():
    """Start local test server once for the test session."""
    server_port = 8092
    config = uvicorn.Config(demo_app, host="127.0.0.1", port=server_port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.0)
    yield f"http://127.0.0.1:{server_port}"


def test_baseline_v1_direct_pass(demo_server):
    """Verify that baseline V1 selectors pass directly with 0 heals."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        smart = SmartPage(page, test_id="TC-PYTEST-01")

        smart.goto(f"{demo_server}/?v=1")
        smart.smart_fill("#username", "qa_engineer")
        smart.smart_fill("#password", "pass123")
        smart.smart_click("#btn-login")

        page.wait_for_url("**/dashboard*")
        res = smart.finish_test("Baseline V1 Test")
        assert res.status == "PASSED"
        assert res.steps_healed == 0
        browser.close()


def test_drifted_v2_self_healing(demo_server):
    """Verify that drifted V2 selectors are autonomously healed at runtime."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        smart = SmartPage(page, test_id="TC-PYTEST-02")

        smart.goto(f"{demo_server}/?v=2")

        # Selectors that are broken in V2:
        smart.smart_fill(
            "#username",
            "qa_lead",
            metadata=SelectorMetadata(original_selector="#username", target_text="Username", target_tag="input")
        )
        smart.smart_fill(
            "#password",
            "secure_pass",
            metadata=SelectorMetadata(original_selector="#password", target_text="Password", target_tag="input")
        )
        smart.smart_click(
            "#btn-login",
            metadata=SelectorMetadata(original_selector="#btn-login", target_text="Login to Account", target_role="button")
        )

        page.wait_for_url("**/dashboard*")
        res = smart.finish_test("Drifted V2 Self-Healing Test")
        assert res.status == "PASSED_WITH_HEALING"
        assert res.steps_healed >= 3  # All 3 broken selectors were healed
        browser.close()

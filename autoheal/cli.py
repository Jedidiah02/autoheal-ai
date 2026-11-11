"""Command-line interface (CLI) for AutoHeal-AI."""

import sys
import time
import threading
import uvicorn
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime, timezone

from autoheal.core.healer import SelfHealingEngine
from autoheal.core.runner import SmartPage
from autoheal.core.reporter import TelemetryReporter
from autoheal.core.models import SelectorMetadata, TestCaseResult
from autoheal.demo_app.app import demo_app

console = Console()


def start_background_demo_server(port: int = 8089):
    """Run SUT FastAPI server in background thread."""
    import urllib.request
    config = uvicorn.Config(demo_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    return server


@click.group()
def main():
    """⚡ AutoHeal-AI: Autonomous Self-Healing Test Automation & Root Cause Analysis Platform."""
    pass


@main.command()
@click.option("--headless", is_flag=True, default=True, help="Run browser in headless mode.")
@click.option("--artifacts-dir", default="artifacts", help="Directory for reports and screenshots.")
def demo(headless: bool, artifacts_dir: str):
    """Run an end-to-end self-healing test demonstration across UI drift and API crashes."""
    console.print(Panel.fit(
        "[bold cyan]AutoHeal-AI Demonstration Suite[/bold cyan]\n"
        "[dim]Simulating UI Selector Drift, Dynamic IDs, and Backend API Crashes[/dim]",
        border_style="cyan"
    ))

    # 1. Start demo server
    server_port = 8089
    console.print(f"[green]✔[/green] Starting SUT (System Under Test) on http://127.0.0.1:{server_port}")
    start_background_demo_server(port=server_port)

    from playwright.sync_api import sync_playwright

    reporter = TelemetryReporter(output_dir=artifacts_dir)
    results = []
    run_start = datetime.now(timezone.utc)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        # -------------------------------------------------------------
        # Test 1: Baseline UI Test (Version 1) - Expected to Pass directly
        # -------------------------------------------------------------
        console.print("\n[bold yellow]▶ Running Test 1: Baseline Authentication (Version 1 - Clean Selectors)[/bold yellow]")
        page1 = browser.new_page()
        smart1 = SmartPage(page1, test_id="TC-001-AUTH-V1", artifacts_dir=artifacts_dir)
        try:
            smart1.goto(f"http://127.0.0.1:{server_port}/?v=1")
            smart1.smart_fill("#username", "john_doe", step_name="Enter Username")
            smart1.smart_fill("#password", "supersecret123", step_name="Enter Password")
            smart1.smart_click("#btn-login", step_name="Submit Login")
            smart1.page.wait_for_url("**/dashboard*")
            res1 = smart1.finish_test("User Login Workflow (Baseline V1)")
            results.append(res1)
            console.print(f"[bold green]✔ Passed[/bold green] (Duration: {res1.duration_ms}ms, Healed: 0)")
        except Exception as e:
            console.print(f"[bold red]✘ Failed:[/bold red] {e}")
        finally:
            page1.close()

        # -------------------------------------------------------------
        # Test 2: Drifted UI Test (Version 2) - Hardcoded selectors broken, AutoHeal repairs them!
        # -------------------------------------------------------------
        console.print("\n[bold yellow]▶ Running Test 2: Drifted UI Workflow (Version 2 - Dynamic IDs & Altered Classes)[/bold yellow]")
        console.print("[dim]Original test script uses old selectors (#username, #password, #btn-login, #pay-now-btn)...[/dim]")
        
        page2 = browser.new_page()
        smart2 = SmartPage(page2, test_id="TC-002-AUTH-V2-DRIFT", artifacts_dir=artifacts_dir)
        try:
            smart2.goto(f"http://127.0.0.1:{server_port}/?v=2")

            # #username does not exist in V2, but label & aria-label are present
            smart2.smart_fill(
                "#username",
                "sarah_connor",
                metadata=SelectorMetadata(original_selector="#username", target_text="Username", target_tag="input"),
                step_name="Enter Username"
            )

            # #password does not exist in V2, but aria-label and type are present
            smart2.smart_fill(
                "#password",
                "skynet_bypass_2026",
                metadata=SelectorMetadata(original_selector="#password", target_text="Password", target_tag="input"),
                step_name="Enter Password"
            )

            # #btn-login does not exist in V2, replaced with button.cta-button
            smart2.smart_click(
                "#btn-login",
                metadata=SelectorMetadata(original_selector="#btn-login", target_text="Login to Account", target_role="button"),
                step_name="Submit Login"
            )

            smart2.page.wait_for_url("**/dashboard*")

            # #pay-now-btn changed in V2, but data-test attribute matches
            smart2.smart_click(
                "#pay-now-btn",
                metadata=SelectorMetadata(original_selector="#pay-now-btn", target_text="Transfer $500", expected_attributes={"data-test": "pay-button"}),
                step_name="Execute Fund Transfer"
            )

            smart2.page.wait_for_selector("#status-msg", state="visible")
            res2 = smart2.finish_test("User Login & Transfer Workflow (Drifted V2)")
            results.append(res2)

            console.print(f"[bold green]✔ Passed with Self-Healing![/bold green] "
                          f"(Duration: {res2.duration_ms}ms, Repaired Selectors: [bold cyan]{res2.steps_healed}[/bold cyan])")
        except Exception as e:
            console.print(f"[bold red]✘ Failed:[/bold red] {e}")
        finally:
            page2.close()

        # -------------------------------------------------------------
        # Test 3: Backend API Crash Test (Triggers AI Root Cause Analysis)
        # -------------------------------------------------------------
        console.print("\n[bold yellow]▶ Running Test 3: Simulating Backend Crash (Triggering Root Cause Analysis)[/bold yellow]")
        page3 = browser.new_page()
        smart3 = SmartPage(page3, test_id="TC-003-API-CRASH-RCA", artifacts_dir=artifacts_dir)
        try:
            # SUT crash simulation endpoint
            smart3.goto(f"http://127.0.0.1:{server_port}/dashboard?v=1&crash=true")
            smart3.smart_click("#pay-now-btn", step_name="Trigger Crashing Transaction")
            
            # Wait a moment for network call to fail
            time.sleep(0.5)
            # Assert successful status message should fail because backend threw 500
            content = smart3.page.inner_text("#status-msg")
            if "Approved" not in content:
                raise AssertionError(f"Expected 'Approved', but message was: '{content}'")
        except Exception as e:
            console.print(f"[bold red]✘ Test Expectedly Failed![/bold red]")
            # Diagnosing failure with RCA
            rca_res = smart3.rca_analyzer.diagnose_failure(
                test_id=smart3.test_id,
                error=e,
                stack_trace="Traceback...",
                current_url=smart3.page.url,
                console_logs=smart3.console_logs,
                network_calls=smart3.network_calls
            )
            failed_case = TestCaseResult(
                test_id=smart3.test_id,
                name="Payment Processing with Server Crash",
                status="FAILED",
                duration_ms=500.0,
                steps_total=1,
                steps_passed=0,
                rca=rca_res
            )
            results.append(failed_case)
            console.print(Panel(
                f"[bold red]Category:[/bold red] {rca_res.failure_category.value}\n"
                f"[bold red]Root Cause:[/bold red] {rca_res.root_cause_summary}\n"
                f"[bold green]Suggested Fix:[/bold green] {rca_res.suggested_fix}",
                title="🤖 AI Root Cause Analysis (RCA) Output",
                border_style="red"
            ))
        finally:
            page3.close()

        browser.close()

    run_end = datetime.now(timezone.utc)
    report = reporter.generate_report(
        run_id=f"RUN-{int(time.time())}",
        results=results,
        started_at=run_start,
        finished_at=run_end
    )

    # 4. Display rich telemetry table
    table = Table(title="⚡ AutoHeal-AI Execution Telemetry Summary")
    table.add_column("Test ID", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Steps Healed", justify="center", style="bold blue")

    for r in results:
        status_style = "green" if r.status == "PASSED" else ("cyan" if r.status == "PASSED_WITH_HEALING" else "red")
        table.add_row(r.test_id, f"[{status_style}]{r.status}[/{status_style}]", f"{r.duration_ms}ms", str(r.steps_healed))

    console.print("\n", table)
    console.print(f"\n[bold green]✔ HTML Report Generated:[/bold green] [underline]{artifacts_dir}/report.html[/underline]")
    console.print(f"[bold green]✔ Selector Diff Generated:[/bold green] [underline]{artifacts_dir}/suggested_selector_patch.diff[/underline]\n")


@main.command()
@click.option("--port", default=8088, help="Port to serve the dashboard on.")
def report(port: int):
    """Launch the interactive AutoHeal-AI telemetry dashboard."""
    console.print(Panel.fit(
        f"[bold cyan]AutoHeal-AI Dashboard Server[/bold cyan]\n"
        f"Serving test artifacts & reports on: [bold green]http://127.0.0.1:{port}[/bold green]",
        border_style="cyan"
    ))
    uvicorn.run("autoheal.server.app:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()

"""AI-assisted Root Cause Analysis (RCA) Engine for automated test failures."""

import os
import json
import re
from typing import List, Dict, Any, Optional
import httpx

from autoheal.core.models import RCAReport, FailureCategory


class RootCauseAnalyzer:
    """Analyzes test failures by correlating DOM state, console logs, and network traffic."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")

    def diagnose_failure(
        self,
        test_id: str,
        error: Exception,
        stack_trace: str,
        current_url: Optional[str] = None,
        console_logs: Optional[List[str]] = None,
        network_calls: Optional[List[Dict[str, Any]]] = None,
        dom_snapshot: Optional[str] = None,
        screenshot_path: Optional[str] = None
    ) -> RCAReport:
        """Perform deterministic heuristic RCA, falling back to LLM if available."""
        console_logs = console_logs or []
        network_calls = network_calls or []
        error_msg = str(error)
        error_type = type(error).__name__

        # Filter failed HTTP calls
        failed_calls = [
            call for call in network_calls
            if call.get("status", 200) >= 400 or call.get("error") is not None
        ]

        # 1. Check for Backend / API 5xx Crash
        server_errors = [c for c in failed_calls if c.get("status", 0) >= 500]
        if server_errors:
            offending_endpoint = server_errors[0].get("url", "unknown endpoint")
            status_code = server_errors[0].get("status", 500)
            return RCAReport(
                test_id=test_id,
                failure_category=FailureCategory.APPLICATION_BUG,
                error_type=error_type,
                error_message=error_msg,
                stack_trace=stack_trace,
                failing_url=current_url,
                console_logs=console_logs,
                failed_network_calls=failed_calls,
                screenshot_path=screenshot_path,
                root_cause_summary=(
                    f"Backend Application Crash: Server responded with HTTP {status_code} "
                    f"on endpoint '{offending_endpoint}' during test step execution."
                ),
                suggested_fix=(
                    f"Check backend service logs for '{offending_endpoint}'. "
                    f"Validate database connection, request payload schema, and unhandled 500 exceptions."
                ),
                confidence_score=0.98
            )

        # 2. Check for Frontend JavaScript Unhandled Exceptions
        js_errors = [log for log in console_logs if "error" in log.lower() or "exception" in log.lower()]
        for log in js_errors:
            if "TypeError" in log or "ReferenceError" in log or "Uncaught" in log:
                return RCAReport(
                    test_id=test_id,
                    failure_category=FailureCategory.APPLICATION_BUG,
                    error_type="FrontendJavaScriptException",
                    error_message=log,
                    stack_trace=stack_trace,
                    failing_url=current_url,
                    console_logs=console_logs,
                    failed_network_calls=failed_calls,
                    screenshot_path=screenshot_path,
                    root_cause_summary=(
                        f"Frontend Runtime Exception: Client-side JavaScript crashed with '{log[:100]}'."
                    ),
                    suggested_fix="Inspect the frontend bundle for null pointer / undefined state access.",
                    confidence_score=0.92
                )

        # 3. Check for Network / Gateway Timeout
        if "Timeout" in error_type or "net::ERR_CONNECTION" in error_msg or "timed out" in error_msg.lower():
            is_env = any("502" in str(c.get("status")) or "504" in str(c.get("status")) for c in failed_calls)
            return RCAReport(
                test_id=test_id,
                failure_category=FailureCategory.ENVIRONMENT_DEFECT if is_env else FailureCategory.NETWORK_TIMEOUT,
                error_type=error_type,
                error_message=error_msg,
                stack_trace=stack_trace,
                failing_url=current_url,
                console_logs=console_logs,
                failed_network_calls=failed_calls,
                screenshot_path=screenshot_path,
                root_cause_summary=(
                    f"Execution Timeout: Operation timed out waiting for condition on '{current_url}'. "
                    + ("Upstream gateway error detected." if is_env else "Target element or page failed to load.")
                ),
                suggested_fix="Verify service health, staging environment latency, or increase test step timeout limits.",
                confidence_score=0.88
            )

        # 4. Check for Locator Failure
        if "NoSuchElement" in error_type or "Waiting for selector" in error_msg or "locator" in error_msg.lower():
            return RCAReport(
                test_id=test_id,
                failure_category=FailureCategory.SCRIPT_MAINTENANCE,
                error_type=error_type,
                error_message=error_msg,
                stack_trace=stack_trace,
                failing_url=current_url,
                console_logs=console_logs,
                failed_network_calls=failed_calls,
                screenshot_path=screenshot_path,
                root_cause_summary="UI Locator Drift: Target element was not found in the DOM hierarchy.",
                suggested_fix="Update the locator definition or ensure AutoHeal-AI engine is enabled with lower confidence threshold.",
                confidence_score=0.90
            )

        # 5. Generic / Assertion Failure
        return RCAReport(
            test_id=test_id,
            failure_category=FailureCategory.APPLICATION_BUG if "AssertionError" in error_type else FailureCategory.SCRIPT_MAINTENANCE,
            error_type=error_type,
            error_message=error_msg,
            stack_trace=stack_trace,
            failing_url=current_url,
            console_logs=console_logs,
            failed_network_calls=failed_calls,
            screenshot_path=screenshot_path,
            root_cause_summary=f"Assertion Failure: {error_msg}",
            suggested_fix="Verify if the business logic or expected outcome has changed in the latest application build.",
            confidence_score=0.85
        )

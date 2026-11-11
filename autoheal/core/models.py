"""Data models and schemas for AutoHeal-AI test execution, self-healing, and RCA."""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class SelectorStrategy(str, Enum):
    HEURISTIC_ATTRIBUTE = "heuristic_attribute"
    TEXT_SIMILARITY = "text_similarity"
    DOM_NEIGHBORHOOD = "dom_neighborhood"
    LLM_SEMANTIC = "llm_semantic"
    FALLBACK = "fallback"


class FailureCategory(str, Enum):
    APPLICATION_BUG = "APPLICATION_BUG"
    ENVIRONMENT_DEFECT = "ENVIRONMENT_DEFECT"
    SCRIPT_MAINTENANCE = "SCRIPT_MAINTENANCE"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"


class SelectorMetadata(BaseModel):
    """Metadata describing the target element to aid in resilient self-healing."""
    original_selector: str
    target_role: Optional[str] = None
    target_text: Optional[str] = None
    target_tag: Optional[str] = None
    expected_attributes: Dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None


class HealingEvent(BaseModel):
    """Details of a selector that failed and was autonomously healed at runtime."""
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    test_id: str
    step_name: str
    original_selector: str
    healed_selector: str
    confidence: float  # 0.0 to 1.0
    strategy: SelectorStrategy
    diff_explanation: str
    execution_time_ms: float
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None


class RCAReport(BaseModel):
    """AI Root Cause Analysis report for a test failure."""
    test_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failure_category: FailureCategory
    error_type: str
    error_message: str
    stack_trace: str
    failing_url: Optional[str] = None
    console_logs: List[str] = Field(default_factory=list)
    failed_network_calls: List[Dict[str, Any]] = Field(default_factory=list)
    screenshot_path: Optional[str] = None
    root_cause_summary: str
    suggested_fix: str
    confidence_score: float = 0.95


class TestCaseResult(BaseModel):
    """Execution status and metrics for a single test case."""
    test_id: str
    name: str
    status: str  # "PASSED", "PASSED_WITH_HEALING", "FAILED"
    duration_ms: float
    steps_total: int = 0
    steps_passed: int = 0
    steps_healed: int = 0
    healing_events: List[HealingEvent] = Field(default_factory=list)
    rca: Optional[RCAReport] = None


class TestRunReport(BaseModel):
    """Comprehensive test execution and self-healing telemetry summary."""
    run_id: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    total_tests: int
    passed_tests: int
    healed_tests: int
    failed_tests: int
    healing_rate_pct: float
    results: List[TestCaseResult] = Field(default_factory=list)

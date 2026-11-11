"""Report generator for AutoHeal-AI test telemetry and healing events."""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

from autoheal.core.models import TestRunReport, TestCaseResult, HealingEvent, RCAReport


class TelemetryReporter:
    """Generates structured JSON telemetry and visual HTML reports."""

    def __init__(self, output_dir: str = "artifacts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        run_id: str,
        results: List[TestCaseResult],
        started_at: datetime,
        finished_at: datetime
    ) -> TestRunReport:
        """Calculate aggregate metrics and export JSON and HTML reports."""
        duration_sec = round((finished_at - started_at).total_seconds(), 2)
        total = len(results)
        passed = sum(1 for r in results if r.status in ["PASSED", "PASSED_WITH_HEALING"])
        healed = sum(1 for r in results if r.status == "PASSED_WITH_HEALING")
        failed = sum(1 for r in results if r.status == "FAILED")
        healing_rate = round((healed / total * 100), 1) if total > 0 else 0.0

        report = TestRunReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_sec,
            total_tests=total,
            passed_tests=passed,
            healed_tests=healed,
            failed_tests=failed,
            healing_rate_pct=healing_rate,
            results=results
        )

        # 1. Export JSON artifact
        json_path = self.output_dir / "telemetry_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

        # 2. Export HTML report
        html_path = self.output_dir / "report.html"
        self._write_html_report(report, html_path)

        # 3. Export Patch Suggestions
        patch_path = self.output_dir / "suggested_selector_patch.diff"
        self._write_patch_diff(report, patch_path)

        return report

    def _write_patch_diff(self, report: TestRunReport, path: Path):
        """Generate a unified git diff snippet suggesting selector updates."""
        all_heals: List[HealingEvent] = []
        for r in report.results:
            all_heals.extend(r.healing_events)

        lines = [
            f"# AutoHeal-AI Suggested Selector Patch",
            f"# Run ID: {report.run_id} | Generated: {datetime.now(timezone.utc).isoformat()}",
            f"# Apply these updates to prevent future runtime healing overhead.\n"
        ]

        for h in all_heals:
            lines.append(f"--- test: {h.test_id} (step: {h.step_name})")
            lines.append(f"- selector: {h.original_selector}")
            lines.append(f"+ selector: {h.healed_selector}  # Confidence: {int(h.confidence*100)}% ({h.diff_explanation})")
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _write_html_report(self, report: TestRunReport, path: Path):
        """Render modern, responsive dark-mode HTML test dashboard."""
        all_heals: List[HealingEvent] = []
        for r in report.results:
            all_heals.extend(r.healing_events)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AutoHeal-AI Telemetry Report - {report.run_id}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Inter', sans-serif; background-color: #0f172a; color: #f8fafc; }}
    .badge-pass {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }}
    .badge-heal {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }}
    .badge-fail {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
  </style>
</head>
<body class="p-8">
  <div class="max-w-6xl mx-auto space-y-8">
    
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-slate-800 pb-6">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-2xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">AutoHeal-AI</span>
          <span class="text-xs px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">Run: {report.run_id}</span>
        </div>
        <p class="text-sm text-slate-400 mt-1">Autonomous Self-Healing Test Automation & Root Cause Analysis Engine</p>
      </div>
      <div class="text-right text-xs text-slate-400 font-mono">
        <div>Completed: {report.finished_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
        <div>Duration: {report.duration_seconds}s</div>
      </div>
    </div>

    <!-- Metric Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="p-5 rounded-xl bg-slate-900 border border-slate-800">
        <div class="text-xs font-semibold uppercase text-slate-400">Total Tests</div>
        <div class="text-3xl font-bold mt-2 text-white">{report.total_tests}</div>
      </div>
      <div class="p-5 rounded-xl bg-slate-900 border border-slate-800">
        <div class="text-xs font-semibold uppercase text-slate-400">Passed (Direct)</div>
        <div class="text-3xl font-bold mt-2 text-emerald-400">{report.passed_tests - report.healed_tests}</div>
      </div>
      <div class="p-5 rounded-xl bg-slate-900 border border-slate-800">
        <div class="text-xs font-semibold uppercase text-slate-400">Autonomously Healed</div>
        <div class="text-3xl font-bold mt-2 text-blue-400">{report.healed_tests} <span class="text-xs font-normal text-slate-400">({report.healing_rate_pct}%)</span></div>
      </div>
      <div class="p-5 rounded-xl bg-slate-900 border border-slate-800">
        <div class="text-xs font-semibold uppercase text-slate-400">Failed / RCA Triggered</div>
        <div class="text-3xl font-bold mt-2 text-rose-400">{report.failed_tests}</div>
      </div>
    </div>

    <!-- Self-Healing Events Section -->
    <div class="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-white flex items-center gap-2">
          <span>⚡</span> Runtime Selector Healing Telemetry
        </h2>
        <span class="text-xs text-slate-400">{len(all_heals)} Locators Autonomously Repaired</span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="text-xs uppercase bg-slate-800/60 text-slate-400 font-mono">
            <tr>
              <th class="p-3 rounded-l-lg">Step / Test</th>
              <th class="p-3">Original (Broken) Selector</th>
              <th class="p-3">Auto-Healed Locator</th>
              <th class="p-3">Confidence</th>
              <th class="p-3">Strategy</th>
              <th class="p-3 rounded-r-lg">Latency</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
"""
        for h in all_heals:
            html += f"""
            <tr class="hover:bg-slate-800/30 font-mono text-xs">
              <td class="p-3 font-sans font-medium text-slate-200">{h.step_name}<br><span class="text-slate-500 text-xs">{h.test_id}</span></td>
              <td class="p-3 text-rose-400 bg-rose-500/5">{h.original_selector}</td>
              <td class="p-3 text-emerald-400 bg-emerald-500/5 font-semibold">{h.healed_selector}</td>
              <td class="p-3"><span class="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-bold">{int(h.confidence*100)}%</span></td>
              <td class="p-3 text-slate-300 font-sans text-xs">{h.strategy.value}<br><span class="text-slate-500 text-[10px]">{h.diff_explanation}</span></td>
              <td class="p-3 text-slate-400">{h.execution_time_ms}ms</td>
            </tr>
"""

        html += """
          </tbody>
        </table>
      </div>
    </div>

    <!-- Suggested Git Patch Preview -->
    <div class="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-3">
      <h2 class="text-lg font-semibold text-white flex items-center gap-2">
        <span>🛠️</span> Code Fix Recommendation (Patch Output)
      </h2>
      <p class="text-xs text-slate-400">Apply these suggested updates to your test suite to eliminate runtime healing overhead permanently:</p>
      <pre class="bg-black/50 p-4 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto border border-slate-800/80">"""
        
        for h in all_heals:
            html += f"\n- {h.original_selector}\n+ {h.healed_selector}  # Confidence: {int(h.confidence*100)}% ({h.diff_explanation})"

        html += """</pre>
    </div>

  </div>
</body>
</html>
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

"""Assemble the check-up: discovery -> checks -> score -> text report."""

from __future__ import annotations

import os
from typing import Callable, List

from . import bloat, imports, scanner, shadow
from .models import Issue, Report, RuleFile

ERROR_COST = 15
WARNING_COST = 5


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def checkup(root: str, read: Callable[[str], str] = _read_text) -> Report:
    """Run the full check-up against *root* and return a Report."""
    root = os.path.abspath(root)
    report = Report(root=root)

    files = scanner.discover(root, read=read)
    report.files = files
    loaded = scanner.loaded_files(files)

    issues: List[Issue] = []
    issues.extend(shadow.check_shadowing(files))
    for rf in loaded:
        issues.extend(imports.check_imports(rf, root, read=read))
    issues.extend(bloat.check_bloat(loaded, read=read))

    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    infos = sum(1 for i in issues if i.severity == "info")
    score = max(0, 100 - ERROR_COST * errors - WARNING_COST * warnings)

    report.issues = issues
    report.score = score
    report.grade = grade_for(score)
    report.stats = {
        "files_found": len(files),
        "files_loaded": len(loaded),
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
    }
    return report


_SEV_MARK = {"error": "[ERROR]", "warning": "[WARN] ", "info": "[INFO] "}

_KIND_LABEL = {
    "claude_md": "PRIMARY -- loaded by Claude Code",
    "claude_local_md": "personal overrides -- loaded alongside",
    "agents_md": "fallback -- loaded only if no CLAUDE.md nearby",
    "claude_dir": "project config directory",
    "other": "other agent ecosystem (not simulated)",
    "imported": "pulled in via @import",
}


def render_text(report: Report) -> str:
    """Render the report as human-readable plain text."""
    out: List[str] = []
    out.append("rules-doctor report: %s" % report.root)
    out.append("Score: %d/100 (%s)" % (report.score, report.grade))
    out.append("")

    out.append("Rule files found (%d, %d loaded):" % (
        report.stats.get("files_found", 0),
        report.stats.get("files_loaded", 0),
    ))
    if not report.files:
        out.append("  (none)")
    for rf in report.files:
        label = _KIND_LABEL.get(rf.kind, rf.kind)
        where = rf.directory or "project root"
        out.append("  - %s [%s] -- %s" % (rf.rel, where, label))
    out.append("")

    if not report.issues:
        out.append("No issues found. Your rules are in good shape.")
        return "\n".join(out) + "\n"

    out.append("Issues (%d):" % len(report.issues))
    for issue in report.issues:
        out.append("")
        loc = issue.file if issue.file else "(project)"
        out.append("%s %s -- %s" % (_SEV_MARK[issue.severity], issue.code, loc))
        out.append("  %s" % issue.message)
        out.append("  Fix: %s" % issue.fix)
    out.append("")
    out.append(
        "Heuristic simulation -- see README 'Honest limitations'. "
        "When in doubt, test with the real Claude Code."
    )
    return "\n".join(out) + "\n"

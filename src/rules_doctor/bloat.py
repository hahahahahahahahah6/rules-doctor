"""Bloat checks: estimate how much rule text the model must digest.

Heuristics (documented, not exact):

* Tokens are estimated as ``len(characters) // 4`` -- the common rough
  rule of thumb for English prose. CJK text, code, and URLs deviate.
* An "instruction line" is a non-empty line outside fenced code blocks
  that is not a Markdown heading or horizontal rule. Past roughly 150 of
  them, models demonstrably start dropping or deprioritizing rules.
"""

from __future__ import annotations

import re
from typing import Callable, List

from .models import Issue, RuleFile

INSTRUCTION_LINE_LIMIT = 150
TOTAL_TOKEN_WARN = 8000

_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_HR_RE = re.compile(r"^\s*([-*_]\s*){3,}\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def estimate_tokens(text: str) -> int:
    """Rough token estimate for English prose."""
    return len(text) // 4


def instruction_lines(text: str) -> int:
    """Count lines that read as instructions (outside code fences)."""
    count = 0
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(line) or _HR_RE.match(line):
            continue
        count += 1
    return count


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def check_bloat(
    files: List[RuleFile],
    read: Callable[[str], str] = _read_text,
) -> List[Issue]:
    """Check the *loaded* rule files for instruction bloat."""
    issues: List[Issue] = []
    total_tokens = 0
    total_instructions = 0

    for rf in files:
        try:
            text = read(rf.path)
        except OSError:
            continue
        tokens = estimate_tokens(text)
        instructions = instruction_lines(text)
        total_tokens += tokens
        total_instructions += instructions

        if instructions > INSTRUCTION_LINE_LIMIT:
            issues.append(
                Issue(
                    code="BLOATED_FILE",
                    severity="warning",
                    file=rf.rel,
                    message="%s has ~%d instruction lines (heuristic limit ~%d) and "
                    "~%d estimated tokens. Models start ignoring rules past this "
                    "size." % (rf.rel, instructions, INSTRUCTION_LINE_LIMIT, tokens),
                    fix="Split by topic into @imported files (e.g. style.md, "
                    "commands.md), delete stale or duplicated rules, and keep "
                    "the root file to the 20% of rules that matter 80% of the time.",
                )
            )

    if total_tokens > TOTAL_TOKEN_WARN and len(files) > 1:
        issues.append(
            Issue(
                code="BLOATED_TOTAL",
                severity="warning",
                file="",
                message="Combined loaded rules are ~%d estimated tokens across %d "
                "files. That is a lot of context spent before the task even starts."
                % (total_tokens, len(files)),
                fix="Triage: keep only rules the model gets wrong without them. "
                "Move reference material (API docs, long examples) into files "
                "imported on demand instead of the always-loaded root file.",
            )
        )

    return issues

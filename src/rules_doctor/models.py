"""Shared data structures for rules-doctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RuleFile:
    """A discovered rule/config file."""

    path: str  # absolute path
    rel: str  # path relative to project root ("" never; use "." for root file's dir)
    kind: str  # claude_md | claude_local_md | agents_md | claude_dir | other
    directory: str  # containing dir, relative to root ("" == project root)
    size_bytes: int = 0
    lines: int = 0


@dataclass
class Issue:
    """A single finding."""

    code: str  # e.g. SHADOWED_AGENTS_MD
    severity: str  # error | warning | info
    file: str  # rel path of the affected file, or "" for project-level
    message: str
    fix: str


@dataclass
class ImportRef:
    """A single @import reference found in a rule file."""

    line_no: int
    raw: str  # the raw @path text as written
    path: str  # cleaned path
    in_fence: bool  # inside a fenced code block -> dead import
    inline: bool  # mid-line mention rather than a directive line


@dataclass
class Report:
    """Full check-up result for one project directory."""

    root: str
    files: List[RuleFile] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    score: int = 100
    grade: str = "A"
    stats: Dict[str, object] = field(default_factory=dict)

    def by_severity(self, severity: str) -> List[Issue]:
        return [i for i in self.issues if i.severity == severity]

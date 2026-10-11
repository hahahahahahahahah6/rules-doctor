"""v0.3 reliability checks: the ADR / scope-creep lint rule set.

rules-doctor v0.1-v0.2 checked that rule files *load* correctly (imports,
shadowing, bloat). v0.3 checks that the rules are *worth loading*: are they
reliable enough that an agent will actually follow them mid-task, and is the
agent's scope of action bounded so it cannot creep into files it was never
asked to touch?

New check codes:

- ``SCOPE_BOUNDARY_MISSING`` (warning): a rule file never says which
  files/directories the agent may touch. Without an explicit scope, "stay in
  your lane" is not a rule the agent can follow -- this is the static proxy
  for scope-creep risk (agents editing files beyond their instructions).
- ``CONTRADICTORY_RULES`` (error): two directives in the same file say
  opposite things about the same topic. A model faced with "always X" and
  "never X" picks one and silently drops the other mid-task.
- ``VAGUE_DIRECTIVE`` (warning): weasel phrasing ("as needed", "remember to",
  "when appropriate") that reads like guidance but is unenforceable -- the
  classic pattern of rules that get ignored halfway through a task.
- ``ADR_MISSING`` (warning): a non-trivial project with no Architecture
  Decision Records. Decisions made by agents without a record get
  re-litigated (or silently reversed) by the next session.

All heuristics are best-effort; see README "Honest limitations".
"""

from __future__ import annotations

import os
import re
from typing import Callable, List, Optional, Sequence, Tuple

from .models import Issue, RuleFile

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```")


def _content_lines(text: str) -> List[str]:
    """Lines outside fenced code blocks (code examples are not rules)."""
    out: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# SCOPE_BOUNDARY_MISSING
# ---------------------------------------------------------------------------

# Rule-file kinds that act as agent instructions and therefore need a scope.
_SCOPED_KINDS = {
    "claude_md",
    "agents_md",
    "claude_local_md",
    "cursorrules",
    "other",  # other-ecosystem rule *files* (dirs are filtered out by callers)
}

# Tiny files (< this many content lines) are exempt: a five-line rule file
# cannot meaningfully scope-creep.
MIN_SCOPE_LINES = 10

_SCOPE_PATTERNS = [
    # Section headers that declare a scope.
    re.compile(
        r"^#{1,6}\s+.*\b(scope|boundar(y|ies)|allowed|forbidden|"
        r"off[- ]?limits|permitted|restrictions?)\b",
        re.IGNORECASE,
    ),
    # Directives pinning down which files the agent may touch.
    re.compile(r"\bonly\s+(edit|modify|touch|change|work\s+on|write\s+to)\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+(edit|modify|touch|change|delete|create)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(edit|modify|touch|change|delete|create)\b", re.IGNORECASE),
    re.compile(r"\bscope\s+of\s+(work|changes?|this\s+\w+)\b", re.IGNORECASE),
    re.compile(r"\brestrict\w*\s+(edits?|changes?|work)\s+to\b", re.IGNORECASE),
    re.compile(r"\b(in|under)\s+scope\b", re.IGNORECASE),
    re.compile(r"\bout\s+of\s+scope\b", re.IGNORECASE),
    re.compile(r"\btouch\s+only\b", re.IGNORECASE),
]


def has_scope_boundary(text: str) -> bool:
    """True if *text* declares an explicit scope for the agent's edits."""
    for line in _content_lines(text):
        for pat in _SCOPE_PATTERNS:
            if pat.search(line):
                return True
    return False


def check_scope_boundary(
    files: Sequence[RuleFile], read: Callable[[str], str]
) -> List[Issue]:
    issues: List[Issue] = []
    for rf in files:
        if rf.kind not in _SCOPED_KINDS:
            continue
        if not os.path.isfile(rf.path):
            continue
        try:
            text = read(rf.path)
        except OSError:
            continue
        lines = [ln for ln in _content_lines(text) if ln.strip()]
        if len(lines) < MIN_SCOPE_LINES:
            continue
        if not has_scope_boundary(text):
            issues.append(
                Issue(
                    code="SCOPE_BOUNDARY_MISSING",
                    severity="warning",
                    file=rf.rel,
                    message=(
                        "%s has %d instruction lines but never says which "
                        "files/directories the agent may touch. Without an "
                        "explicit scope, edits creep into files nobody asked "
                        "for." % (rf.rel, len(lines))
                    ),
                    fix=(
                        "Add a '## Scope' section: list the directories the "
                        "agent may modify and mark the rest off-limits, e.g. "
                        "'Only edit files under src/; never touch "
                        "migrations/ or *.lock files.'"
                    ),
                )
            )
    return issues


# ---------------------------------------------------------------------------
# CONTRADICTORY_RULES
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")

_NEGATIONS = frozenset(
    [
        "never", "not", "no", "n't",
        "dont", "don't", "doesnt", "doesn't", "didnt", "didn't",
        "wont", "won't", "cant", "can't", "cannot",
        "shouldnt", "shouldn't", "mustnt", "mustn't",
        "couldnt", "couldn't", "wouldnt", "wouldn't",
        "avoid", "avoiding", "skip", "skipping",
        "forbidden", "prohibited", "prohibit", "banned", "ban",
        "refrain", "disallow", "disallowed",
    ]
)

_POSITIVES = frozenset(
    [
        "always", "must", "should", "shall",
        "required", "require", "requires", "mandatory",
        "ensure", "guarantee",
    ]
)

_STOPWORDS = frozenset(
    """
    a an the and or but if then else when while for with of at by to in on
    from as is are was were be been being it its this that these those
    their there here your you we they he she them his her our us all any
    each every few more most other some such nor only own same so than too
    very can will just now my mine into out up down over under again once
    also file files code project repo repository using used use via per
    thing things way ways get gets make makes made sure
    """.split()
)


def _stem(word: str) -> str:
    if len(word) > 4:
        if word.endswith("ies") and len(word) > 5:
            return word[:-3] + "y"
        if word.endswith("es") and not word.endswith(("sses", "xes", "ches", "shes")):
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
    return word


class _Rule:
    __slots__ = ("line_no", "text", "polarity", "topic")

    def __init__(self, line_no: int, text: str):
        self.line_no = line_no
        self.text = text
        words = [w.lower() for w in _WORD_RE.findall(text)]
        if any(w in _NEGATIONS for w in words):
            self.polarity = "neg"
        elif any(w in _POSITIVES for w in words):
            self.polarity = "pos"
        else:
            self.polarity = "neu"
        self.topic = {
            _stem(w)
            for w in words
            if w not in _STOPWORDS and w not in _NEGATIONS and w not in _POSITIVES
            and len(w) > 1
        }


def _extract_rules(text: str) -> List[_Rule]:
    rules: List[_Rule] = []
    for idx, line in enumerate(_content_lines(text), start=1):
        m = _BULLET_RE.match(line)
        if m:
            body = m.group(1).strip()
            if body:
                rules.append(_Rule(idx, body))
    return rules


def _short(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def check_contradictions(
    files: Sequence[RuleFile], read: Callable[[str], str], max_per_file: int = 3
) -> List[Issue]:
    """Flag pairs of directives that say opposite things about one topic."""
    issues: List[Issue] = []
    for rf in files:
        if rf.kind not in _SCOPED_KINDS:
            continue
        if not os.path.isfile(rf.path):
            continue
        try:
            text = read(rf.path)
        except OSError:
            continue
        rules = [r for r in _extract_rules(text) if len(r.topic) >= 2]
        found = 0
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                a, b = rules[i], rules[j]
                if not (
                    (a.polarity == "neg") != (b.polarity == "neg")
                ):
                    continue
                shared = a.topic & b.topic
                if len(shared) < 2:
                    continue
                issues.append(
                    Issue(
                        code="CONTRADICTORY_RULES",
                        severity="error",
                        file=rf.rel,
                        message=(
                            "Line %d contradicts line %d in %s: %r vs %r. A "
                            "model faced with both picks one and silently "
                            "drops the other mid-task."
                            % (a.line_no, b.line_no, rf.rel,
                               _short(a.text), _short(b.text))
                        ),
                        fix=(
                            "Decide which rule wins, then delete or rewrite "
                            "the loser. Contradictory rules train the model "
                            "to ignore both."
                        ),
                    )
                )
                found += 1
                if found >= max_per_file:
                    break
            if found >= max_per_file:
                break
    return issues


# ---------------------------------------------------------------------------
# VAGUE_DIRECTIVE
# ---------------------------------------------------------------------------

_VAGUE_PHRASES = [
    "as needed",
    "when appropriate",
    "where appropriate",
    "as appropriate",
    "whenever possible",
    "if possible",
    "try to",
    "remember to",
    "don't forget",
    "dont forget",
    "do not forget",
    "generally",
    "in general",
    "usually",
    "normally",
    "at your discretion",
    "feel free",
    "best effort",
    "where applicable",
    "when applicable",
]

_VAGUE_RES = [
    re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in _VAGUE_PHRASES
]


def check_vague_directives(
    files: Sequence[RuleFile], read: Callable[[str], str], max_per_file: int = 4
) -> List[Issue]:
    """Flag weasel phrasing that models reliably ignore mid-task."""
    issues: List[Issue] = []
    for rf in files:
        if rf.kind not in _SCOPED_KINDS:
            continue
        if not os.path.isfile(rf.path):
            continue
        try:
            text = read(rf.path)
        except OSError:
            continue
        found = 0
        for idx, line in enumerate(_content_lines(text), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            hit: Optional[str] = None
            for pat, phrase in zip(_VAGUE_RES, _VAGUE_PHRASES):
                if pat.search(stripped):
                    hit = phrase
                    break
            if hit is None:
                continue
            issues.append(
                Issue(
                    code="VAGUE_DIRECTIVE",
                    severity="warning",
                    file=rf.rel,
                    message=(
                        "Line %d of %s uses weasel phrasing %r -- reads like "
                        "guidance but is unenforceable, so it is the first "
                        "thing dropped mid-task: %r"
                        % (idx, rf.rel, hit, _short(stripped))
                    ),
                    fix=(
                        "Rewrite as a concrete, checkable instruction: say "
                        "exactly what to do and when, with no wiggle room."
                    ),
                )
            )
            found += 1
            if found >= max_per_file:
                break
    return issues


# ---------------------------------------------------------------------------
# ADR_MISSING
# ---------------------------------------------------------------------------

_ADR_DIR_NAMES = {"adr", "adrs", "decisions", "decision-log", "decisionlog"}
_ADR_FILE_RES = [
    re.compile(r"(?i)^\d{4}-.+\.(md|mdx|rst|txt)$"),  # 0001-*.md Nygard style
    re.compile(r"(?i)^adr[-_].*\.(md|mdx|rst|txt)$"),
    re.compile(r"(?i)^decisions?\.(md|mdx|rst|txt)$"),
    re.compile(r"(?i)^architecture[-_]decision.*\.(md|mdx|rst|txt)$"),
]

_SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".scala",
}
_SOURCE_DIRS = {
    "src", "lib", "app", "packages", "backend", "frontend", "server",
    "client", "cmd", "pkg", "internal", "core",
}
_SKIP_WALK = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".eggs", "target", ".idea", ".vscode",
}

# A project with more than this many source files (or a conventional source
# dir) is "non-trivial" enough to deserve ADRs.
MIN_SOURCE_FILES_FOR_ADR = 5


def _walk_source_files(root: str) -> Tuple[int, bool]:
    """Return (source file count, has conventional source dir)."""
    count = 0
    has_src_dir = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_WALK]
        if os.path.basename(dirpath) in _SOURCE_DIRS:
            if filenames:
                has_src_dir = True
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in _SOURCE_EXTS:
                count += 1
    return count, has_src_dir


def has_adr(root: str) -> bool:
    """True if the project keeps Architecture Decision Records."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_WALK]
        if os.path.basename(dirpath).lower() in _ADR_DIR_NAMES:
            return True
        for fn in filenames:
            for pat in _ADR_FILE_RES:
                if pat.match(fn):
                    return True
    return False


def check_adr(root: str) -> List[Issue]:
    issues: List[Issue] = []
    n_sources, has_src_dir = _walk_source_files(root)
    nontrivial = n_sources > MIN_SOURCE_FILES_FOR_ADR or has_src_dir
    if nontrivial and not has_adr(root):
        issues.append(
            Issue(
                code="ADR_MISSING",
                severity="warning",
                file="",
                message=(
                    "Non-trivial project (%d source files) keeps no "
                    "Architecture Decision Records. Decisions made by one "
                    "agent session get re-litigated -- or silently reversed "
                    "-- by the next." % n_sources
                ),
                fix=(
                    "Record significant decisions in docs/adr/ as "
                    "NNNN-short-title.md (context, decision, consequences). "
                    "One file per decision; the Nygard template is enough."
                ),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def check_reliability(
    files: Sequence[RuleFile],
    loaded: Sequence[RuleFile],
    root: str,
    read: Callable[[str], str],
) -> List[Issue]:
    """Run all v0.3 reliability checks."""
    # Content-bearing rule files: everything the simulated loader reads, plus
    # other-ecosystem rule *files* (e.g. .cursorrules) discovered by the
    # scanner. Imported fragments keep their v0.2 treatment (bloat only).
    content_files: List[RuleFile] = [
        rf for rf in loaded if rf.kind in _SCOPED_KINDS
    ]
    seen = {os.path.realpath(rf.path) for rf in content_files}
    for rf in files:
        if rf.kind != "other" or not os.path.isfile(rf.path):
            continue
        key = os.path.realpath(rf.path)
        if key in seen:
            continue
        seen.add(key)
        content_files.append(rf)

    issues: List[Issue] = []
    issues.extend(check_scope_boundary(content_files, read))
    issues.extend(check_contradictions(content_files, read))
    issues.extend(check_vague_directives(content_files, read))
    issues.extend(check_adr(root))
    return issues

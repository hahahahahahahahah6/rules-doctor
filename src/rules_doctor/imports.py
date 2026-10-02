"""@import expansion checks.

Claude Code expands ``@path/to/file`` references found in rule files.
rules-doctor statically follows those references and flags:

* imports written inside fenced code blocks (dead imports -- silently ignored)
* imports pointing at files that do not exist
* import chains nested deeper than 4 hops
* circular import chains
* imports escaping the project root via ``..``
"""

from __future__ import annotations

import os
import re
from typing import Callable, List, Set

from .models import ImportRef, Issue, RuleFile

MAX_IMPORT_DEPTH = 4

# A directive import: a line whose first non-space token is @path.
_DIRECTIVE_RE = re.compile(r"^\s*@(?P<path>\S+)\s*$")
# Quoted variant: @"path with spaces.md"
_QUOTED_RE = re.compile(r'^\s*@"(?P<path>[^"]+)"\s*$')
# Inline mention: @path/to/file.md appearing mid-line (outside fences).
_INLINE_RE = re.compile(r"(?<![\w@`])@(?P<path>[\w][\w\-./]*\.\w[\w]*)")
# Fence openers: ``` or ~~~ (info strings allowed).
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _clean_path(raw: str) -> str:
    path = raw.strip().strip("\"'").strip()
    # Drop URL fragments / query strings: @rules.md#section
    path = re.split(r"[#?]", path, maxsplit=1)[0].strip()
    return path


def find_imports(text: str) -> List[ImportRef]:
    """Extract every @import-looking reference from *text*.

    Tracks fenced code blocks so references inside them can be flagged
    as dead imports.
    """
    refs: List[ImportRef] = []
    in_fence = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue

        m = _QUOTED_RE.match(line) or _DIRECTIVE_RE.match(line)
        if m:
            raw = m.group("path")
            path = _clean_path(raw)
            if path:
                refs.append(
                    ImportRef(
                        line_no=lineno,
                        raw=raw,
                        path=path,
                        in_fence=in_fence,
                        inline=False,
                    )
                )
            continue

        if not in_fence:
            for m in _INLINE_RE.finditer(line):
                path = _clean_path(m.group("path"))
                if path:
                    refs.append(
                        ImportRef(
                            line_no=lineno,
                            raw=m.group("path"),
                            path=path,
                            in_fence=False,
                            inline=True,
                        )
                    )
    return refs


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def check_imports(
    rule_file: RuleFile,
    root: str,
    read: Callable[[str], str] = _read_text,
) -> List[Issue]:
    """Check @imports of a single loaded rule file, following nesting."""
    issues: List[Issue] = []
    try:
        text = read(rule_file.path)
    except OSError as exc:
        return [
            Issue(
                code="UNREADABLE_FILE",
                severity="warning",
                file=rule_file.rel,
                message="Could not read rule file: %s" % exc,
                fix="Make sure the file is readable UTF-8 text.",
            )
        ]

    for ref in find_imports(text):
        _check_ref(rule_file, ref, root, read, issues, chain=(), depth=1)
    return issues


def _check_ref(
    rule_file: RuleFile,
    ref: ImportRef,
    root: str,
    read: Callable[[str], str],
    issues: List[Issue],
    chain: tuple,
    depth: int,
) -> None:
    where = "%s:%d" % (rule_file.rel, ref.line_no)

    # 1. Dead import: inside a fenced code block the @ is literal text.
    if ref.in_fence:
        issues.append(
            Issue(
                code="DEAD_IMPORT",
                severity="warning",
                file=rule_file.rel,
                message="Dead @import at %s: '@%s' sits inside a fenced code block, "
                "so it is rendered as literal text and never expanded." % (where, ref.raw),
                fix="Move the import out of the code fence onto its own line, "
                "e.g. `@%s` with no surrounding backticks." % ref.path,
            )
        )
        return

    base_dir = os.path.dirname(rule_file.path)
    target = os.path.normpath(os.path.join(base_dir, ref.path))

    # 2. Escaping the project root.
    if os.path.commonpath([root, target]) != root:
        issues.append(
            Issue(
                code="IMPORT_ESCAPES_ROOT",
                severity="warning",
                file=rule_file.rel,
                message="Import at %s escapes the project root: '@%s'."
                % (where, ref.raw),
                fix="Keep imported files inside the project so the rules travel "
                "with the repo; use a path relative to the project root.",
            )
        )

    # 3. Missing / not-a-file targets.
    if not os.path.exists(target):
        issues.append(
            Issue(
                code="BROKEN_IMPORT",
                severity="error",
                file=rule_file.rel,
                message="Broken @import at %s: '@%s' points to a file that does not exist."
                % (where, ref.raw),
                fix="Create the missing file, or fix the path. Remember the path is "
                "resolved relative to %s." % rule_file.rel,
            )
        )
        return
    if os.path.isdir(target):
        issues.append(
            Issue(
                code="BROKEN_IMPORT",
                severity="error",
                file=rule_file.rel,
                message="Broken @import at %s: '@%s' points to a directory, not a file."
                % (where, ref.raw),
                fix="Point the import at a specific file inside that directory.",
            )
        )
        return

    # 4. Nesting depth.
    if depth > MAX_IMPORT_DEPTH:
        issues.append(
            Issue(
                code="IMPORT_TOO_DEEP",
                severity="error",
                file=rule_file.rel,
                message="Import chain too deep at %s: '@%s' is hop %d "
                "(limit is %d). Deeper imports are silently dropped."
                % (where, ref.raw, depth, MAX_IMPORT_DEPTH),
                fix="Flatten the chain: import the deep files directly from %s "
                "instead of nesting them." % rule_file.rel,
            )
        )
        return

    # 5. Circular imports.
    if target in chain:
        loop = " -> ".join(
            [os.path.relpath(p, root) for p in chain + (target,)]
        )
        issues.append(
            Issue(
                code="CIRCULAR_IMPORT",
                severity="error",
                file=rule_file.rel,
                message="Circular @import at %s: %s." % (where, loop),
                fix="Break the cycle by removing one of the imports in the loop.",
            )
        )
        return

    # 6. Inline mentions are uncertain: flag for verification, don't recurse.
    if ref.inline:
        issues.append(
            Issue(
                code="INLINE_IMPORT_UNCERTAIN",
                severity="info",
                file=rule_file.rel,
                message="Inline @mention at %s ('@%s'): mid-line mentions may not "
                "expand the same way a directive-line import does."
                % (where, ref.raw),
                fix="Prefer a directive line (the import alone on its own line) "
                "for anything that must be loaded.",
            )
        )
        return

    # Recurse into the imported file.
    try:
        sub_text = read(target)
    except OSError:
        return
    sub_file = RuleFile(
        path=target,
        rel=os.path.relpath(target, root),
        kind="imported",
        directory=os.path.relpath(os.path.dirname(target), root),
    )
    for sub_ref in find_imports(sub_text):
        _check_ref(
            sub_file, sub_ref, root, read, issues,
            chain=chain + (target,), depth=depth + 1,
        )

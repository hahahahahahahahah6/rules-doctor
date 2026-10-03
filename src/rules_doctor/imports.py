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
import stat
from typing import Callable, List, Optional, Set

from .models import ImportRef, Issue, RuleFile

MAX_IMPORT_DEPTH = 4
MAX_IMPORT_BYTES = 1024 * 1024

# A directive import: a line whose first non-space token is @path.
_DIRECTIVE_RE = re.compile(r"^\s*@(?P<path>\S+)\s*$")
# Quoted variant: @"path with spaces.md"
_QUOTED_RE = re.compile(r'^\s*@"(?P<path>[^"]+)"\s*$')
# Inline mention: @path/to/file.md appearing mid-line (outside fences).
_INLINE_RE = re.compile(r"(?<![\w@`])@(?P<path>[\w][\w\-./]*\.\w[\w]*)")
# Fence openers: ``` or ~~~ (info strings allowed).
_FENCE_RE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<rest>.*)$")


def _plausible_path(path: str) -> bool:
    """Exclude social mentions and URLs while retaining file-like references."""
    if not path or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path):
        return False
    if path.startswith("@") or any(ch in path for ch in "<>|\0"):
        return False
    basename = path.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1]
    return (
        "/" in path
        or "\\" in path
        or path.startswith((".", "~"))
        or "." in basename
    )


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
    fence_char: Optional[str] = None
    fence_length = 0

    for lineno, line in enumerate(text.splitlines(), start=1):
        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group("marker")
            rest = fence.group("rest")
            if fence_char is None:
                fence_char, fence_length = marker[0], len(marker)
                continue
            # A closer must use the opening character, be at least as long, and
            # contain no info string (only optional whitespace).
            if marker[0] == fence_char and len(marker) >= fence_length and not rest.strip():
                fence_char, fence_length = None, 0
                continue

        m = _QUOTED_RE.match(line) or _DIRECTIVE_RE.match(line)
        if m:
            raw = m.group("path")
            path = _clean_path(raw)
            if _plausible_path(path):
                refs.append(
                    ImportRef(
                        line_no=lineno,
                        raw=raw,
                        path=path,
                        in_fence=fence_char is not None,
                        inline=False,
                    )
                )
            continue

        if fence_char is None:
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
        text = fh.read(MAX_IMPORT_BYTES + 1)
    if len(text.encode("utf-8", "replace")) > MAX_IMPORT_BYTES:
        raise OSError("file exceeds the %d-byte import limit" % MAX_IMPORT_BYTES)
    return text


def check_imports(
    rule_file: RuleFile,
    root: str,
    read: Callable[[str], str] = _read_text,
    visited: Optional[Set[str]] = None,
    imported: Optional[List[RuleFile]] = None,
) -> List[Issue]:
    """Check @imports of a single loaded rule file, following nesting."""
    issues: List[Issue] = []
    root = os.path.realpath(root)
    if visited is None:
        visited = set()
    if imported is None:
        imported = []
    source = os.path.realpath(rule_file.path)
    if source in visited:
        return issues
    visited.add(source)
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
        _check_ref(rule_file, ref, root, read, issues, visited, imported,
                   chain=(source,), depth=1)
    return issues


def _check_ref(
    rule_file: RuleFile,
    ref: ImportRef,
    root: str,
    read: Callable[[str], str],
    issues: List[Issue],
    visited: Set[str],
    imported: List[RuleFile],
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
    # realpath resolves every symlink component.  Normalize only afterward so
    # containment is checked against the object that would actually be read.
    target = os.path.normpath(os.path.realpath(os.path.join(base_dir, ref.path)))

    # 2. Escaping the project root.
    try:
        escapes = os.path.commonpath([root, target]) != root
    except ValueError:
        escapes = True
    if escapes:
        issues.append(
            Issue(
                code="IMPORT_ESCAPES_ROOT",
                severity="error",
                file=rule_file.rel,
                message="Import at %s escapes the project root: '@%s'."
                % (where, ref.raw),
                fix="Keep imported files inside the project so the rules travel "
                "with the repo; use a path relative to the project root.",
            )
        )
        return

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
    try:
        target_stat = os.stat(target)
        mode = target_stat.st_mode
    except OSError as exc:
        issues.append(_unreadable(rule_file, where, ref, exc))
        return
    if not stat.S_ISREG(mode):
        issues.append(
            Issue(
                code="BROKEN_IMPORT",
                severity="error",
                file=rule_file.rel,
                message="Broken @import at %s: '@%s' does not point to a regular file."
                % (where, ref.raw),
                fix="Point the import at a regular file inside the project.",
            )
        )
        return
    if target_stat.st_size > MAX_IMPORT_BYTES:
        issues.append(_unreadable(
            rule_file, where, ref,
            OSError("file exceeds the %d-byte import limit" % MAX_IMPORT_BYTES),
        ))
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

    # The first traversal owns all findings and bloat for a target.  This also
    # prevents repeated imports from multiplying work and scores.
    if target in visited:
        return
    visited.add(target)

    # Recurse into the imported file.
    try:
        sub_text = read(target)
    except OSError as exc:
        issues.append(_unreadable(rule_file, where, ref, exc))
        return
    sub_file = RuleFile(
        path=target,
        rel=os.path.relpath(target, root),
        kind="imported",
        directory=os.path.relpath(os.path.dirname(target), root),
    )
    imported.append(sub_file)
    for sub_ref in find_imports(sub_text):
        _check_ref(
            sub_file, sub_ref, root, read, issues, visited, imported,
            chain=chain + (target,), depth=depth + 1,
        )


def _unreadable(rule_file: RuleFile, where: str, ref: ImportRef, exc: OSError) -> Issue:
    return Issue(
        code="UNREADABLE_FILE",
        severity="warning",
        file=rule_file.rel,
        message="Could not read @import at %s ('@%s'): %s" % (where, ref.raw, exc),
        fix="Make sure the imported path is a readable regular UTF-8 text file.",
    )

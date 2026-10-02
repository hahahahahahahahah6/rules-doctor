"""Discovery of rule files in a project directory."""

from __future__ import annotations

import os
from typing import Callable, List

from .models import RuleFile

# File names rules-doctor understands, mapped to their kind.
RULE_FILENAMES = {
    "CLAUDE.md": "claude_md",
    "CLAUDE.local.md": "claude_local_md",
    "AGENTS.md": "agents_md",
}

# Directories that are project config rather than rule files, but worth noting.
CONFIG_DIRNAMES = {
    ".claude": "claude_dir",
}

# Rule files belonging to *other* agent ecosystems. Informational only:
# rules-doctor does not simulate their loaders.
OTHER_RULE_FILES = {
    ".cursorrules": "cursorrules",
    ".github/copilot-instructions.md": "copilot_instructions",
    ".aider.conf.yml": "aider_conf",
    ".muserules": "muse_rules",
}
OTHER_RULE_DIRS = {
    ".cursor/rules": "cursor_rules",
    ".muse/rules": "windsurf_rules",
    ".github/instructions": "copilot_instructions_dir",
}

# Directories never descended into during discovery.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    "dist",
    "build",
    ".eggs",
}


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def discover(root: str, read: Callable[[str], str] = _read_text) -> List[RuleFile]:
    """Walk *root* and return every recognized rule/config file.

    ``directory`` is the containing directory relative to *root*
    ("" means the project root itself).
    """
    root = os.path.abspath(root)
    found: List[RuleFile] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories we never want to descend into.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        for name in filenames:
            kind = RULE_FILENAMES.get(name)
            if kind is None:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            try:
                text = read(full)
            except OSError:
                text = ""
            found.append(
                RuleFile(
                    path=full,
                    rel=rel,
                    kind=kind,
                    directory=rel_dir,
                    size_bytes=len(text.encode("utf-8", "replace")),
                    lines=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
                )
            )

        for name in list(dirnames):
            if name in CONFIG_DIRNAMES:
                full = os.path.join(dirpath, name)
                found.append(
                    RuleFile(
                        path=full,
                        rel=os.path.relpath(full, root),
                        kind=CONFIG_DIRNAMES[name],
                        directory=rel_dir,
                    )
                )
            # Other-ecosystem rule dirs are informational.
            rel_sub = os.path.join(rel_dir, name) if rel_dir else name
            if rel_sub in OTHER_RULE_DIRS or name in OTHER_RULE_DIRS:
                full = os.path.join(dirpath, name)
                found.append(
                    RuleFile(
                        path=full,
                        rel=os.path.relpath(full, root),
                        kind="other",
                        directory=rel_dir,
                    )
                )

    # Root-level "other" rule files (checked directly, not via walk).
    for rel_path in OTHER_RULE_FILES:
        full = os.path.join(root, rel_path)
        if os.path.isfile(full):
            found.append(
                RuleFile(
                    path=full,
                    rel=rel_path,
                    kind="other",
                    directory=os.path.dirname(rel_path),
                )
            )

    # Deterministic order: project root first, then alphabetical.
    def sort_key(rf: RuleFile):
        return (rf.directory != "", rf.rel)

    found.sort(key=sort_key)
    return found


def loaded_files(files: List[RuleFile]) -> List[RuleFile]:
    """Rule files that (per the simulated loader) actually get loaded.

    A shadowed AGENTS.md is *not* loaded; everything else is.
    """
    shadowed = set()
    by_dir = {}
    for rf in files:
        by_dir.setdefault(rf.directory, []).append(rf)
    for directory, group in by_dir.items():
        kinds = {rf.kind for rf in group}
        if "claude_md" in kinds and "agents_md" in kinds:
            for rf in group:
                if rf.kind == "agents_md":
                    shadowed.add(rf.rel)
    return [rf for rf in files if rf.rel not in shadowed and rf.kind in (
        "claude_md",
        "claude_local_md",
        "agents_md",
    )]

"""Shadowing checks: which rule files actually get loaded.

Simulated loader model (heuristic -- see README "Honest limitations"):

* ``CLAUDE.md`` in a directory is the primary rule file for that scope.
* ``AGENTS.md`` is a *fallback*: it is only read when no ``CLAUDE.md``
  exists in the same directory. A stray ``CLAUDE.md`` next to it silently
  disables it.
* ``CLAUDE.local.md`` is additive personal overrides, loaded alongside.
* Nested ``CLAUDE.md`` / ``AGENTS.md`` files outside the project root are
  only loaded when that subdirectory is the working directory -- otherwise
  they are stray files that confuse more than they help.
"""

from __future__ import annotations

from typing import List

from .models import Issue, RuleFile


def check_shadowing(files: List[RuleFile]) -> List[Issue]:
    issues: List[Issue] = []

    if not any(rf.kind in ("claude_md", "claude_local_md", "agents_md") for rf in files):
        issues.append(
            Issue(
                code="NO_RULE_FILES",
                severity="info",
                file="",
                message="No CLAUDE.md, CLAUDE.local.md, or AGENTS.md found anywhere "
                "in this project.",
                fix="If you want persistent project rules, add a CLAUDE.md at the "
                "project root describing conventions, commands, and gotchas.",
            )
        )
        # Keep examining the inventory: files for other ecosystems are still
        # useful findings even when no Claude-compatible rule file exists.

    by_dir = {}
    for rf in files:
        by_dir.setdefault(rf.directory, []).append(rf)

    root_kinds = {rf.kind for rf in by_dir.get("", [])}

    for directory, group in sorted(by_dir.items()):
        kinds = {rf.kind for rf in group}
        label = directory or "(project root)"

        # The headline case: CLAUDE.md shadows AGENTS.md in the same directory.
        if "claude_md" in kinds and "agents_md" in kinds:
            agents = next(rf for rf in group if rf.kind == "agents_md")
            issues.append(
                Issue(
                    code="SHADOWED_AGENTS_MD",
                    severity="error",
                    file=agents.rel,
                    message="%s: AGENTS.md is shadowed by CLAUDE.md -- when both "
                    "exist, only CLAUDE.md is loaded and AGENTS.md is silently "
                    "ignored." % label,
                    fix="Keep a single source of truth: merge the AGENTS.md rules "
                    "into CLAUDE.md (or vice versa) and delete the other file.",
                )
            )

        for rf in group:
            # Stray nested rule files.
            if directory and rf.kind == "claude_md":
                issues.append(
                    Issue(
                        code="STRAY_CLAUDE_MD",
                        severity="warning",
                        file=rf.rel,
                        message="%s: nested CLAUDE.md outside the project root. It is "
                        "only loaded when this subdirectory is the working "
                        "directory." % rf.rel,
                        fix="Move project-wide rules up to the root CLAUDE.md; keep "
                        "only genuinely directory-scoped rules here.",
                    )
                )
            if directory and rf.kind == "agents_md" and "claude_md" not in root_kinds:
                # A nested AGENTS.md while the root relies on AGENTS.md too.
                issues.append(
                    Issue(
                        code="STRAY_AGENTS_MD",
                        severity="warning",
                        file=rf.rel,
                        message="%s: nested AGENTS.md outside the project root. It is "
                        "only loaded when this subdirectory is the working "
                        "directory." % rf.rel,
                        fix="Consolidate shared rules into the root AGENTS.md and "
                        "keep only directory-scoped overrides here.",
                    )
                )
            if rf.kind == "claude_local_md":
                issues.append(
                    Issue(
                        code="LOCAL_OVERRIDES",
                        severity="info",
                        file=rf.rel,
                        message="%s: CLAUDE.local.md holds personal overrides loaded "
                        "alongside the project rules." % rf.rel,
                        fix="No action needed -- just remember these overrides are "
                        "yours alone and do not travel with the repo for teammates.",
                    )
                )
            if rf.kind == "other":
                issues.append(
                    Issue(
                        code="OTHER_AGENT_RULES",
                        severity="info",
                        file=rf.rel,
                        message="%s: rule file for another agent ecosystem. "
                        "rules-doctor does not simulate its loader." % rf.rel,
                        fix="No action needed. Consider mirroring shared conventions "
                        "into CLAUDE.md so every agent sees them.",
                    )
                )

    return issues

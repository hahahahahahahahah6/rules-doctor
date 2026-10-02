"""Tests for rule-file discovery."""

import os

from rules_doctor import scanner


def test_discovers_all_known_rule_files(proj):
    root, write = proj
    write("CLAUDE.md", "# rules")
    write("CLAUDE.local.md", "# local")
    write("AGENTS.md", "# agents")
    files = scanner.discover(str(root))
    kinds = {f.rel: f.kind for f in files}
    assert kinds["CLAUDE.md"] == "claude_md"
    assert kinds["CLAUDE.local.md"] == "claude_local_md"
    assert kinds["AGENTS.md"] == "agents_md"


def test_skips_ignored_directories(proj):
    root, write = proj
    write("node_modules/pkg/CLAUDE.md", "# nope")
    write(".git/CLAUDE.md", "# nope")
    write("CLAUDE.md", "# yes")
    files = scanner.discover(str(root))
    assert [f.rel for f in files] == ["CLAUDE.md"]


def test_nested_rule_files_record_directory(proj):
    root, write = proj
    write("docs/CLAUDE.md", "# nested")
    (files,) = [f for f in scanner.discover(str(root)) if f.kind == "claude_md"]
    assert files.directory == "docs"
    assert files.rel == os.path.join("docs", "CLAUDE.md")


def test_notes_claude_config_dir(proj):
    root, write = proj
    os.makedirs(str(root / ".claude" / "commands"), exist_ok=True)
    files = scanner.discover(str(root))
    kinds = [f.kind for f in files]
    assert "claude_dir" in kinds


def test_loaded_files_excludes_shadowed_agents_md(proj):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    files = scanner.discover(str(root))
    loaded = scanner.loaded_files(files)
    assert {f.kind for f in loaded} == {"claude_md"}


def test_loaded_files_keeps_agents_md_without_claude_md(proj):
    root, write = proj
    write("AGENTS.md", "# a")
    files = scanner.discover(str(root))
    loaded = scanner.loaded_files(files)
    assert {f.kind for f in loaded} == {"agents_md"}

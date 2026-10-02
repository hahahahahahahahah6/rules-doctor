"""Tests for shadowing checks."""

from rules_doctor import scanner, shadow


def _codes(issues):
    return {i.code for i in issues}


def test_claude_md_shadows_agents_md(proj):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert "SHADOWED_AGENTS_MD" in _codes(issues)
    err = next(i for i in issues if i.code == "SHADOWED_AGENTS_MD")
    assert err.severity == "error"
    assert err.file == "AGENTS.md"
    assert err.fix  # every issue carries a fix suggestion


def test_agents_md_alone_not_shadowed(proj):
    root, write = proj
    write("AGENTS.md", "# a")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert "SHADOWED_AGENTS_MD" not in _codes(issues)


def test_nested_claude_md_is_stray(proj):
    root, write = proj
    write("CLAUDE.md", "# root")
    write("docs/CLAUDE.md", "# nested")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert "STRAY_CLAUDE_MD" in _codes(issues)


def test_no_rule_files_info(proj):
    root, write = proj
    write("README.md", "# hi")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert "NO_RULE_FILES" in _codes(issues)


def test_claude_local_md_is_info(proj):
    root, write = proj
    write("CLAUDE.local.md", "# mine")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert "LOCAL_OVERRIDES" in _codes(issues)
    info = next(i for i in issues if i.code == "LOCAL_OVERRIDES")
    assert info.severity == "info"


def test_every_issue_has_a_fix(proj):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    write("docs/CLAUDE.md", "# nested")
    write("CLAUDE.local.md", "# local")
    issues = shadow.check_shadowing(scanner.discover(str(root)))
    assert issues, "expected some issues in this fixture"
    for issue in issues:
        assert issue.fix.strip(), "issue %s has no fix suggestion" % issue.code

"""Tests for @import expansion checks."""

from rules_doctor import imports
from rules_doctor.models import RuleFile


def _rule(root, rel):
    return RuleFile(
        path=str(root / rel), rel=rel, kind="claude_md", directory=""
    )


def _codes(issues):
    return {i.code for i in issues}


def test_dead_import_inside_fence(proj):
    root, write = proj
    write("CLAUDE.md", "```\n@rules/style.md\n```\n")
    write("rules/style.md", "# style")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "DEAD_IMPORT" in _codes(issues)
    assert all(i.severity == "warning" for i in issues if i.code == "DEAD_IMPORT")


def test_broken_import_missing_file(proj):
    root, write = proj
    write("CLAUDE.md", "@does/not-exist.md\n")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "BROKEN_IMPORT" in _codes(issues)
    assert any(i.severity == "error" for i in issues)


def test_valid_import_no_issues(proj):
    root, write = proj
    write("CLAUDE.md", "@rules/style.md\n")
    write("rules/style.md", "# style\n")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert issues == []


def test_import_of_directory_is_broken(proj):
    root, write = proj
    write("CLAUDE.md", "@rules\n")
    (root / "rules").mkdir()
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "BROKEN_IMPORT" in _codes(issues)


def _chain(proj, depth):
    """Build CLAUDE.md -> a1 -> a2 -> ... chain of *depth* hops."""
    root, write = proj
    prev = "CLAUDE.md"
    names = ["CLAUDE.md"] + ["a%d.md" % i for i in range(1, depth + 1)]
    for i, name in enumerate(names):
        nxt = names[i + 1] if i + 1 < len(names) else None
        write(name, ("@%s\n" % nxt) if nxt else "# leaf\n")
    return root


def test_four_hops_ok(proj):
    root = _chain(proj, 4)
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "IMPORT_TOO_DEEP" not in _codes(issues)


def test_five_hops_too_deep(proj):
    root = _chain(proj, 5)
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "IMPORT_TOO_DEEP" in _codes(issues)


def test_circular_import_detected(proj):
    root, write = proj
    write("CLAUDE.md", "@b.md\n")
    write("b.md", "@CLAUDE.md\n")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "CIRCULAR_IMPORT" in _codes(issues)


def test_import_escaping_root_warns(proj):
    root, write = proj
    outside = root.parent / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    write("CLAUDE.md", "@../outside.md\n")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "IMPORT_ESCAPES_ROOT" in _codes(issues)


def test_inline_mention_flagged_info(proj):
    root, write = proj
    write("CLAUDE.md", "See @rules/style.md for details.\n")
    write("rules/style.md", "# style\n")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "INLINE_IMPORT_UNCERTAIN" in _codes(issues)
    assert all(i.severity == "info" for i in issues if i.code == "INLINE_IMPORT_UNCERTAIN")


def test_import_inside_tilde_fence_is_dead(proj):
    root, write = proj
    write("CLAUDE.md", "~~~\n@rules/style.md\n~~~\n")
    write("rules/style.md", "# style")
    issues = imports.check_imports(_rule(root, "CLAUDE.md"), str(root))
    assert "DEAD_IMPORT" in _codes(issues)

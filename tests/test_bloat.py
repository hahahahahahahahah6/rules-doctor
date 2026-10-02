"""Tests for bloat heuristics."""

from rules_doctor import bloat
from rules_doctor.models import RuleFile


def _rule(root, rel):
    return RuleFile(path=str(root / rel), rel=rel, kind="claude_md", directory="")


def test_estimate_tokens_rule_of_thumb():
    assert bloat.estimate_tokens("a" * 400) == 100
    assert bloat.estimate_tokens("") == 0


def test_instruction_lines_ignores_fences_and_headings():
    text = (
        "# Title\n"
        "\n"
        "- do this\n"
        "- do that\n"
        "```\n"
        "- not an instruction, just code\n"
        "```\n"
        "---\n"
        "plain instruction line\n"
    )
    assert bloat.instruction_lines(text) == 3


def test_bloated_file_warns(proj):
    root, write = proj
    write("CLAUDE.md", "".join("- rule %d\n" % i for i in range(200)))
    issues = bloat.check_bloat([_rule(root, "CLAUDE.md")])
    assert any(i.code == "BLOATED_FILE" and i.severity == "warning" for i in issues)


def test_small_file_no_bloat(proj):
    root, write = proj
    write("CLAUDE.md", "- rule one\n- rule two\n")
    assert bloat.check_bloat([_rule(root, "CLAUDE.md")]) == []


def test_boundary_150_lines_ok(proj):
    root, write = proj
    write("CLAUDE.md", "".join("- rule %d\n" % i for i in range(150)))
    issues = bloat.check_bloat([_rule(root, "CLAUDE.md")])
    assert not any(i.code == "BLOATED_FILE" for i in issues)

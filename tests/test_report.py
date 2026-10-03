"""Tests for report assembly, scoring, and rendering."""

from rules_doctor import report


def test_grade_boundaries():
    assert report.grade_for(100) == "A"
    assert report.grade_for(90) == "A"
    assert report.grade_for(89) == "B"
    assert report.grade_for(75) == "B"
    assert report.grade_for(74) == "C"
    assert report.grade_for(60) == "C"
    assert report.grade_for(59) == "D"
    assert report.grade_for(40) == "D"
    assert report.grade_for(39) == "F"
    assert report.grade_for(0) == "F"


def test_score_math_one_error(proj):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")  # shadowed -> exactly one error
    rep = report.checkup(str(root))
    assert rep.score == 85
    assert rep.grade == "B"
    assert rep.stats["errors"] == 1


def test_score_floor_zero(proj):
    root, write = proj
    write("CLAUDE.md", "@missing.md\n")  # one broken import
    write("AGENTS.md", "# a")  # shadowed
    rep = report.checkup(str(root))
    assert rep.score == 70  # 100 - 15*2


def test_clean_project_scores_100(proj):
    root, write = proj
    write("CLAUDE.md", "# Conventions\n- Use ruff.\n")
    rep = report.checkup(str(root))
    assert rep.score == 100
    assert rep.grade == "A"
    assert rep.issues == []


def test_render_contains_sections(proj):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    text = report.render_text(report.checkup(str(root)))
    assert "rules-doctor report" in text
    assert "Score: 85/100 (B)" in text
    assert "Rule files found" in text
    assert "SHADOWED_AGENTS_MD" in text
    assert "Fix:" in text


def test_render_clean_project(proj):
    root, write = proj
    write("CLAUDE.md", "# c\n")
    text = report.render_text(report.checkup(str(root)))
    assert "No issues found" in text


def test_full_checkup_dead_import_and_bloat(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "```\n@rules/dead.md\n```\n"
        + "".join("- rule %d\n" % i for i in range(160)),
    )
    rep = report.checkup(str(root))
    codes = {i.code for i in rep.issues}
    assert "DEAD_IMPORT" in codes
    assert "BLOATED_FILE" in codes


def test_imported_file_is_loaded_and_counted_for_bloat(proj):
    root, write = proj
    write("CLAUDE.md", "@rules.md\n")
    write("rules.md", "\n".join("do thing %d" % n for n in range(151)))
    rep = report.checkup(str(root))
    assert rep.stats["files_loaded"] == 2
    assert any(f.rel == "rules.md" and f.kind == "imported" for f in rep.files)
    assert any(i.code == "BLOATED_FILE" and i.file == "rules.md" for i in rep.issues)


def test_nested_rule_is_not_analyzed_as_loaded(proj):
    root, write = proj
    write("CLAUDE.md", "# root\n")
    write("docs/CLAUDE.md", "@missing.md\n")
    rep = report.checkup(str(root))
    assert any(i.code == "STRAY_CLAUDE_MD" for i in rep.issues)
    assert not any(i.code == "BROKEN_IMPORT" and i.file == "docs/CLAUDE.md" for i in rep.issues)

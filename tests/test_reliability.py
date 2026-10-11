"""Tests for the v0.3 reliability rule set (ADR / scope-creep lint)."""

from rules_doctor import reliability, report, scanner


def _codes(issues):
    return {i.code for i in issues}


def _scoped_claude_md(n_rules=12):
    lines = ["# Project rules\n"]
    lines += ["- Directive number %d: keep the build green.\n" % i for i in range(n_rules)]
    return "".join(lines)


# ---- SCOPE_BOUNDARY_MISSING -------------------------------------------------


def test_scope_creep_detected_without_boundary(proj):
    root, write = proj
    write("CLAUDE.md", _scoped_claude_md())
    rep = report.checkup(str(root))
    assert "SCOPE_BOUNDARY_MISSING" in _codes(rep.issues)
    hit = [i for i in rep.issues if i.code == "SCOPE_BOUNDARY_MISSING"][0]
    assert hit.severity == "warning"
    assert hit.file == "CLAUDE.md"


def test_scope_boundary_section_header_passes(proj):
    root, write = proj
    content = _scoped_claude_md() + "\n## Scope\n\nOnly edit files under src/.\n"
    write("CLAUDE.md", content)
    rep = report.checkup(str(root))
    assert "SCOPE_BOUNDARY_MISSING" not in _codes(rep.issues)


def test_scope_boundary_directive_passes(proj):
    root, write = proj
    content = _scoped_claude_md() + "\n- Never modify files under migrations/.\n"
    write("CLAUDE.md", content)
    rep = report.checkup(str(root))
    assert "SCOPE_BOUNDARY_MISSING" not in _codes(rep.issues)


def test_tiny_rule_file_exempt_from_scope(proj):
    root, write = proj
    write("CLAUDE.md", "# Conventions\n- Use ruff.\n")
    rf = scanner.discover(str(root))[0]
    issues = reliability.check_scope_boundary([rf], lambda p: open(p).read())
    assert issues == []


def test_cursorrules_gets_scope_check(proj):
    root, write = proj
    write(".cursorrules", _scoped_claude_md())
    rep = report.checkup(str(root))
    assert "SCOPE_BOUNDARY_MISSING" in _codes(rep.issues)


# ---- CONTRADICTORY_RULES ----------------------------------------------------


def test_contradiction_detected(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\nOnly edit files under src/.\n\n"
        "# Testing\n\n"
        "- Always run the full test suite after changing code.\n"
        "- Never run the full test suite -- it is too slow.\n",
    )
    rep = report.checkup(str(root))
    assert "CONTRADICTORY_RULES" in _codes(rep.issues)
    hit = [i for i in rep.issues if i.code == "CONTRADICTORY_RULES"][0]
    assert hit.severity == "error"


def test_consistent_rules_no_contradiction(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\nOnly edit files under src/.\n\n"
        "# Testing\n\n"
        "- Always run the full test suite after changing code.\n"
        "- Fix every failing test before committing.\n",
    )
    rep = report.checkup(str(root))
    assert "CONTRADICTORY_RULES" not in _codes(rep.issues)


def test_unrelated_negations_do_not_collide(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\nOnly edit files under src/.\n\n"
        "- Always run tests before committing.\n"
        "- Never commit directly to the main branch.\n",
    )
    rep = report.checkup(str(root))
    assert "CONTRADICTORY_RULES" not in _codes(rep.issues)


# ---- VAGUE_DIRECTIVE --------------------------------------------------------


def test_vague_directive_detected(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\nOnly edit files under src/.\n\n"
        "# Style\n\n"
        "- Refactor the code as needed.\n"
        "- Remember to update the changelog.\n",
    )
    rep = report.checkup(str(root))
    assert "VAGUE_DIRECTIVE" in _codes(rep.issues)
    hits = [i for i in rep.issues if i.code == "VAGUE_DIRECTIVE"]
    assert len(hits) == 2
    assert hits[0].severity == "warning"


def test_concrete_directives_pass(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\nOnly edit files under src/.\n\n"
        "# Style\n\n"
        "- Run `ruff check` before every commit.\n"
        "- Update CHANGELOG.md under 'Unreleased' for user-facing changes.\n",
    )
    rep = report.checkup(str(root))
    assert "VAGUE_DIRECTIVE" not in _codes(rep.issues)


# ---- ADR_MISSING ------------------------------------------------------------


def test_adr_missing_detected_for_nontrivial_project(proj):
    root, write = proj
    write("CLAUDE.md", "## Scope\n\nOnly edit files under src/.\n")
    for i in range(6):
        write("src/mod%d.py" % i, "# module %d\n" % i)
    rep = report.checkup(str(root))
    assert "ADR_MISSING" in _codes(rep.issues)
    hit = [i for i in rep.issues if i.code == "ADR_MISSING"][0]
    assert hit.severity == "warning"
    assert hit.file == ""


def test_adr_present_passes(proj):
    root, write = proj
    write("CLAUDE.md", "## Scope\n\nOnly edit files under src/.\n")
    for i in range(6):
        write("src/mod%d.py" % i, "# module %d\n" % i)
    write("docs/adr/0001-record-architecture-decisions.md", "# 1. Record ADRs\n")
    rep = report.checkup(str(root))
    assert "ADR_MISSING" not in _codes(rep.issues)


def test_trivial_project_exempt_from_adr(proj):
    root, write = proj
    write("CLAUDE.md", "## Scope\n\nOnly edit files under src/.\n")
    rep = report.checkup(str(root))
    assert "ADR_MISSING" not in _codes(rep.issues)


# ---- clean pass -------------------------------------------------------------


def test_clean_project_passes_all_v03_checks(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        "## Scope\n\n"
        "Only edit files under src/. Never touch migrations/ or lock files.\n\n"
        "# Testing\n\n"
        "- Always run the full test suite after changing code.\n"
        "- Fix every failing test before committing.\n\n"
        "# Style\n\n"
        "- Run `ruff check` before every commit.\n",
    )
    for i in range(6):
        write("src/mod%d.py" % i, "# module %d\n" % i)
    write("docs/adr/0001-record-architecture-decisions.md", "# 1. Record ADRs\n")
    rep = report.checkup(str(root))
    assert rep.issues == []
    assert rep.score == 100
    assert rep.grade == "A"


def test_v03_score_penalty_math(proj):
    root, write = proj
    write(
        "CLAUDE.md",
        _scoped_claude_md()
        + "- Always run the full test suite after changing code.\n"
        + "- Never run the full test suite -- it is too slow.\n",
    )
    for i in range(6):
        write("src/mod%d.py" % i, "# module %d\n" % i)
    rep = report.checkup(str(root))
    # 1 error (contradiction) + 2 warnings (scope, adr) = 100 - 15 - 10
    assert rep.stats["errors"] == 1
    assert rep.stats["warnings"] == 2
    assert rep.score == 75

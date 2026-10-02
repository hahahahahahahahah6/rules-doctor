"""Tests for the CLI."""

from rules_doctor import cli


def test_version(capsys):
    import pytest

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "rules-doctor" in out


def test_bad_path_exits_2(capsys):
    assert cli.main(["/does/not/exist-xyz"]) == 2


def test_default_exit_zero_with_errors(proj, capsys):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    assert cli.main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "Score:" in out


def test_fail_on_error(proj, capsys):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")  # shadowed -> error
    assert cli.main([str(root), "--fail-on", "error"]) == 1


def test_fail_on_error_clean_project(proj, capsys):
    root, write = proj
    write("CLAUDE.md", "# c\n")
    assert cli.main([str(root), "--fail-on", "error"]) == 0


def test_fail_on_warning(proj, capsys):
    root, write = proj
    content = "```\n@x.md\n```\n"  # dead import -> warning only
    write("CLAUDE.md", content)
    assert cli.main([str(root), "--fail-on", "warning"]) == 1
    assert cli.main([str(root), "--fail-on", "error"]) == 0


def test_quiet_drops_file_list(proj, capsys):
    root, write = proj
    write("CLAUDE.md", "# c")
    write("AGENTS.md", "# a")
    assert cli.main([str(root), "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "Rule files found" not in out
    assert "Score:" in out
    assert "SHADOWED_AGENTS_MD" in out

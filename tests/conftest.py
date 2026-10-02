"""Shared fixtures for rules-doctor tests."""

import os

import pytest


@pytest.fixture
def proj(tmp_path):
    """A fresh empty project directory with a write helper."""

    def write(rel, content=""):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)

    return tmp_path, write


def codes(report):
    return {i.code for i in report.issues}

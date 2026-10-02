"""Command-line interface for rules-doctor."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .report import checkup, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rules-doctor",
        description="Health-check your CLAUDE.md / AGENTS.md rule files: "
        "finds dead @imports, shadowed files, and instruction bloat.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to check (default: current directory).",
    )
    parser.add_argument(
        "--fail-on",
        choices=["never", "warning", "error"],
        default="never",
        help="Exit non-zero if issues at or above this severity are found "
        "(default: never -- report only).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only print the score line and issues, skip the file list.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="rules-doctor %s" % __version__,
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print("rules-doctor: not a directory: %s" % args.path, file=sys.stderr)
        return 2

    report = checkup(root)
    text = render_text(report)
    if args.quiet:
        # Keep the header, score, and issues; drop the file inventory.
        lines = text.splitlines()
        keep = []
        in_files = False
        for line in lines:
            if line.startswith("Rule files found"):
                in_files = True
                continue
            if in_files and line == "":
                in_files = False
                continue
            if not in_files:
                keep.append(line)
        text = "\n".join(keep) + "\n"
    print(text, end="")

    if args.fail_on == "error" and report.by_severity("error"):
        return 1
    if args.fail_on == "warning" and (
        report.by_severity("error") or report.by_severity("warning")
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

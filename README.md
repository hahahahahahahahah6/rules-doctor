# rules-doctor

A check-up for your `CLAUDE.md` / `AGENTS.md` rule files. It statically simulates
how Claude Code loads project rules and reports the silent failures that waste
your context window:

- **Dead `@import`s** — an `@import` written inside a fenced code block is
  rendered as literal text and never expanded. Neither is one pointing at a
  file that doesn't exist.
- **Shadowed files** — when `CLAUDE.md` and `AGENTS.md` sit in the same
  directory, only `CLAUDE.md` is loaded. Your `AGENTS.md` is silently ignored.
- **Instruction bloat** — past ~150 instruction lines, models start dropping
  or deprioritizing rules. rules-doctor tells you when you've crossed the line.

Zero dependencies. Pure standard library.

## Install

```bash
pip install rules-doctor
```

## Usage

```bash
# Check the current project
rules-doctor

# Check another directory
rules-doctor ~/my-project

# CI mode: exit 1 if any errors (or warnings) are found
rules-doctor --fail-on error

# Compact output
rules-doctor --quiet
```

Example output:

```
rules-doctor report: /home/hao/my-project
Score: 70/100 (C)

Rule files found (2, 1 loaded):
  - CLAUDE.md [project root] -- PRIMARY -- loaded by Claude Code
  - AGENTS.md [project root] -- fallback -- loaded only if no CLAUDE.md nearby

Issues (2):

[ERROR] SHADOWED_AGENTS_MD -- AGENTS.md
  (project root): AGENTS.md is shadowed by CLAUDE.md -- when both exist,
  only CLAUDE.md is loaded and AGENTS.md is silently ignored.
  Fix: Keep a single source of truth: merge the AGENTS.md rules into
  CLAUDE.md (or vice versa) and delete the other file.

[WARN] DEAD_IMPORT -- CLAUDE.md
  Dead @import at CLAUDE.md:42: '@rules/deploy.md' sits inside a fenced
  code block, so it is rendered as literal text and never expanded.
  Fix: Move the import out of the code fence onto its own line, e.g.
  `@rules/deploy.md` with no surrounding backticks.
```

## What it checks

| Check | Severity | What it means |
|---|---|---|
| `SHADOWED_AGENTS_MD` | error | `AGENTS.md` next to a `CLAUDE.md` is never loaded |
| `BROKEN_IMPORT` | error | `@import` points to a missing file or a directory |
| `IMPORT_TOO_DEEP` | error | Import chain nested deeper than 4 hops (deeper ones are dropped) |
| `CIRCULAR_IMPORT` | error | Import chain loops back on itself |
| `DEAD_IMPORT` | warning | `@import` inside a fenced code block — silently ignored |
| `IMPORT_ESCAPES_ROOT` | warning | `@import` with `..` leaves the project |
| `BLOATED_FILE` | warning | More than ~150 instruction lines in one file |
| `BLOATED_TOTAL` | warning | All loaded rules exceed ~8000 estimated tokens |
| `STRAY_CLAUDE_MD` / `STRAY_AGENTS_MD` | warning | Nested rule file outside the project root |
| `INLINE_IMPORT_UNCERTAIN` | info | Mid-line `@mention` may not expand like a directive line |
| `LOCAL_OVERRIDES` | info | `CLAUDE.local.md` personal overrides noted |
| `NO_RULE_FILES` | info | No rule files found at all |

Scoring: start at 100, −15 per error, −5 per warning, floor of 0.
Grades: A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 40, F < 40.

## Honest limitations

This tool is a **static heuristic simulation, not the Claude Code loader**.
Anthropic does not publish the exact rule-loading algorithm, and it changes
between versions. Concretely, this means:

- **The shadowing model is inferred from observed behavior** (e.g. reports
  that Claude Code ignores `AGENTS.md` when `CLAUDE.md` exists), not from
  official documentation. If Anthropic changes precedence, reports can be
  wrong in either direction — false alarms or missed shadows.
- **`@import` semantics are approximated.** The 4-hop nesting limit, fence
  handling, and inline-mention behavior are best-effort guesses. Edge cases
  (quoted paths, fragments like `@file.md#section`, symlinks) may be
  misclassified.
- **Token counts are `len(text) // 4`**, a rough rule of thumb for English
  prose. Code, URLs, and CJK text tokenize very differently.
- **The ~150 instruction-line limit is a heuristic**, not a measured cliff.
  Model attention degrades gradually; your mileage varies by model version.
- **Only Markdown-style rule files are understood.** `.claude/` project
  config (settings, hooks, skills) is noted but not validated.

When a finding looks suspicious, verify against the real Claude Code
(`--debug` shows what was actually loaded). Bug reports with a minimal
repro are welcome — that's how the heuristics get better.

## Development

```bash
pip install pytest
python -m pytest tests/ -q
```

## License

MIT — see [LICENSE](LICENSE).

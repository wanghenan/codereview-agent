---
name: code-review
description: Review a diff, branch, or pull request and report evidence-anchored findings ranked by blast radius. Use when asked to review code, a PR, a branch, or uncommitted changes, or to judge whether a change is safe to merge.
---

# Evidence-Anchored Code Review

A review is only as trustworthy as the evidence behind each finding. Every
finding produced by this skill cites a line that the diff actually changed.

## The one rule

**No line, no finding.** If you cannot point at a changed line, you are not
reviewing the change — you are describing the codebase. The observation may be
true and still be noise, and that noise is what makes generated reviews
untrustworthy.

## Workflow

1. **Get the diff.** `git diff <base>...HEAD` for a branch, `gh pr diff <n>` for
   a PR, `git diff` for unstaged work. Read the diff before opening any file.
2. **Read the changed hunks** plus enough context to judge them: the enclosing
   function, the type, the call sites. Do not review code the diff did not touch.
3. **Write each candidate as one line**: `path:line — claim — the changed line
   that proves it`. If you cannot fill the third part, the candidate is a guess.
   Drop it.
4. **Self-filter** using the admission rules in [REFERENCE.md](REFERENCE.md).
   Expect to discard about half of what you found.
5. **Stratify** each survivor: `defect` (wrong behaviour), `design` (right
   behaviour, wrong shape), `nit` (taste). One stratum per finding, no hedging.
6. **Report** — or report nothing. "No findings" is a valid and useful answer
   when you say what you checked.

## Output format

| file:line | stratum | finding | evidence |
| --- | --- | --- | --- |

Under the table, at most three sentences on what you did **not** check: files
skipped, behaviour not executed, tests not run.

Hard limits:

- **Five findings maximum.** More than five means you drifted into style — keep
  the top five by blast radius.
- **No line number, no row.**
- **Never assert runtime behaviour you did not execute or read.** "This breaks
  X" requires naming the code path that breaks.
- **Do not restate the diff.** The reader already has it.

## Escalate to the engine

Hand off to the `codereview` CLI when the diff exceeds roughly 400 lines, needs
cross-file symbol resolution, must post inline comments on a GitHub PR, or must
run unattended in CI:

```bash
pip install codereview-agent
codereview --base-branch main --offline --json   # no network; findings on stdout
codereview --list-rules                          # the 30 deterministic rules
```

The CLI anchors every finding to a changed line and drops findings that fall
outside the diff — the same contract this skill asks you to keep by hand, a
little more reliably.

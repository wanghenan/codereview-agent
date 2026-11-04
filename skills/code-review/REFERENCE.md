# Reference: strata, admission rules, and known failure modes

Load this when a review has more than a handful of candidates, or when a
finding's stratum is contested.

## Strata

Pick one. The stratum is a claim about the *kind* of problem, not its severity.

| stratum | meaning | test | example |
| --- | --- | --- | --- |
| `defect` | The change does the wrong thing, or stops the wrong thing from happening. | Can you name an input or state where the new code misbehaves? | A retry loop retries a 401 forever. |
| `design` | Behaviour is correct; the shape makes the next change harder or the failure mode worse. | Would a competent maintainer accept the behaviour but want the structure changed? | Auth failures are classified inside the retry loop instead of in one place. |
| `nit` | Preference. The code is right by any standard that matters. | Would two reviewers disagree, and does it matter? | `_is_retryable` reads better as `_is_retryable_error`. |

Severity is a **separate** axis and belongs in prose, not in the stratum. A
`defect` can be cosmetic; a `design` finding can be release-blocking.

## Admission rules

A finding is admitted only if all four hold.

1. **Anchored.** The cited line is part of the diff — a `+` line, or the
   surrounding context of a changed hunk. For a newly added file, any line.
2. **Caused or exposed by this diff.** Pre-existing problems in untouched code
   are not this review's business unless the change makes them live.
3. **Actionable.** There is a specific change that fixes it. "Consider
   refactoring this module" fails; "move the auth check above the retry" passes.
4. **Not a preference the repo already answered.** Check `AGENTS.md`,
   `pyproject.toml`, and nearby code for the house style before calling it a
   problem.

Drop the finding, not the rule, when in doubt: an unanchored finding costs the
reader more than a missed nit.

## Why the filter is aggressive

Measured on 20 real pull requests from this repository, with a judging model
allowed to read the full diff:

| measure | value |
| --- | --- |
| Candidate hit: same file, line within ±3 | 12/20 |
| Semantic agreement: same concern, any line | 5/20 |
| Candidate rate overstating semantic agreement | ≈ 2.4× |

Moving the line tolerance alone moved the candidate rate from 8/20 (±0) to
19/20 (±30). In other words, most of what a line-based match calls a hit is
**anchor drift**, not agreement. A reviewer that reports everything it notices
will look right on a per-line metric and be wrong about the code.

Two practical consequences:

- **Anchor precision is the product.** Reviewers do not punish a missed nit;
  they punish findings that point at the wrong line.
- **Empty is allowed.** On a clean diff, "no findings" plus what you checked is a
  better answer than three speculative ones.

## Worked examples

**Admitted — defect, anchored**

```
Review failed for aiohttp/client.py (auth, not retried)
```

The diff introduced per-failure-kind classification. A 401 will never succeed on
retry, so retrying it burns quota. Evidence: the changed line that maps status →
kind, and the loop that consumes it. Fix is local.

**Rejected — unanchored**

> The error handling in `client.py` could be more robust.

No line, no failing input, no fix. This is the shape of finding that inflates a
candidate rate while telling the reader nothing.

**Rejected — out of scope**

> `helpers.py` has a race condition.

`helpers.py` is not in the diff. Unless the change makes that race reachable, it
belongs in its own issue.

## Anti-patterns

- **Restating the diff** as findings ("this adds a retry loop").
- **Severity theatre**: labelling style as `defect` to justify reporting it.
- **Hedged claims**: "might potentially cause issues" — commit to a claim or drop it.
- **Invented test results.** Never state that tests pass without running them.

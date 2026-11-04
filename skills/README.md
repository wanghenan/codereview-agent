# Agent skills

Portable `SKILL.md` bundles that teach a coding agent how to use this project's
review contract without running the CLI.

| skill | what it does |
| --- | --- |
| [`code-review/`](code-review/SKILL.md) | Reviews a diff with evidence-anchored findings, a five-finding cap, and an admission filter; escalates to the `codereview` CLI when a change is too large to review by hand. |

## Install

Claude Code — this repository is also a plugin marketplace
(`.claude-plugin/marketplace.json`), so there is nothing to copy:

```bash
/plugin marketplace add wanghenan/codereview-agent
/plugin install code-review@codereview-agent
```

That registers the skill as `code-review:code-review`. Verified with Claude Code
2.1.266: one skill, ~61 tokens always-on, ~620 on invoke.

Claude Code, by copying instead — project-local:

```bash
mkdir -p .claude/skills
cp -r path/to/crAgent/skills/code-review .claude/skills/
```

Personal, available in every project:

```bash
mkdir -p ~/.claude/skills
cp -r path/to/crAgent/skills/code-review ~/.claude/skills/
```

Any other agent (Cursor, Copilot, Codex, Gemini CLI) that reads a rules or
context file: copy the body of `SKILL.md` — everything below the `---`
frontmatter — into that agent's file (`.cursor/rules/`,
`.github/copilot-instructions.md`, `AGENTS.md`), and keep `REFERENCE.md` beside
it if the agent can read files on demand.

If your agent's skill path differs, the frontmatter is the only part that needs
adapting: `name` and `description` are what the agent matches on.

## Why these live here

The skill is a **manual fallback**, not a product. It encodes the same contract
the Python engine enforces mechanically:

- a finding must anchor to a line the diff changed,
- findings outside the diff are dropped, not downgraded,
- "no findings" is a legitimate result.

Anything the engine can do — 30 deterministic rules, cross-file symbol
resolution, inline PR comments, CI gating — the CLI does better, and the skill
says so. What the skill adds is coverage in agents that cannot install a Python
package: it turns the review discipline into instructions instead of code.

Distribution is deliberately self-hosted. Paid skill marketplaces take a cut and
serve the bundle behind a connector that the buyer cannot inspect; a review tool
whose whole argument is *verifiable evidence* should not ship as an
uninspectable black box. The files are MIT, same as the rest of the repo.

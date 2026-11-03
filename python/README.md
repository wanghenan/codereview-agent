# codereview-agent

AI code review for pull requests. An LLM reads the diff, every finding is
anchored to the lines that actually changed, and the result is posted as inline
GitHub review comments.

- **Evidence-anchored findings** — a comment quotes the code it is about, so a
  drifting line number is visible instead of silent.
- **Diff-scoped** — comments and linter findings are limited to changed lines; a
  one-line change does not drag in the file's existing backlog.
- **Admission filter** — low-confidence findings are dropped before they reach
  the PR, and team dismissals are remembered.
- **Cross-file context** — a symbol index finds callers of a changed signature
  and puts them in the prompt.

## Install

```bash
pip install "git+https://github.com/wanghenan/codereview-agent.git@v1#subdirectory=python"
```

## Configure

```yaml
# .codereview-agent.yaml
llm:
  provider: opencode-go        # or openai / anthropic / deepseek / zhipu / qwen / minimax
  apiKey: ${LLM_API_KEY}
```

`opencode-go` defaults to `deepseek-v4.1-flash`. Official providers need only
`provider` and `apiKey`; see
[docs/configuration.md](https://github.com/wanghenan/codereview-agent/blob/main/docs/configuration.md)
for the full reference.

## Review a diff

```bash
codereview --diff '{"files": [...]}' --offline   # print the review, post nothing
codereview --pr 123                              # review a real PR
```

`codereview --help` lists the rest. The repository README
(https://github.com/wanghenan/codereview-agent#readme) covers the GitHub Action,
the benchmark corpus and the design notes.

## License

MIT

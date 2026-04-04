# CodeReview Agent 综合改进计划

## TL;DR

> **Quick Summary**: 从高频用户视角出发，分6个维度全面改进 CodeReview Agent —— CLI体验、配置灵活化、错误处理、进度反馈、测试覆盖、高级功能。采用分层推进策略，TDD开发，tqdm进度条。
> 
> **Deliverables**:
> - 修复确认Bug (cli.py:491)
> - 修复347个lint错误
> - 新增CLI标志: --version, --verbose, --quiet, --log-level, --list-rules, --disable-rule, --clear-cache
> - 核心参数全部可配置化 (max_concurrency, timeout, cache路径, 模型列表等)
> - 消除所有静默失败，错误消息附带完整上下文
> - 缓存原子化写入 + --clear-cache 命令
> - tqdm进度条 + ETA + 当前文件提示
> - 核心模块测试覆盖从45%提升到>80%
> - LLM Provider fallback链
> - Rate Limit检测与自动退避
> - 交互式fix选择模式
> 
> **Estimated Effort**: XL (6个维度，~20个任务)
> **Parallel Execution**: YES - 6 waves
> **Critical Path**: Task1-3(Wave1) → Task4-6(Wave2) → Task7-9(Wave3) → Task10-13(Wave4) → Task14-16(Wave5) → Task17-18(Wave6) → F1-F4(Final)

---

## Context

### Original Request
用户作为项目的忠实高频使用者，从使用者角度分析项目原代码还有什么功能需要改进优化。经过全面探索和讨论，确定6个改进维度。

### Interview Summary
**Key Discussions**:
- CLI体验: 缺少 --version, --verbose/--quiet, --list-rules, --disable-rule, --clear-cache 等基本标志
- 配置灵活化: max_concurrency=5, timeout_seconds=30.0, cache路径, LLM默认模型, 输出时间戳 全部硬编码
- 错误处理: get_git_diff()失败静默返回空字符串、JSON解析失败只debug日志、GitHub API错误静默返回空列表、项目分析失败静默创建"unknown"上下文
- 进度反馈: 长时间review(50+文件)无进度条、无ETA、无当前文件提示
- 测试覆盖: 约45%，核心模块(llm.py, config.py, github_client.py, reviewer.py, analyzer.py, models/)零测试
- 高级功能: 无LLM fallback链、无Rate Limit处理、fix命令全有或全无

**Confirmed Bug**: `cli.py:491` — `preview.get("files", []) > 5` 缺少 `len()`

**User Decisions**:
- 策略: TDD (Red→Green→Refactor)
- 节奏: 分层推进 (CLI→Config→错误处理→进度→测试→高级功能)
- 进度条: tqdm
- 范围: 全部6个维度

### Research Findings
- **项目技术栈**: Python 3.9+, LangGraph, 6个LLM Provider (OpenAI/Anthropic/Zhipu/MiniMax/Qwen/DeepSeek)
- **CLI**: 3个子命令 review/fix/merge, 主入口1264行
- **规则引擎**: 22条OWASP通用 + 3条Python + 3条JS + 2条Java = 30条规则, YAML定义, 但无法禁用单条
- **缓存**: 双层(项目上下文 + 文件review), 非原子写入, 文件名可能冲突
- **Lint**: 347个ruff错误 (~100 import排序, ~100 Optional vs |, 多处unused import, 149个LSP类型错误)
- **测试**: 201个测试可收集, 1个收集错误(matplotlib缺失)

### Metis Review
**Identified Gaps** (addressed):
- Python版本: README说3.10+但环境有3.9 → 按3.9兼容处理, 使用Optional[X]而非X | None
- 缓存迁移: 新配置不应破坏现有缓存 → 保留默认路径, 新增可选配置
- tqdm在CI兼容性 → 支持TQDM_DISABLE环境变量
- --verbose和--quiet同时指定 → 后者覆盖前者
- 交互式fix UI → y/n/a (yes/no/all) 每文件询问
- --disable-rule按ID禁用 → 支持精确ID匹配
- 347个lint必须先修再改功能 → Wave1先行修复
- matplotlib缺失导致测试收集失败 → 添加到dev依赖

---

## Work Objectives

### Core Objective
从忠实用户的视角出发，系统性解决CodeReview Agent的6大痛点，将产品体验从"能用"提升到"好用"。

### Concrete Deliverables
- **Wave 1**: Bug修复 + Lint清理 + 测试基础设施修复 (3 tasks)
- **Wave 2**: CLI标志扩展 + 配置灵活化 + 错误处理改进 (3 tasks)
- **Wave 3**: 进度反馈 + 日志控制 + 规则管理 (3 tasks)
- **Wave 4**: 核心模块测试覆盖 (4 tasks)
- **Wave 5**: 高级功能 - fallback/rate-limit/交互fix (3 tasks)
- **Wave 6**: 最终Lint清理 + 代码质量收尾 (2 tasks)

### Definition of Done
- [ ] `ruff check python/src/` 零错误
- [ ] `pytest python/tests/ -v` 全部通过
- [ ] `python -m codereview.cli --version` 正确输出
- [ ] `python -m codereview.cli --list-rules` 列出30条规则
- [ ] `python -m codereview.cli --disable-rule OWASP-A01-001` 正常工作
- [ ] 核心模块测试覆盖 >80%
- [ ] 所有静默失败已修复为明确错误

### Must Have
- 修复cli.py:491确认Bug
- --version标志
- --verbose/--quiet/--log-level日志控制
- --list-rules列出所有规则
- --disable-rule禁用特定规则
- --clear-cache清除缓存
- max_concurrency可配置
- timeout_seconds可配置
- cache路径可配置
- LLM默认模型可配置
- 消除get_git_diff()静默失败
- 消除JSON解析静默失败
- 消除GitHub API静默失败
- 缓存原子化写入
- tqdm进度条
- LLM Provider fallback链
- Rate Limit检测与退避
- 交互式fix选择

### Must NOT Have (Guardrails)
- ❌ 不改变现有CLI flag行为（向后兼容）
- ❌ 不破坏现有缓存格式（保持读取兼容）
- ❌ 不添加新LLM Provider（仅优化现有6个）
- ❌ 不添加TUI/图形界面（纯CLI）
- ❌ 不添加多仓库分析能力
- ❌ 不添加代码解释生成
- ❌ 不使用bare except: 子句
- ❌ 不添加非Pydantic配置验证
- ❌ AI slop: 不要过度注释、不要过度抽象、不要泛型命名(data/result/item)
- ❌ 不要在现有flag行为上做breaking change
- ❌ tqdm只用于用户可见进度，不污染library日志

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: TDD (Red→Green→Refactor)
- **Framework**: pytest + pytest-asyncio + pytest-cov
- **TDD Flow**: 每个功能先写失败测试 → 最小实现 → 重构

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CLI flags**: Use Bash (subprocess) — Run command, capture output, assert exit code + content
- **Config/Models**: Use Bash (pytest) — Run tests, assert coverage thresholds
- **Error handling**: Use Bash (pytest) — Mock failures, verify error messages
- **Progress bars**: Use Bash (TQDM_DISABLE=0) — Capture stderr, verify progress output
- **LLM/Fallback**: Use Bash (pytest + mock) — Mock provider failures, verify fallback

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — 基础修复 + 清理):
├── Task 1: 修复确认Bug cli.py:491 [quick]
├── Task 2: Lint自动修复 (ruff --fix) [quick]
└── Task 3: 修复测试收集 + 添加tqdm依赖 [quick]

Wave 2 (After Wave 1 — CLI + 配置 + 错误处理):
├── Task 4: CLI标志扩展 (--version, --clear-cache, --log-level) [deep]
├── Task 5: 配置灵活化 (max_concurrency, timeout, cache路径, 模型列表) [deep]
└── Task 6: 错误处理改进 (静默失败修复 + 错误上下文 + 原子缓存) [deep]

Wave 3 (After Wave 2 — 规则管理 + 进度 + 日志):
├── Task 7: 规则管理 (--list-rules, --disable-rule, 规则过滤) [deep]
├── Task 8: tqdm进度反馈 (进度条 + ETA + 当前文件) [quick]
└── Task 9: 日志控制 (--verbose, --quiet, 结构化日志) [quick]

Wave 4 (After Wave 3 — 测试覆盖):
├── Task 10: LLM Factory + Config测试 [deep]
├── Task 11: GitHub Client测试 [deep]
├── Task 12: ReviewAgent + Analyzer测试 [deep]
└── Task 13: Models + Fixer + AutoMerger测试补全 [deep]

Wave 5 (After Wave 4 — 高级功能):
├── Task 14: LLM Provider fallback链 [unspecified-high]
├── Task 15: Rate Limit检测与退避 [unspecified-high]
└── Task 16: 交互式fix选择模式 [unspecified-high]

Wave 6 (After Wave 5 — 最终清理):
├── Task 17: 手动Lint修复 + 类型标注完善 [unspecified-high]
└── Task 18: conftest.py共享fixtures + 测试基础设施 [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: T1→T2→T5→T6→T8→T10→T14→T17→F1-F4
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 4 (Waves 4, 5)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | — | 1 |
| 2 | — | 4,5,6,7,8,9,14,15,16,17 | 1 |
| 3 | — | 10,11,12,13 | 1 |
| 4 | 2 | — | 2 |
| 5 | 2 | 6,8 | 2 |
| 6 | 2 | 7 | 2 |
| 7 | 6 | — | 3 |
| 8 | 5 | — | 3 |
| 9 | 4 | — | 3 |
| 10 | 3 | 14 | 4 |
| 11 | 3 | 15 | 4 |
| 12 | 3 | 14 | 4 |
| 13 | 3 | 16 | 4 |
| 14 | 10,12 | — | 5 |
| 15 | 11 | — | 5 |
| 16 | 13 | — | 5 |
| 17 | 2 | 18 | 6 |
| 18 | 17 | — | 6 |

### Agent Dispatch Summary

- **Wave 1**: **3** — T1 → `quick`, T2 → `quick`, T3 → `quick`
- **Wave 2**: **3** — T4 → `deep`, T5 → `deep`, T6 → `deep`
- **Wave 3**: **3** — T7 → `deep`, T8 → `quick`, T9 → `quick`
- **Wave 4**: **4** — T10 → `deep`, T11 → `deep`, T12 → `deep`, T13 → `deep`
- **Wave 5**: **3** — T14 → `unspecified-high`, T15 → `unspecified-high`, T16 → `unspecified-high`
- **Wave 6**: **2** — T17 → `unspecified-high`, T18 → `quick`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. 修复确认Bug cli.py:491 (len()缺失)

  **What to do**:
  - 在 `cli.py:491` 将 `preview.get("files", []) > 5` 改为 `len(preview.get("files", [])) > 5`
  - 同时检查同一文件是否有类似的 `list > int` 错误模式
  - 先写一个测试验证修复前后的行为差异（TDD RED）
  - 修复后确认测试通过（TDD GREEN）

  **Must NOT do**:
  - 不要修改其他不相关的代码
  - 不要添加新功能

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单行bug修复，明确且简单
  - **Skills**: [`systematic-debugging`]
    - `systematic-debugging`: 确认bug根因并验证修复

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py:491` — 确认的Bug位置: `preview.get("files", []) > 5` 应为 `len(preview.get("files", [])) > 5`
  - `python/src/codereview/cli.py:879-999` — `_print_fix_output()` 函数上下文，理解preview结构

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `python/tests/test_cli_bug_fix.py`
  - [ ] 测试用例验证 `len()` 修复后的正确行为
  - [ ] `pytest python/tests/test_cli_bug_fix.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: Bug修复验证 — preview文件数判断
    Tool: Bash (pytest)
    Preconditions: cli.py中bug已修复
    Steps:
      1. 创建测试用例：构造files列表长度为6的preview dict
      2. 调用_print_fix_output()中相关的判断逻辑
      3. 断言结果正确（显示"... and N more files"）
    Expected Result: 测试通过，不抛出TypeError
    Failure Indicators: TypeError: '>' not supported between 'list' and 'int'
    Evidence: .sisyphus/evidence/task-1-bug-fix.txt
  ```

  **Commit**: YES
  - Message: `fix(cli): fix len() bug in fix preview display`
  - Files: `python/src/codereview/cli.py`, `python/tests/test_cli_bug_fix.py`
  - Pre-commit: `pytest python/tests/test_cli_bug_fix.py -v`

- [x] 2. Lint自动修复 (ruff --fix)

  **What to do**:
  - 运行 `ruff check --fix python/src/` 自动修复所有可修复的lint错误
  - 运行 `ruff format python/src/` 统一代码格式
  - 检查剩余无法自动修复的错误数量，记录到证据文件
  - 特别关注: import排序(I001)、未使用import(F401)、空行空白(W293)
  - **不要**修改 `Optional[X]` → `X | None`，因为项目需要兼容Python 3.9

  **Must NOT do**:
  - 不要修改业务逻辑
  - 不要将 `Optional[X]` 改为 `X | None`（Python 3.9兼容）
  - 不要修改测试文件

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 主要是运行工具命令，无需深度思考
  - **Skills**: []
    - 无需额外skills，纯ruff操作

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: Tasks 4, 5, 6, 7, 8, 9, 14, 15, 16, 17
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `AGENTS.md` — 项目lint配置说明: `ruff check python/src/`, `ruff check --fix python/src/`
  - `pyproject.toml` — ruff配置（target-version, line-length等）

  **Acceptance Criteria**:
  - [ ] `ruff check python/src/` 自动修复错误数显著减少
  - [ ] `ruff format --check python/src/` → PASS
  - [ ] 剩余手动修复错误数量记录到证据文件

  **QA Scenarios**:
  ```
  Scenario: Lint自动修复验证
    Tool: Bash (ruff)
    Preconditions: ruff已安装
    Steps:
      1. ruff check --fix python/src/
      2. ruff format python/src/
      3. ruff check python/src/ 2>&1 | tee evidence
      4. 统计剩余错误数
    Expected Result: 自动修复错误>100个，剩余需手动修复的错误记录在证据文件
    Failure Indicators: ruff check --fix 本身报错
    Evidence: .sisyphus/evidence/task-2-lint-fix.txt

  Scenario: 格式一致性检查
    Tool: Bash (ruff format)
    Steps:
      1. ruff format --check python/src/
    Expected Result: 0 files would be reformatted
    Failure Indicators: 有文件需要格式化
    Evidence: .sisyphus/evidence/task-2-format-check.txt
  ```

  **Commit**: YES
  - Message: `chore: auto-fix lint errors with ruff`
  - Files: `python/src/codereview/` (multiple)
  - Pre-commit: `ruff check python/src/ && ruff format --check python/src/`

- [x] 3. 修复测试收集 + 添加tqdm依赖

  **What to do**:
  - 修复 `test_report_generator.py` 因缺少 matplotlib 导致的import错误（将matplotlib添加到dev依赖或mock掉）
  - 在 `pyproject.toml` 的 dependencies 中添加 `tqdm`
  - 在 `pyproject.toml` 的 dev dependencies 中确认有 `pytest-cov`
  - 验证 `pytest python/tests/ --collect-only` 无错误
  - 运行全部测试确认基线通过

  **Must NOT do**:
  - 不要修改测试的断言逻辑
  - 不要删除任何现有测试

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 主要是依赖管理和import修复
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: 确保测试基础设施正确

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Tasks 10, 11, 12, 13
  - **Blocked By**: None

  **References**:
  **Pattern References**:
  - `python/pyproject.toml` — 当前依赖列表，需要添加tqdm
  - `python/tests/test_report_generator.py` — matplotlib import错误的源头
  - `AGENTS.md` — 测试运行方式: `pytest python/tests/ -v`

  **API/Type References**:
  - tqdm官方文档: `https://github.com/tqdm/tqdm` — 基本用法 `from tqdm import tqdm`

  **Acceptance Criteria**:
  - [ ] `pytest python/tests/ --collect-only` → 无error，201 tests collected
  - [ ] `pytest python/tests/ -v` → ALL pass (或仅有已知的expected failure)
  - [ ] `python -c "from tqdm import tqdm; print('tqdm OK')"` → 成功
  - [ ] `python -c "import matplotlib; print('matplotlib OK')"` → 成功 (或mock正常)

  **QA Scenarios**:
  ```
  Scenario: 测试收集完整性
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/ --collect-only 2>&1
      2. 统计collected数量
      3. 检查是否有error行
    Expected Result: 201+ tests collected, 0 errors
    Failure Indicators: "error" in output, collected < 200
    Evidence: .sisyphus/evidence/task-3-test-collect.txt

  Scenario: tqdm可用性验证
    Tool: Bash (python)
    Steps:
      1. python -c "from tqdm import tqdm; [print(i) for i in tqdm(range(5))]"
    Expected Result: 成功导入并输出进度条
    Failure Indicators: ImportError / ModuleNotFoundError
    Evidence: .sisyphus/evidence/task-3-tqdm-import.txt

  Scenario: 全量测试基线
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/ -v --tb=short 2>&1
      2. 统计pass/fail/error
    Expected Result: ALL pass
    Failure Indicators: FAILED or ERROR in output
    Evidence: .sisyphus/evidence/task-3-test-baseline.txt
  ```

  **Commit**: YES
  - Message: `fix(tests): fix test collection error + add tqdm dependency`
  - Files: `python/pyproject.toml`, `python/tests/test_report_generator.py`
  - Pre-commit: `pytest python/tests/ --collect-only`

- [x] 4. CLI标志扩展 (--version, --clear-cache, --log-level)

  **What to do**:
  - TDD RED: 先写测试 `test_cli_flags.py`:
    - 测试 `--version` 输出版本号 (从 pyproject.toml 或 __version__ 读取)
    - 测试 `--clear-cache` 清除 `.codereview-agent/cache/` 目录
    - 测试 `--clear-cache --yes` 跳过确认
    - 测试 `--log-level DEBUG/INFO/WARNING/ERROR` 设置日志级别
    - 测试 `--verbose` 等同 `--log-level DEBUG`
    - 测试 `--quiet` 等同 `--log-level ERROR`
    - 测试 `--verbose` 和 `--quiet` 同时指定时，后者优先
  - TDD GREEN: 实现：
    - `--version`: 从 `importlib.metadata.version("codereview")` 读取，打印后exit(0)
    - `--clear-cache`: 删除 `.codereview-agent/cache/` 目录（默认需确认，--yes跳过）
    - `--log-level`: 设置 `logging.basicConfig(level=...)` 级别
    - `--verbose` / `--quiet`: 便捷标志，映射到log-level
  - TDD REFACTOR: 清理代码，确保与现有CLI结构一致

  **Must NOT do**:
  - 不要改变现有flag的行为
  - 不要添加新子命令

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及CLI架构改动，需要理解argparse结构
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Task 9
  - **Blocked By**: Task 2 (lint fix)

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py:381-508` — 当前argparse定义，添加新flag的位置
  - `python/src/codereview/cli.py:26-30` — 当前logging.basicConfig()配置
  - `python/pyproject.toml` — version字段位置，用于--version读取

  **API/Type References**:
  - `importlib.metadata.version()` — Python标准库，读取包版本

  **Test References**:
  - `python/tests/test_cli.py` — 现有CLI测试模式

  **Acceptance Criteria**:
  - [ ] `test_cli_flags.py` 创建，包含7个测试用例
  - [ ] `python -m codereview.cli --version` 输出版本号
  - [ ] `python -m codereview.cli --clear-cache --yes` 清除缓存目录
  - [ ] `python -m codereview.cli --log-level DEBUG --diff '...'` 显示DEBUG日志
  - [ ] `pytest python/tests/test_cli_flags.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: --version标志验证
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --version
      2. 检查输出是否为 X.Y.Z 格式
    Expected Result: 输出如 "codereview-agent 1.2.3"
    Failure Indicators: exit code != 0 或输出不是版本号格式
    Evidence: .sisyphus/evidence/task-4-version.txt

  Scenario: --clear-cache清除验证
    Tool: Bash (python)
    Preconditions: .codereview-agent/cache/ 目录存在
    Steps:
      1. mkdir -p .codereview-agent/cache/test && echo "data" > .codereview-agent/cache/test/file.json
      2. python -m codereview.cli --clear-cache --yes
      3. 检查 .codereview-agent/cache/ 是否已删除
    Expected Result: 缓存目录被成功删除
    Failure Indicators: 目录仍存在
    Evidence: .sisyphus/evidence/task-4-clear-cache.txt

  Scenario: --log-level无效值错误处理
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --log-level INVALID 2>&1
    Expected Result: 明确的错误消息 "invalid log level: INVALID"
    Failure Indicators: 静默忽略或crash
    Evidence: .sisyphus/evidence/task-4-log-level-error.txt
  ```

  **Commit**: YES
  - Message: `feat(cli): add --version, --clear-cache, --log-level flags`
  - Files: `python/src/codereview/cli.py`, `python/tests/test_cli_flags.py`
  - Pre-commit: `pytest python/tests/test_cli_flags.py -v`

- [x] 5. 配置灵活化 (max_concurrency, timeout, cache路径, 模型列表)

  **What to do**:
  - TDD RED: 先写测试 `test_config_flexibility.py`:
    - 测试 max_concurrency 从config读取 (默认5)
    - 测试 timeout_seconds 从config读取 (默认30)
    - 测试 cache_dir 从config读取 (默认".codereview-agent/cache")
    - 测试 default_models 从config读取/覆盖
    - 测试边界值: max_concurrency=0报错, >100警告
    - 测试 temperature 范围验证 (0.0-2.0)
  - TDD GREEN: 实现：
    - 在 `models/__init__.py` 的 Config Pydantic model 中添加新字段:
      ```python
      max_concurrency: int = Field(default=5, ge=1, le=50)
      timeout_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
      cache_dir: str = ".codereview-agent/cache"
      default_models: Optional[dict[str, str]] = None  # 覆盖内置默认模型
      ```
    - 修改 `reviewer.py` 使用 `config.max_concurrency` 替代硬编码
    - 修改 `reviewer.py` 使用 `config.timeout_seconds` 替代硬编码
    - 修改 `cache.py` 使用 `config.cache_dir` 替代硬编码
    - 修改 `llm.py` 的 `get_default_model()` 支持 config 覆盖
    - 更新 `.codereview-agent.yaml` 示例配置
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要破坏现有配置文件的兼容性（新字段都有默认值）
  - 不要移除现有缓存目录（保持读取旧缓存的能力）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及多文件改动（models, reviewer, cache, llm），需要协调
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Tasks 6, 8
  - **Blocked By**: Task 2 (lint fix)

  **References**:
  **Pattern References**:
  - `python/src/codereview/models/__init__.py` — Config Pydantic model定义，添加新字段的位置
  - `python/src/codereview/agents/reviewer.py:108-109` — 硬编码 `max_concurrency=5`, `timeout_seconds=30.0`
  - `python/src/codereview/core/cache.py:27-28` — 硬编码缓存路径
  - `python/src/codereview/core/llm.py:17-24, 104-107` — 硬编码默认模型和 `get_default_model()`

  **API/Type References**:
  - `python/src/codereview/core/config.py` — ConfigLoader，解析YAML配置
  - `python/src/codereview/models/__init__.py:ConfigLLM` — 现有LLM配置模型

  **Test References**:
  - `python/tests/test_cache.py` — 现有cache测试模式

  **Acceptance Criteria**:
  - [ ] `test_config_flexibility.py` 创建，包含6个测试
  - [ ] Config模型包含新字段且有正确的默认值
  - [ ] reviewer.py使用config值替代硬编码
  - [ ] cache.py使用config值替代硬编码
  - [ ] `pytest python/tests/test_config_flexibility.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: 自定义并发数验证
    Tool: Bash (pytest)
    Steps:
      1. 创建config: max_concurrency: 3
      2. 创建ReviewAgent使用该config
      3. 验证semaphore值为3
    Expected Result: 并发限制为3
    Failure Indicators: 仍然使用默认值5
    Evidence: .sisyphus/evidence/task-5-concurrency.txt

  Scenario: 边界值验证 — max_concurrency=0
    Tool: Bash (pytest)
    Steps:
      1. 创建config: max_concurrency: 0
      2. 验证Pydantic validation error
    Expected Result: ValidationError, "must be greater than or equal to 1"
    Failure Indicators: 静默接受0值
    Evidence: .sisyphus/evidence/task-5-boundary.txt

  Scenario: 自定义缓存路径验证
    Tool: Bash (pytest)
    Steps:
      1. 创建config: cache_dir: "/tmp/test-cache"
      2. 验证CacheManager使用新路径
    Expected Result: 缓存文件写入 /tmp/test-cache/
    Failure Indicators: 仍然使用 .codereview-agent/cache/
    Evidence: .sisyphus/evidence/task-5-cache-path.txt
  ```

  **Commit**: YES
  - Message: `feat(config): make core parameters configurable`
  - Files: `python/src/codereview/models/__init__.py`, `python/src/codereview/agents/reviewer.py`, `python/src/codereview/core/cache.py`, `python/src/codereview/core/llm.py`, `python/tests/test_config_flexibility.py`
  - Pre-commit: `pytest python/tests/test_config_flexibility.py -v`

- [ ] 6. 错误处理改进 (静默失败修复 + 错误上下文 + 原子缓存)

  **What to do**:
  - TDD RED: 先写测试 `test_error_handling.py`:
    - 测试 get_git_diff() 失败时抛出明确错误（不再静默返回空字符串）
    - 测试 JSON解析失败时WARNING日志包含原始输入片段
    - 测试 GitHub API HTTPError时错误消息包含PR号和URL
    - 测试 ConfigError包含具体字段名
    - 测试 项目分析失败时日志WARNING（不再静默创建"unknown"）
    - 测试 缓存原子写入：模拟写入中途失败，验证旧缓存未被破坏
  - TDD GREEN: 实现：
    - `cli.py get_git_diff()`: 失败时抛出 `RuntimeError("Failed to get git diff: {stderr}")` 
    - `cli.py _parse_diff()`: JSON解析失败时 log.warning 包含前100个字符
    - `github_client.py`: 所有HTTPError消息添加 PR号/URL
    - `config.py ConfigError`: 添加 `field_name` 属性
    - `analyzer.py`: 项目分析失败时 log.warning("Failed to analyze project context, using defaults")
    - `cache.py save()`: 使用原子写入 (write to temp file + os.replace)
    - `cache.py`: 所有JSON解析错误添加 log.warning
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要用bare except
  - 不要把error改成exception（保持现有调用方的try/except兼容）
  - 不要删除日志，只提升日志级别（debug→warning）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 多文件改动，涉及错误处理策略，需仔细分析每个调用方
  - **Skills**: [`systematic-debugging`, `test-driven-development`]
    - `systematic-debugging`: 理解错误传播链路
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5)
  - **Blocks**: Task 7
  - **Blocked By**: Task 2 (lint fix)

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py:66-67` — `get_git_diff()` 静默返回空字符串的位置
  - `python/src/codereview/cli.py:362-376` — `_parse_diff()` JSON解析静默失败
  - `python/src/codereview/core/github_client.py:264,415,639` — HTTPError消息缺少PR号/URL
  - `python/src/codereview/core/config.py:50-67` — ConfigError缺少字段名
  - `python/src/codereview/agents/analyzer.py:167` — 分析失败静默创建默认值
  - `python/src/codereview/core/cache.py:154-155,157-179` — 缓存读取/写入问题

  **Test References**:
  - `python/tests/test_cli.py` — 现有CLI测试模式（subprocess mock）

  **Acceptance Criteria**:
  - [ ] `test_error_handling.py` 创建，包含6个测试
  - [ ] get_git_diff() 失败时调用方能看到明确错误
  - [ ] 所有静默失败改为至少WARNING级别日志
  - [ ] 缓存save()使用原子写入（tempfile + os.replace）
  - [ ] `pytest python/tests/test_error_handling.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: get_git_diff失败明确报错
    Tool: Bash (pytest)
    Steps:
      1. Mock subprocess.run 抛出FileNotFoundError("git not found")
      2. 调用 get_git_diff()
      3. 验证不再返回空字符串，而是明确错误
    Expected Result: 调用方收到明确的错误信息 "Failed to get git diff: git not found"
    Failure Indicators: 仍然静默返回空字符串
    Evidence: .sisyphus/evidence/task-6-git-diff-error.txt

  Scenario: 缓存原子写入 — 模拟中途失败
    Tool: Bash (pytest)
    Steps:
      1. 创建缓存文件 old_cache.json 包含有效数据
      2. Mock os.replace 抛出OSError
      3. 调用 cache.save()
      4. 验证 old_cache.json 仍然完整
    Expected Result: 旧缓存文件未被破坏
    Failure Indicators: old_cache.json 为空或损坏
    Evidence: .sisyphus/evidence/task-6-atomic-cache.txt

  Scenario: GitHub API错误包含PR号
    Tool: Bash (pytest)
    Steps:
      1. Mock GitHub API返回404
      2. 调用get_pr(pr_number=123)
      3. 验证错误消息包含"PR #123"
    Expected Result: "Failed to get PR #123: 404 Not Found"
    Failure Indicators: 错误消息不包含PR号
    Evidence: .sisyphus/evidence/task-6-github-error.txt
  ```

  **Commit**: YES
  - Message: `fix(core): improve error handling and add context to errors`
  - Files: `python/src/codereview/cli.py`, `python/src/codereview/core/github_client.py`, `python/src/codereview/core/config.py`, `python/src/codereview/core/cache.py`, `python/src/codereview/agents/analyzer.py`, `python/tests/test_error_handling.py`
  - Pre-commit: `pytest python/tests/test_error_handling.py -v`

- [x] 7. 规则管理 (--list-rules, --disable-rule, 规则过滤)

  **What to do**:
  - TDD RED: 先写测试 `test_rule_management.py`:
    - 测试 `--list-rules` 输出所有30条规则（表格格式）
    - 测试 `--list-rules --json` 输出JSON数组
    - 测试 `--disable-rule OWASP-A01-001` 跳过该规则
    - 测试 `--disable-rule` 支持逗号分隔多个ID
    - 测试 `--disable-rule INVALID_ID` 输出warning
    - 测试 RuleEngine新增 `get_all_rules()` 方法
    - 测试 RuleEngine新增 `disable_rules(ids: list[str])` 方法
  - TDD GREEN: 实现：
    - `rules/__init__.py` 添加:
      - `get_all_rules() -> list[DetectionRule]`: 返回所有已加载规则
      - `disable_rules(ids: list[str]) -> None`: 按ID禁用规则
    - `cli.py` 添加:
      - `--list-rules`: 列出规则后exit(0)
      - `--disable-rule RULE_ID`: 可重复使用或逗号分隔
    - `reviewer.py`: 创建RuleEngine时传入disabled_rules
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要改变规则引擎的核心检测逻辑
  - 不要删除规则，只做禁用

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 涉及rules引擎架构改动和CLI集成
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 9)
  - **Blocks**: None
  - **Blocked By**: Task 6 (error handling)

  **References**:
  **Pattern References**:
  - `python/src/codereview/rules/__init__.py:67-239` — RuleEngine类，添加 get_all_rules() 和 disable_rules() 的位置
  - `python/src/codereview/rules/__init__.py:149-172` — detect() 方法，需要跳过disabled规则
  - `python/src/codereview/rules/owasp_rules.yaml` — 规则YAML定义，理解规则结构(id, name, severity, pattern)

  **API/Type References**:
  - `python/src/codereview/rules/__init__.py:DetectionRule` — 规则数据类(id, name, pattern, severity, description, suggestion, language)
  - `python/src/codereview/rules/__init__.py:create_rule_engine()` — 规则引擎工厂方法

  **Test References**:
  - `python/tests/test_rules.py` — 现有规则测试模式

  **Acceptance Criteria**:
  - [ ] `test_rule_management.py` 创建，包含7个测试
  - [ ] `python -m codereview.cli --list-rules` 列出30条规则
  - [ ] `python -m codereview.cli --list-rules --json` 输出有效JSON
  - [ ] `python -m codereview.cli --disable-rule OWASP-A01-001` 跳过该规则
  - [ ] `pytest python/tests/test_rule_management.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: --list-rules完整输出验证
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --list-rules
      2. 验证输出包含30条规则
      3. 验证每条规则包含ID、Name、Severity
    Expected Result: 表格格式输出，30行规则数据
    Failure Indicators: 规则数!=30 或格式不完整
    Evidence: .sisyphus/evidence/task-7-list-rules.txt

  Scenario: --list-rules --json输出验证
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --list-rules --json 2>/dev/null
      2. python -c "import json,sys; d=json.load(sys.stdin); assert len(d)==30"
    Expected Result: 有效JSON数组，长度30
    Failure Indicators: JSON解析失败或长度不对
    Evidence: .sisyphus/evidence/task-7-list-rules-json.txt

  Scenario: --disable-rule禁用验证
    Tool: Bash (pytest)
    Steps:
      1. 创建RuleEngine并disable OWASP-A01-001
      2. 用含 "password = 'hardcoded'" 的内容调用 detect()
      3. 验证OWASP-A01-001不在结果中
    Expected Result: 硬编码密码不被检测（因为规则被禁用）
    Failure Indicators: 仍然检测到该规则
    Evidence: .sisyphus/evidence/task-7-disable-rule.txt

  Scenario: --disable-rule无效ID处理
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --disable-rule INVALID-RULE-ID --diff '{}' 2>&1
    Expected Result: WARNING日志 "Unknown rule ID: INVALID-RULE-ID, ignoring"
    Failure Indicators: 静默忽略或crash
    Evidence: .sisyphus/evidence/task-7-invalid-rule.txt
  ```

  **Commit**: YES
  - Message: `feat(rules): add --list-rules and --disable-rule CLI flags`
  - Files: `python/src/codereview/cli.py`, `python/src/codereview/rules/__init__.py`, `python/tests/test_rule_management.py`
  - Pre-commit: `pytest python/tests/test_rule_management.py -v`

- [x] 8. tqdm进度反馈 (进度条 + ETA + 当前文件)

  **What to do**:
  - TDD RED: 先写测试 `test_progress.py`:
    - 测试 review_files() 对多文件显示进度条
    - 测试 进度条显示 "Reviewing file N/M: filename.py"
    - 测试 TQDM_DISABLE=1 环境变量禁用进度条
    - 测试 单文件review时不显示进度条（只有1个不需要）
    - 测试 进度条在完成后关闭（不残留）
  - TDD GREEN: 实现：
    - 在 `reviewer.py review_files()` 中集成tqdm:
      ```python
      from tqdm import tqdm
      pbar = tqdm(diff_entries, desc="Reviewing", unit="file", disable=len(diff_entries)<=1)
      for entry in pbar:
          pbar.set_postfix(file=entry.filename[:30])
          # ... review logic
      pbar.close()
      ```
    - 在 `cli.py main()` 中为项目分析添加简单进度提示
    - 确保 tqdm 在 --quiet 模式下自动禁用
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要在library代码中使用tqdm（只在CLI入口使用）
  - 不要添加声音/动画等花哨功能
  - 不要在JSON输出模式下显示进度条

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: tqdm集成相对简单，主要是包裹现有循环
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 7, 9)
  - **Blocks**: None
  - **Blocked By**: Task 5 (config flexibility - 需要config中的max_concurrency)

  **References**:
  **Pattern References**:
  - `python/src/codereview/agents/reviewer.py:139-206` — `review_files()` 方法，包裹tqdm的位置
  - `python/src/codereview/cli.py:216,242-248` — main()中的review调用位置

  **External References**:
  - tqdm官方文档: `https://github.com/tqdm/tqdm` — 基本用法和tqdm.asyncio

  **Acceptance Criteria**:
  - [ ] `test_progress.py` 创建，包含5个测试
  - [ ] 多文件review时stderr显示进度条
  - [ ] 进度条显示文件名和ETA
  - [ ] TQDM_DISABLE=1 环境变量正常工作
  - [ ] `pytest python/tests/test_progress.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: 多文件进度条验证
    Tool: Bash (python)
    Steps:
      1. 构造10个DiffEntry
      2. 运行review_files()
      3. 捕获stderr输出
      4. 验证包含 "Reviewing" 和 "file" 和ETA
    Expected Result: stderr包含进度条字符 (|, #, %)
    Failure Indicators: 无进度条输出
    Evidence: .sisyphus/evidence/task-8-progress.txt

  Scenario: TQDM_DISABLE环境变量
    Tool: Bash (python)
    Steps:
      1. TQDM_DISABLE=1 python -m codereview.cli --diff '...'
      2. 验证stderr无进度条输出
    Expected Result: 干净的输出，无进度条
    Failure Indicators: 仍有进度条输出
    Evidence: .sisyphus/evidence/task-8-tqdm-disable.txt

  Scenario: 单文件无进度条
    Tool: Bash (python)
    Steps:
      1. 构造1个DiffEntry
      2. 运行review_files()
      3. 验证无进度条输出
    Expected Result: 直接输出结果，无进度条
    Failure Indicators: 1个文件也显示进度条
    Evidence: .sisyphus/evidence/task-8-single-file.txt
  ```

  **Commit**: YES
  - Message: `feat(ui): add tqdm progress bars for long operations`
  - Files: `python/src/codereview/agents/reviewer.py`, `python/src/codereview/cli.py`, `python/tests/test_progress.py`
  - Pre-commit: `pytest python/tests/test_progress.py -v`

- [x] 9. 日志控制 (--verbose, --quiet, 结构化日志)

  **What to do**:
  - TDD RED: 先写测试 (扩展 `test_cli_flags.py`):
    - 测试 `--verbose` 设置日志级别为DEBUG
    - 测试 `--quiet` 设置日志级别为ERROR
    - 测试 `--verbose` + `--quiet` 后者覆盖前者
    - 测试 `--log-level DEBUG` 等同 `--verbose`
    - 测试 在 `--json` 模式下日志不干扰JSON输出
  - TDD GREEN: 实现：
    - 重构 `cli.py` 的 logging 配置:
      ```python
      if args.quiet:
          log_level = logging.ERROR
      elif args.verbose:
          log_level = logging.DEBUG
      elif args.log_level:
          log_level = getattr(logging, args.log_level.upper())
      else:
          log_level = logging.INFO
      logging.basicConfig(level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
      ```
    - 在 `--json` 模式下将日志输出到stderr（避免干扰stdout的JSON）
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要改变现有日志消息的内容
  - 不要添加新的日志handler

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 主要是logging配置重构，逻辑简单
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 7, 8)
  - **Blocks**: None
  - **Blocked By**: Task 4 (CLI flags)

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py:26-30` — 当前 `logging.basicConfig()` 位置
  - `python/src/codereview/cli.py:467,489` — 使用emoji的日志输出（在--quiet模式下应隐藏）

  **Acceptance Criteria**:
  - [ ] `--verbose` 显示DEBUG级别日志
  - [ ] `--quiet` 只显示ERROR级别日志
  - [ ] 两者同时指定后者优先
  - [ ] `--json` 模式下日志走stderr
  - [ ] `pytest python/tests/test_cli_flags.py -v` → ALL pass (含新增测试)

  **QA Scenarios**:
  ```
  Scenario: --verbose模式验证
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --verbose --diff '{}' 2>&1 | head -5
      2. 验证输出包含DEBUG级别日志
    Expected Result: 日志行包含 "DEBUG"
    Failure Indicators: 只有INFO/WARNING级别
    Evidence: .sisyphus/evidence/task-9-verbose.txt

  Scenario: --quiet模式验证
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --quiet --diff '{}' 2>&1
      2. 验证输出只有ERROR级别
    Expected Result: 无INFO/WARNING/DEBUG日志
    Failure Indicators: 出现非ERROR日志
    Evidence: .sisyphus/evidence/task-9-quiet.txt

  Scenario: --json模式日志隔离
    Tool: Bash (python)
    Steps:
      1. python -m codereview.cli --json --diff '{}' 2>/dev/null
      2. 验证stdout只有纯JSON
      3. python -m codereview.cli --json --diff '{}' 1>/dev/null
      4. 验证stderr有日志
    Expected Result: stdout纯JSON, stderr有日志
    Failure Indicators: JSON和日志混在stdout
    Evidence: .sisyphus/evidence/task-9-json-logging.txt
  ```

  **Commit**: YES (groups with Task 4)
  - Message: `feat(cli): add --verbose/--quiet logging control`
  - Files: `python/src/codereview/cli.py`, `python/tests/test_cli_flags.py`
  - Pre-commit: `pytest python/tests/test_cli_flags.py -v`

- [x] 10. LLM Factory + Config测试覆盖

  **What to do**:
  - 为 `core/llm.py` 编写完整测试 `test_llm.py`:
    - 测试每个Provider的创建 (OpenAI, Anthropic, Zhipu, MiniMax, Qwen, DeepSeek)
    - 测试 `get_default_model()` 对每个Provider返回正确的默认模型
    - 测试 `get_default_base_url()` 对每个Provider返回正确的URL
    - 测试未知Provider抛出ValueError
    - 测试temperature传递
    - 测试custom model override
    - 测试custom base_url override
    - 测试API key为空时的错误处理
  - 为 `core/config.py` 编写完整测试 `test_config.py`:
    - 测试YAML配置加载
    - 测试 `${ENV_VAR}` 环境变量替换
    - 测试 `${ENV_VAR:-default}` 带默认值的环境变量替换
    - 测试嵌套环境变量替换
    - 测试无效YAML语法的错误处理
    - 测试缺失必填字段的ValidationError
    - 测试自定义prompt路径验证
    - 测试ConfigError包含字段名

  **Must NOT do**:
  - 不要调用真实LLM API（全部mock）
  - 不要改变现有llm.py/config.py的接口

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要深入理解LLM工厂模式和配置解析逻辑
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: 测试编写

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 11, 12, 13)
  - **Blocks**: Task 14
  - **Blocked By**: Task 3 (test infrastructure)

  **References**:
  **Pattern References**:
  - `python/src/codereview/core/llm.py:13-107` — LLMFactory完整实现，需要测试每个方法
  - `python/src/codereview/core/config.py` — ConfigLoader完整实现

  **Test References**:
  - `python/tests/test_cache.py` — 参考测试模式（tempfile隔离）
  - `python/tests/test_auto_merger.py` — 参考AsyncMock使用

  **Acceptance Criteria**:
  - [ ] `test_llm.py` 创建，包含8+个测试
  - [ ] `test_config.py` 创建，包含8+个测试
  - [ ] `pytest python/tests/test_llm.py python/tests/test_config.py -v` → ALL pass
  - [ ] 覆盖率 >80% for llm.py and config.py

  **QA Scenarios**:
  ```
  Scenario: 所有Provider创建验证
    Tool: Bash (pytest)
    Steps:
      1. 对每个Provider mock ChatOpenAI
      2. 验证传入正确的model, base_url, api_key, temperature
    Expected Result: 6个provider全部创建成功，参数正确
    Failure Indicators: 任何provider创建失败或参数不匹配
    Evidence: .sisyphus/evidence/task-10-llm-providers.txt

  Scenario: 环境变量替换验证
    Tool: Bash (pytest)
    Steps:
      1. 设置TEST_API_KEY=sk-test-123
      2. 解析 "${TEST_API_KEY}" → "sk-test-123"
      3. 解析 "${MISSING_KEY:-default-key}" → "default-key"
    Expected Result: 环境变量正确替换
    Failure Indicators: 替换失败或保留${}语法
    Evidence: .sisyphus/evidence/task-10-env-vars.txt

  Scenario: 覆盖率检查
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/test_llm.py python/tests/test_config.py --cov=codereview.core.llm --cov=codereview.core.config --cov-report=term-missing
    Expected Result: 两个文件覆盖率均 >80%
    Failure Indicators: 覆盖率 <80%
    Evidence: .sisyphus/evidence/task-10-coverage.txt
  ```

  **Commit**: YES
  - Message: `test: add comprehensive tests for LLM Factory and Config`
  - Files: `python/tests/test_llm.py`, `python/tests/test_config.py`
  - Pre-commit: `pytest python/tests/test_llm.py python/tests/test_config.py -v`

- [x] 11. GitHub Client测试覆盖

  **What to do**:
  - 为 `core/github_client.py` (770行) 编写完整测试 `test_github_client.py`:
    - 测试 PR获取 (get_pr) — 成功/404/403
    - 测试 diff获取 (get_diff) — 成功/空diff/网络错误
    - 测试 评论发布 (post_comment) — 成功/失败
    - 测试 approval检查 (get_approvals) — 有approvals/无approvals/API错误
    - 测试 合并 (merge_pr) — squash/merge/rebase三种方式
    - 测试 check run状态更新
    - 测试 token验证 — 空/无效
    - 测试 gh CLI fallback — gh可用/不可用
    - 测试 大diff处理（>10MB）
    - 测试 rate limit响应处理

  **Must NOT do**:
  - 不要调用真实GitHub API（全部mock aiohttp）
  - 不要修改github_client.py的接口

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 770行代码，需要全面覆盖各种HTTP场景
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: 测试编写

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 10, 12, 13)
  - **Blocks**: Task 15
  - **Blocked By**: Task 3 (test infrastructure)

  **References**:
  **Pattern References**:
  - `python/src/codereview/core/github_client.py` — 完整实现，770行
  - `python/src/codereview/core/github_client.py:77-117` — __init__方法
  - `python/src/codereview/core/github_client.py:264` — get_pr (404处理)
  - `python/src/codereview/core/github_client.py:415` — get_diff
  - `python/src/codereview/core/github_client.py:639` — merge_pr

  **Test References**:
  - `python/tests/test_auto_merger.py` — AsyncMock for GitHub client的模式

  **Acceptance Criteria**:
  - [ ] `test_github_client.py` 创建，包含10+个测试
  - [ ] `pytest python/tests/test_github_client.py -v` → ALL pass
  - [ ] 覆盖率 >80% for github_client.py

  **QA Scenarios**:
  ```
  Scenario: PR获取成功和失败
    Tool: Bash (pytest)
    Steps:
      1. Mock 200响应返回PR数据
      2. 验证返回正确的PR信息
      3. Mock 404响应
      4. 验证RuntimeError包含PR号
    Expected Result: 成功返回数据，失败抛出明确错误
    Failure Indicators: 测试失败
    Evidence: .sisyphus/evidence/task-11-github-pr.txt

  Scenario: 覆盖率检查
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/test_github_client.py --cov=codereview.core.github_client --cov-report=term-missing
    Expected Result: 覆盖率 >80%
    Failure Indicators: 覆盖率 <80%
    Evidence: .sisyphus/evidence/task-11-coverage.txt
  ```

  **Commit**: YES
  - Message: `test: add comprehensive tests for GitHub Client`
  - Files: `python/tests/test_github_client.py`
  - Pre-commit: `pytest python/tests/test_github_client.py -v`

- [x] 12. ReviewAgent + Analyzer测试覆盖

  **What to do**:
  - 为 `agents/reviewer.py` 编写完整测试 `test_reviewer.py`:
    - 测试 单文件review流程 (mock LLM返回)
    - 测试 多文件并行review (验证并发控制)
    - 测试 缓存命中 (跳过已缓存文件)
    - 测试 排除模式匹配 (_should_exclude)
    - 测试 retry逻辑 (3次重试后降级)
    - 测试 超时处理
    - 测试 LLM响应解析 (正常/异常JSON)
    - 测试 置信度计算逻辑
  - 为 `agents/analyzer.py` 编写完整测试 `test_analyzer.py`:
    - 测试 项目文件收集
    - 测试 LLM分析成功/失败
    - 测试 缓存的ProjectContext加载
    - 测试 默认上下文创建（LLM失败时）

  **Must NOT do**:
  - 不要调用真实LLM API
  - 不要修改agent接口

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 核心业务逻辑，需要深入理解LangGraph工作流
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: 测试编写

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 10, 11, 13)
  - **Blocks**: Task 14
  - **Blocked By**: Task 3 (test infrastructure)

  **References**:
  **Pattern References**:
  - `python/src/codereview/agents/reviewer.py:102-450` — ReviewAgent完整实现
  - `python/src/codereview/agents/reviewer.py:231-253` — retry逻辑
  - `python/src/codereview/agents/reviewer.py:139-206` — review_files并发逻辑
  - `python/src/codereview/agents/analyzer.py` — ProjectAnalyzer完整实现

  **Test References**:
  - `python/tests/test_retry.py` — 现有retry测试（非常浅，只检查存在性）

  **Acceptance Criteria**:
  - [ ] `test_reviewer.py` 创建，包含8+个测试
  - [ ] `test_analyzer.py` 创建，包含4+个测试
  - [ ] `pytest python/tests/test_reviewer.py python/tests/test_analyzer.py -v` → ALL pass
  - [ ] 覆盖率 >80% for reviewer.py and analyzer.py

  **QA Scenarios**:
  ```
  Scenario: 并发review验证
    Tool: Bash (pytest)
    Steps:
      1. Mock LLM返回 (delay=0.1s)
      2. 创建10个DiffEntry
      3. 设置max_concurrency=3
      4. 验证同时最多3个并发调用
    Expected Result: 并发数不超过3
    Failure Indicators: 并发数>3或全部串行
    Evidence: .sisyphus/evidence/task-12-concurrency.txt

  Scenario: retry降级验证
    Tool: Bash (pytest)
    Steps:
      1. Mock LLM始终抛出TimeoutError
      2. 验证3次重试后返回降级结果
      3. 验证降级结果risk_level=MEDIUM
    Expected Result: 返回降级FileReview，标记为MEDIUM
    Failure Indicators: 未重试3次或抛出异常
    Evidence: .sisyphus/evidence/task-12-retry.txt

  Scenario: 覆盖率检查
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/test_reviewer.py python/tests/test_analyzer.py --cov=codereview.agents --cov-report=term-missing
    Expected Result: 覆盖率 >80%
    Failure Indicators: 覆盖率 <80%
    Evidence: .sisyphus/evidence/task-12-coverage.txt
  ```

  **Commit**: YES
  - Message: `test: add comprehensive tests for ReviewAgent and Analyzer`
  - Files: `python/tests/test_reviewer.py`, `python/tests/test_analyzer.py`
  - Pre-commit: `pytest python/tests/test_reviewer.py python/tests/test_analyzer.py -v`

- [x] 13. Models + Fixer + AutoMerger测试补全

  **What to do**:
  - 为 `models/__init__.py` 编写测试 `test_models.py`:
    - 测试所有Pydantic model的默认值
    - 测试 ConfigLLM temperature范围验证 (0.0-2.0)
    - 测试 CacheConfig ttl_days范围验证 (1-30)
    - 测试 RiskLevel/ReviewConclusion/MergeMethod枚举
    - 测试 FileIssue/FileReview/ReviewResult序列化
    - 测试 Config完整加载验证
  - 补全 `test_fixer.py` 中的测试:
    - 测试 apply_fix 成功/部分匹配/无匹配
    - 测试 fix预览格式化
    - 测试 多文件fix批量处理
  - 补全 `test_auto_merger.py` 中的测试:
    - 测试 merge条件组合 (minConfidence + maxSeverity + requireApproval)
    - 测试 merge方法选择 (squash/merge/rebase)
    - 测试 dry-run模式

  **Must NOT do**:
  - 不要修改model定义（只测试现有行为）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 多个模块的测试补全
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: 测试编写

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 10, 11, 12)
  - **Blocks**: Task 16
  - **Blocked By**: Task 3 (test infrastructure)

  **References**:
  **Pattern References**:
  - `python/src/codereview/models/__init__.py` — 所有Pydantic model定义
  - `python/src/codereview/core/fixer.py` — CodeFixer实现
  - `python/src/codereview/core/auto_merger.py` — AutoMerger实现

  **Test References**:
  - `python/tests/test_fixer.py` — 现有fixer测试
  - `python/tests/test_auto_merger.py` — 现有auto_merger测试

  **Acceptance Criteria**:
  - [ ] `test_models.py` 创建，包含6+个测试
  - [ ] `test_fixer.py` 新增3+个测试
  - [ ] `test_auto_merger.py` 新增3+个测试
  - [ ] `pytest python/tests/test_models.py python/tests/test_fixer.py python/tests/test_auto_merger.py -v` → ALL pass

  **QA Scenarios**:
  ```
  Scenario: Pydantic model验证
    Tool: Bash (pytest)
    Steps:
      1. 测试ConfigLLM(temperature=3.0) → ValidationError
      2. 测试CacheConfig(ttl_days=0) → ValidationError
      3. 测试CacheConfig(ttl_days=31) → ValidationError
    Expected Result: 无效值全部被Pydantic拒绝
    Failure Indicators: 无效值被接受
    Evidence: .sisyphus/evidence/task-13-models-validation.txt

  Scenario: 覆盖率检查
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/test_models.py --cov=codereview.models --cov-report=term-missing
    Expected Result: models/ 覆盖率 100%
    Failure Indicators: 覆盖率 <100%
    Evidence: .sisyphus/evidence/task-13-coverage.txt
  ```

  **Commit**: YES
  - Message: `test: add tests for Models, Fixer, AutoMerger`
  - Files: `python/tests/test_models.py`, `python/tests/test_fixer.py`, `python/tests/test_auto_merger.py`
  - Pre-commit: `pytest python/tests/test_models.py python/tests/test_fixer.py python/tests/test_auto_merger.py -v`

- [x] 14. LLM Provider fallback链

  **What to do**:
  - TDD RED: 先写测试 `test_llm_fallback.py`:
    - 测试 主Provider失败后自动切换到fallback Provider
    - 测试 所有Provider都失败时返回明确错误
    - 测试 fallback不改变review结果的质量
    - 测试 fallback日志记录 "Primary provider X failed, falling back to Y"
    - 测试 Config配置fallback链: `fallback_providers: [anthropic, deepseek]`
    - 测试 单个Provider超时触发fallback
  - TDD GREEN: 实现：
    - 在 `models/__init__.py` Config中添加 `fallback_providers: Optional[list[str]] = None`
    - 在 `core/llm.py` LLMFactory中添加:
      ```python
      def create_with_fallback(self, config: ConfigLLM, fallback_providers: Optional[list[str]] = None) -> BaseChatModel:
          """尝试主provider，失败则按序尝试fallback providers"""
          providers_to_try = [config.provider] + (fallback_providers or [])
          last_error = None
          for provider in providers_to_try:
              try:
                  return self.create(provider, config)
              except Exception as e:
                  logger.warning(f"Provider {provider} failed: {e}, trying next...")
                  last_error = e
          raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
      ```
    - 在 `reviewer.py` 中使用 `create_with_fallback()`
    - 在 `analyzer.py` 中使用 `create_with_fallback()`
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要无限重试（最多尝试所有配置的providers）
  - 不要静默fallback（必须记录日志）
  - 不要添加基于成本或延迟的智能路由

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要设计fallback策略，涉及多provider协调
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 15, 16)
  - **Blocks**: None
  - **Blocked By**: Tasks 10, 12 (LLM + Reviewer tests in place)

  **References**:
  **Pattern References**:
  - `python/src/codereview/core/llm.py:35-98` — 当前 `create()` 方法，需要扩展为支持fallback
  - `python/src/codereview/agents/reviewer.py` — 使用LLM的位置
  - `python/src/codereview/agents/analyzer.py` — 使用LLM的位置

  **API/Type References**:
  - `python/src/codereview/core/llm.py:LLMProvider` — Provider枚举
  - `python/src/codereview/models/__init__.py:ConfigLLM` — 现有LLM配置

  **Acceptance Criteria**:
  - [ ] `test_llm_fallback.py` 创建，包含6+个测试
  - [ ] Config支持 `fallback_providers` 字段
  - [ ] 主provider失败自动切换到fallback
  - [ ] 所有provider失败返回明确RuntimeError
  - [ ] `pytest python/tests/test_llm_fallback.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: 主provider失败 → fallback成功
    Tool: Bash (pytest)
    Steps:
      1. Mock OpenAI provider抛出ConnectionError
      2. Mock Anthropic provider返回成功
      3. 配置fallback_providers: ["anthropic"]
      4. 调用create_with_fallback()
    Expected Result: 返回Anthropic的chat model实例
    Failure Indicators: 抛出异常或返回None
    Evidence: .sisyphus/evidence/task-14-fallback-success.txt

  Scenario: 所有provider失败
    Tool: Bash (pytest)
    Steps:
      1. Mock 所有provider抛出异常
      2. 配置fallback_providers: ["anthropic", "deepseek"]
      3. 调用create_with_fallback()
    Expected Result: RuntimeError "All LLM providers failed"
    Failure Indicators: 静默返回None或空结果
    Evidence: .sisyphus/evidence/task-14-all-fail.txt

  Scenario: fallback日志验证
    Tool: Bash (pytest)
    Steps:
      1. Mock主provider失败
      2. 捕获日志输出
      3. 验证包含 "falling back to" 消息
    Expected Result: WARNING日志记录fallback过程
    Failure Indicators: 无fallback日志
    Evidence: .sisyphus/evidence/task-14-fallback-log.txt
  ```

  **Commit**: YES
  - Message: `feat(llm): implement provider fallback chain`
  - Files: `python/src/codereview/core/llm.py`, `python/src/codereview/models/__init__.py`, `python/src/codereview/agents/reviewer.py`, `python/src/codereview/agents/analyzer.py`, `python/tests/test_llm_fallback.py`
  - Pre-commit: `pytest python/tests/test_llm_fallback.py -v`

- [x] 15. Rate Limit检测与退避

  **What to do**:
  - TDD RED: 先写测试 `test_rate_limit.py`:
    - 测试 LLM API 429响应触发退避重试
    - 测试 退避使用Retry-After header值
    - 测试 无Retry-After header时使用指数退避
    - 测试 GitHub API 429响应触发退避
    - 测试 最大重试次数后放弃
    - 测试 退避期间日志记录 "Rate limited, waiting N seconds..."
  - TDD GREEN: 实现：
    - 创建 `core/rate_limiter.py`:
      ```python
      class RateLimitHandler:
          def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
              ...
          async def execute_with_retry(self, fn, *args, **kwargs):
              """带rate limit感知的重试包装器"""
              for attempt in range(self.max_retries):
                  try:
                      return await fn(*args, **kwargs)
                  except RateLimitError as e:
                      delay = self._get_delay(e, attempt)
                      logger.warning(f"Rate limited, waiting {delay:.1f}s...")
                      await asyncio.sleep(delay)
              raise RuntimeError(f"Max retries ({self.max_retries}) exceeded")
      ```
    - 在 `reviewer.py` 中包装LLM调用
    - 在 `github_client.py` 中添加429检测
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要使用固定间隔重试（必须使用指数退避）
  - 不要无限重试
  - 不要在退避期间阻塞其他并发请求

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 异步重试策略设计，涉及并发控制
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 14, 16)
  - **Blocks**: None
  - **Blocked By**: Task 11 (GitHub client tests in place)

  **References**:
  **Pattern References**:
  - `python/src/codereview/agents/reviewer.py:231-236` — 现有指数退避(2**attempt)，需要增强为rate-limit感知
  - `python/src/codereview/core/github_client.py:311-313` — 当前静默处理HTTPError，需要添加429检测

  **Acceptance Criteria**:
  - [ ] `test_rate_limit.py` 创建，包含6+个测试
  - [ ] `core/rate_limiter.py` 创建
  - [ ] LLM 429响应触发退避
  - [ ] GitHub API 429响应触发退避
  - [ ] `pytest python/tests/test_rate_limit.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: LLM rate limit退避验证
    Tool: Bash (pytest)
    Steps:
      1. Mock LLM返回429 (Retry-After: 2)
      2. 第2次调用成功
      3. 验证等待时间约2秒
    Expected Result: 退避约2秒后重试成功
    Failure Indicators: 立即重试或等待时间不对
    Evidence: .sisyphus/evidence/task-15-llm-ratelimit.txt

  Scenario: GitHub API rate limit退避验证
    Tool: Bash (pytest)
    Steps:
      1. Mock GitHub API返回429 (无Retry-After)
      2. 第2次调用成功
      3. 验证使用指数退避 (1s, 2s, 4s)
    Expected Result: 指数退避重试
    Failure Indicators: 固定间隔或不重试
    Evidence: .sisyphus/evidence/task-15-github-ratelimit.txt

  Scenario: 最大重试后放弃
    Tool: Bash (pytest)
    Steps:
      1. Mock 始终返回429
      2. 验证3次重试后抛出RuntimeError
    Expected Result: "Max retries (3) exceeded"
    Failure Indicators: 无限重试或静默失败
    Evidence: .sisyphus/evidence/task-15-max-retries.txt
  ```

  **Commit**: YES
  - Message: `feat(api): implement rate limit detection and backoff`
  - Files: `python/src/codereview/core/rate_limiter.py`, `python/src/codereview/agents/reviewer.py`, `python/src/codereview/core/github_client.py`, `python/tests/test_rate_limit.py`
  - Pre-commit: `pytest python/tests/test_rate_limit.py -v`

- [x] 16. 交互式fix选择模式

  **What to do**:
  - TDD RED: 先写测试 `test_interactive_fix.py`:
    - 测试 `--interactive` 标志启用交互模式
    - 测试 y/n/a (yes/no/all) 输入处理
    - 测试 'a' (all) 跳过后续所有确认
    - 测试 无效输入重新提示
    - 测试 fix预览显示：文件名、问题描述、建议修复
    - 测试 Ctrl+C (KeyboardInterrupt) 优雅退出
    - 测试 `--yes` 跳过交互直接应用
  - TDD GREEN: 实现：
    - 在 `cli.py` 的 fix 子命令添加 `--interactive` / `-i` 标志
    - 在 `core/fixer.py` 添加交互模式:
      ```python
      def interactive_fix(self, suggestions: list[FixSuggestion], apply: bool = False):
          """交互式选择要应用的fix"""
          apply_all = False
          for suggestion in suggestions:
              if apply_all:
                  yield suggestion, True
                  continue
              self._display_fix_preview(suggestion)
              choice = input("Apply this fix? [y/n/a/q]: ").lower().strip()
              if choice == 'a':
                  apply_all = True
                  yield suggestion, True
              elif choice == 'y':
                  yield suggestion, True
              elif choice == 'q':
                  break
              else:
                  yield suggestion, False
      ```
    - 添加 `_display_fix_preview()` 显示diff预览
  - TDD REFACTOR: 清理

  **Must NOT do**:
  - 不要添加TUI/全屏界面（纯CLI交互）
  - 不要修改现有 --apply / --dry-run 行为

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 交互式UX设计，需要考虑多种输入场景
  - **Skills**: [`test-driven-development`]
    - `test-driven-development`: TDD流程

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Tasks 14, 15)
  - **Blocks**: None
  - **Blocked By**: Task 13 (fixer tests in place)

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py:793-866` — 当前fix子命令，添加--interactive的位置
  - `python/src/codereview/core/fixer.py:318-373` — apply_fix()方法
  - `python/src/codereview/core/fixer.py:640-658` — generate_fix()方法

  **Acceptance Criteria**:
  - [ ] `test_interactive_fix.py` 创建，包含7+个测试
  - [ ] `--interactive` 标志可用
  - [ ] y/n/a/q 输入处理正确
  - [ ] fix预览显示文件名、描述、diff
  - [ ] `pytest python/tests/test_interactive_fix.py -v` → PASS

  **QA Scenarios**:
  ```
  Scenario: y/n交互验证
    Tool: Bash (pytest + input mock)
    Steps:
      1. 创建3个FixSuggestion
      2. Mock input() 返回 ['y', 'n', 'y']
      3. 验证第1和第3个被标记为apply
    Expected Result: 返回 [(s1, True), (s2, False), (s3, True)]
    Failure Indicators: 选择逻辑错误
    Evidence: .sisyphus/evidence/task-16-interactive.txt

  Scenario: 'a' (apply all) 验证
    Tool: Bash (pytest + input mock)
    Steps:
      1. 创建5个FixSuggestion
      2. Mock input() 返回 ['n', 'a']
      3. 验证第2-5个全部标记为apply
    Expected Result: [(s1, False), (s2, True), (s3, True), (s4, True), (s5, True)]
    Failure Indicators: 'a'后仍需确认
    Evidence: .sisyphus/evidence/task-16-apply-all.txt

  Scenario: Ctrl+C优雅退出
    Tool: Bash (pytest)
    Steps:
      1. Mock input() 抛出KeyboardInterrupt
      2. 验证不crash，已确认的fix仍被应用
    Expected Result: 优雅退出，部分应用
    Failure Indicators: unhandled KeyboardInterrupt
    Evidence: .sisyphus/evidence/task-16-ctrl-c.txt
  ```

  **Commit**: YES
  - Message: `feat(cli): implement interactive fix selection mode`
  - Files: `python/src/codereview/cli.py`, `python/src/codereview/core/fixer.py`, `python/tests/test_interactive_fix.py`
  - Pre-commit: `pytest python/tests/test_interactive_fix.py -v`

- [x] 17. 手动Lint修复 + 类型标注完善

  **What to do**:
  - 修复 `ruff check --fix` 无法自动修复的剩余lint错误:
    - 修复LSP类型错误（LangGraph StateGraph类型兼容性等）
    - 为使用 `Any` 的位置添加具体类型
    - 为缺少docstring的公共API添加Google-style docstring
    - 修复 `Optional[X]` 应为 `X | None`（仅在Python 3.10+环境中，或保持Optional兼容3.9）
    - 修复中英文混合问题 (cli.py:879-999)
  - 特别关注:
    - `cli.py` 149个LSP类型错误
    - `analyzer.py` / `reviewer.py` LangGraph StateGraph类型不兼容
    - `cache.py` tomli import问题
    - `config.py` 返回类型不匹配

  **Must NOT do**:
  - 不要改变业务逻辑
  - 不要做Python版本不兼容的改动（保持3.9+兼容）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要深入理解类型系统和LSP错误
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (partially)
  - **Parallel Group**: Wave 6 (with Task 18)
  - **Blocks**: Task 18
  - **Blocked By**: Task 2 (auto-fix done), all feature tasks (avoid conflicts)

  **References**:
  **Pattern References**:
  - `python/src/codereview/cli.py` — 149个LSP类型错误
  - `python/src/codereview/agents/analyzer.py:184-197` — LangGraph类型不兼容
  - `python/src/codereview/agents/reviewer.py:432-445` — LangGraph类型不兼容
  - `python/src/codereview/core/cache.py:19` — tomli import
  - `python/src/codereview/core/config.py:93` — 返回类型不匹配
  - `python/src/codereview/cli.py:879-999` — 中英文混合输出

  **Acceptance Criteria**:
  - [ ] `ruff check python/src/` → 0 errors
  - [ ] LSP错误显著减少
  - [ ] 所有公共函数有docstring
  - [ ] `Any` 使用减少到最低必要
  - [ ] 中英文输出统一为英文

  **QA Scenarios**:
  ```
  Scenario: Lint零错误
    Tool: Bash (ruff)
    Steps:
      1. ruff check python/src/ 2>&1
    Expected Result: 0 errors found
    Failure Indicators: 任何lint错误
    Evidence: .sisyphus/evidence/task-17-lint-clean.txt

  Scenario: 类型检查改进
    Tool: Bash (mypy)
    Steps:
      1. mypy python/src/ --no-error-summary 2>&1 | wc -l
    Expected Result: 错误数比基线显著减少
    Failure Indicators: 错误数未减少或增多
    Evidence: .sisyphus/evidence/task-17-mypy.txt
  ```

  **Commit**: YES
  - Message: `chore: fix remaining lint errors and improve type hints`
  - Files: multiple files
  - Pre-commit: `ruff check python/src/ && mypy python/src/`

- [x] 18. conftest.py共享fixtures + 测试基础设施

  **What to do**:
  - 创建 `python/tests/conftest.py` 包含共享fixtures:
    - `sample_config()` — 标准测试Config对象
    - `sample_diff_entry()` — 标准DiffEntry对象
    - `sample_file_review()` — 标准FileReview对象
    - `sample_review_result()` — 标准ReviewResult对象
    - `mock_llm()` — Mock LLM provider
    - `mock_github_client()` — Mock GitHub client
    - `temp_cache_dir()` — 临时缓存目录
    - `sample_owasp_rules()` — 规则引擎示例
  - 添加 `pytest.ini` 或更新 `pyproject.toml` pytest配置:
    - 设置testpaths
    - 添加markers (slow, integration)
    - 添加coverage配置
  - 重构现有测试文件使用共享fixtures（可选，低优先）

  **Must NOT do**:
  - 不要删除现有测试中的inline fixtures（除非明显重复）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 主要是创建fixtures文件，模式固定
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6 (sequential after Task 17)
  - **Blocks**: None
  - **Blocked By**: Task 17

  **References**:
  **Pattern References**:
  - `python/tests/test_cache.py` — inline fixtures模式（tempfile使用）
  - `python/tests/test_auto_merger.py` — AsyncMock使用模式
  - `python/tests/test_report_generator.py` — fixtures for sample data

  **Acceptance Criteria**:
  - [ ] `python/tests/conftest.py` 创建
  - [ ] 包含8+个共享fixtures
  - [ ] `pytest python/tests/ --collect-only` → 无error
  - [ ] `pytest python/tests/ -v` → ALL pass

  **QA Scenarios**:
  ```
  Scenario: conftest.py加载验证
    Tool: Bash (pytest)
    Steps:
      1. 创建一个使用共享fixture的简单测试
      2. pytest python/tests/test_fixture_check.py -v
    Expected Result: fixture正确加载，测试通过
    Failure Indicators: fixture not found
    Evidence: .sisyphus/evidence/task-18-conftest.txt

  Scenario: 全量测试最终验证
    Tool: Bash (pytest)
    Steps:
      1. pytest python/tests/ -v --tb=short 2>&1
    Expected Result: ALL pass
    Failure Indicators: FAILED or ERROR
    Evidence: .sisyphus/evidence/task-18-final-tests.txt
  ```

  **Commit**: YES
  - Message: `test: add shared test fixtures and conftest.py`
  - Files: `python/tests/conftest.py`, `python/pyproject.toml`
  - Pre-commit: `pytest python/tests/ --collect-only`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `ruff check python/src/` + `mypy python/src/` + `pytest python/tests/ -v`. Review all changed files for: bare except, empty catches, console.log in prod, commented-out code, unused imports, AI slop patterns. Verify type hints on all new functions.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute key QA scenarios: `--version`, `--list-rules`, `--disable-rule`, `--clear-cache`, `--verbose`, `--quiet`, a multi-file review with progress bar, trigger LLM failure to test fallback. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect scope creep: tasks adding unrequested features. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `fix(cli): fix len() bug in fix preview display` — cli.py
- **Wave 1**: `chore: auto-fix lint errors with ruff` — multiple files
- **Wave 1**: `fix(tests): fix test collection error + add tqdm dependency` — pyproject.toml, tests/
- **Wave 2**: `feat(cli): add --version, --clear-cache, --log-level flags` — cli.py, tests/
- **Wave 2**: `feat(config): make core parameters configurable` — config.py, models/, tests/
- **Wave 2**: `fix(core): improve error handling and add context to errors` — core/, agents/, tests/
- **Wave 3**: `feat(rules): add --list-rules and --disable-rule CLI flags` — cli.py, rules/, tests/
- **Wave 3**: `feat(ui): add tqdm progress bars for long operations` — agents/, cli.py, tests/
- **Wave 3**: `feat(cli): add --verbose/--quiet logging control` — cli.py, tests/
- **Wave 4**: `test: add comprehensive tests for LLM Factory and Config` — tests/
- **Wave 4**: `test: add comprehensive tests for GitHub Client` — tests/
- **Wave 4**: `test: add comprehensive tests for ReviewAgent and Analyzer` — tests/
- **Wave 4**: `test: add tests for Models, Fixer, AutoMerger` — tests/
- **Wave 5**: `feat(llm): implement provider fallback chain` — core/llm.py, tests/
- **Wave 5**: `feat(api): implement rate limit detection and backoff` — core/, agents/, tests/
- **Wave 5**: `feat(cli): implement interactive fix selection mode` — cli.py, core/fixer.py, tests/
- **Wave 6**: `chore: fix remaining lint errors and improve type hints` — multiple files
- **Wave 6**: `test: add shared test fixtures and conftest.py` — tests/

---

## Success Criteria

### Verification Commands
```bash
# Lint
ruff check python/src/          # Expected: 0 errors
ruff format --check python/src/ # Expected: 0 errors

# Type check
mypy python/src/                # Expected: 0 errors (stretch goal)

# Tests
pytest python/tests/ -v         # Expected: ALL pass
pytest python/tests/ --cov=codereview --cov-report=term-missing  # Expected: >80% on core modules

# CLI smoke tests
python -m codereview.cli --version                    # Expected: version string
python -m codereview.cli --list-rules                 # Expected: 30 rules listed
python -m codereview.cli --list-rules --json          # Expected: valid JSON array
python -m codereview.cli --disable-rule OWASP-A01-001 --diff '...'  # Expected: skips rule
python -m codereview.cli --clear-cache --yes          # Expected: cache cleared
python -m codereview.cli --verbose --diff '...'       # Expected: DEBUG logs visible
python -m codereview.cli --quiet --diff '...'         # Expected: minimal output
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass (480 passed)
- [x] ruff check zero errors (UP045 ignored for Python 3.9 compat)
- [x] Core module test coverage >80%
- [x] CLI --version works
- [x] CLI --list-rules works
- [x] CLI --disable-rule works
- [x] No silent failures remain
- [x] tqdm progress bar visible during multi-file review
- [x] LLM fallback chain tested
- [x] Rate limit handling tested
- [x] Interactive fix mode works

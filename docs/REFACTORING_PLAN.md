# CodeReview Agent 重构技术方案

> 评审基线:`HEAD = e798d43`(2026-08-05 拉取最新代码)
> 评审方法:参考 [mattpocock/skills · code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md) 的双轴评审法 ——
> **Standards 轴**(是否遵守本仓库文档化标准 `AGENTS.md` + Fowler《重构》第 3 章坏味道基线)与
> **Spec 轴**(是否符合 `docs/DESIGN.md` 设计意图、是否存在逻辑缺陷),两条轴独立报告、不合并排序。
>
> 质量基线(评审时实测):`554 tests passed` · `ruff check` 全绿 · `mypy` 9 errors(3 个文件)

---

## 1. 现状盘点

| 区域 | 行数 | 主流程是否接线 |
|---|---|---|
| `cli.py` | 1751 | ✅(review / fix / merge 三命令全在一个文件) |
| `agents/reviewer.py` | 777 | ✅ 核心审查流程 |
| `agents/analyzer.py` | 274 | ✅ 项目分析 |
| `core/llm.py` `cache.py` `config.py` `fixer.py` `github_client.py` `auto_merger.py` `path_matcher.py` | ~3400 | ✅ |
| `rules/__init__.py` + `owasp_rules.yaml` | 289 | ✅ 静态规则引擎 |
| `output/generator.py` | 134 | ✅ |
| `core/report_generator.py` | 1062 | ❌ **无任何调用方** |
| `core/complexity_scorer.py` | 546 | ❌ **无任何调用方** |
| `core/team_insights.py` | 567 | ❌ **无任何调用方** |
| `core/history_tracker.py` | 585 | ❌ **无任何调用方** |
| `core/languages/*`(7 种语言分析器) | ~2438 | ❌ **只被自身引用,主流程从未 import** |
| `github_app.py` | 132 | ❌ 未被 action/CLI 引用 |

**结论:约 5300 行(全量源码 ~9500 行的 55%)是未接线的孤立代码**,只有测试文件在引用它们——测试在为死代码提供"存活性假象"。

---

## 2. Spec 轴评审发现(对照 DESIGN.md 与功能正确性)

DESIGN.md 定义的核心引擎是 **Context Analyzer / Rule Engine / Review Agent** 三件套 + 三种交付形态。以下为判定为缺陷或偏差的事项:

| # | 严重度 | 位置 | 问题 |
|---|---|---|---|
| S1 | 🔴 高 | `core/languages/*`、`report_generator.py`、`complexity_scorer.py`、`team_insights.py`、`history_tracker.py`、`github_app.py` | **约 55% 代码未接入主流程**,与 DESIGN.md 的三件套架构不符;属于 Speculative Generality 的规模化形态 |
| S2 | 🔴 高 | `cli.py:1296-1331` | **`main_fix` 的确认提示在 `run_fix` 已经应用修复之后才弹出**——`run_fix(apply=True)` 内部已写盘,事后再问 "Confirm applying?" 毫无意义,取消也无法回滚。交互逻辑 bug |
| S3 | 🔴 高 | `cli.py:1004-1006` | **`--min-risk high` 过滤失效**: `if issue.risk_level.value in [min_risk, "high", "medium"]` + `if ... in ("high","medium")` 的组合使 medium 问题在 `--min-risk high` 下依然被纳入修复范围 |
| S4 | 🟡 中 | `core/config.py:129-177` | **示例配置与 Pydantic 模型字段不一致**:示例写 `cache.ttl`(模型为 `ttl_days`)、`customPrompt`(模型为 `custom_prompt_path`)。`Config` 未设 `extra="forbid"`,用户照抄示例后配置被**静默丢弃** |
| S5 | 🟡 中 | `cli.py:795` | 注释引用 `--apply-auto-merge` 标志,但该 flag 在 argparse 中**不存在**;review 路径的 auto-merge 永远 dry-run,功能半成品 |
| S6 | 🟡 中 | `agents/reviewer.py:92-102` | `OrchestratorState(dict)` 伪装 TypedDict:mypy 报 9 个错误中 7 个源于此;且 `file_reviews: list[FileReview] = []` 是**类级可变默认值**,LangGraph 状态合并语义不明确 |
| S7 | 🟡 中 | `cli.py:401-409` | 用 `type("CacheInfo", (), {...})()` 动态类冒充 `CacheInfo` Pydantic 模型赋给 `result.cache_info`,绕过类型系统,`model_dump()` 序列化行为不受控 |
| S8 | 🟢 低 | `cli.py:1473` | `print('"   +++ Fixed')` 字符串内混入多余引号,输出瑕疵 |
| S9 | 🟢 低 | `cli.py:905` | `run_fix` 的 `output_path` 参数声明后从未在函数体内使用 |
| S10 | 🟢 低 | `pyproject.toml` | `requires-python = ">=3.10"` 但 ruff `target-version = "py39"`,工具链口径不一致 |

---

## 3. Standards 轴评审发现(AGENTS.md + Fowler 坏味道基线)

> 依据规则:仓库文档化标准优先于坏味道基线;基线条目均为 judgement call。

### 3.1 违反 AGENTS.md 文档化标准(硬违规)

| # | 位置 | 违规 |
|---|---|---|
| A1 | `cli.py:147-161` | `get_version` 两处 `except Exception: pass` 静默吞异常,违反"Never bare except / catch specific exceptions / log appropriately" |
| A2 | `agents/reviewer.py:198-204, 624-630` | `llm: Any`、`rule_engine: Optional[Any]`、`file_cache: Optional[Any]` —— 核心类的关键依赖全部放弃类型标注,违反"Type Hints required" |
| A3 | 全仓 | 类型风格混用:同一函数签名内 `str \| Path \| None` 与 `Optional[list[str]]` 并存(`cli.py:293-305`),AGENTS.md 明文要求 `Optional[X]`,但代码实际已迁移 PEP 604 且 `requires-python>=3.10` —— **标准文档与代码现实脱节,需二选一统一** |
| A4 | `pyproject.toml` | ruff `target-version = "py39"` 与 `requires-python = ">=3.10"` 矛盾(同 S10,属标准一致性问题) |

### 3.2 Fowler 坏味道(judgement calls)

| # | 坏味道 | 位置 | 说明 |
|---|---|---|---|
| B1 | **Long Module / Divergent Change** | `cli.py`(1751 行) | 一个文件承担 6 种变更理由:argparse 定义、diff 解析、review 编排、fix 编排、merge 编排、终端富文本格式化(`_print_fix_output` 等约 400 行 emoji 打印逻辑) |
| B2 | **Duplicated Code** | `cli.py:88-109` | `_classify_error` 与 `_exit_code_for_error` 使用同一套关键词列表做两次匹配 |
| B3 | **Duplicated Code** | 三处 | 语言检测表 3 份拷贝且内容互不一致:`cli.py:1229`、 `reviewer.py:590`、`core/languages/__init__.py:24` |
| B4 | **Duplicated Code** | `rules/__init__.py:101-139` | `_load_yaml_rules` 与 `_load_json_rules` 除解析器外逐行相同 |
| B5 | **Duplicated Code** | `core/cache.py` | TTL 过期判定逻辑在 `get` / `get_stats` / `cleanup_expired` / `CacheManager.load` 重复 4 次 |
| B6 | **Duplicated Code** | `core/llm.py:255-309` | `_invoke_fallback_chain` 与 `_ainvoke_fallback_chain` 同步/异步两份镜像;`_create_openai` 与 `_create_compatible` 近乎相同 |
| B7 | **Speculative Generality** | `core/llm.py:312-376` | `is_rate_limit_error` / `get_retry_after_delay` / `get_backoff_delay` 定义后**全仓无调用**;`cache.py:400` `VersionDetector` 仅自引用;`llm.py:155-175` `create_with_fallback` 的 `attempt>0` 分支为死路径;`rules/__init__.py:279` 模块级 `disable_rules` 创建一次性 engine 后即丢弃 |
| B8 | **Middle Man / 过度设计** | `agents/reviewer.py:644-665` | LangGraph 三节点**线性**图(prepare→review→calculate)无任何分支/条件边,图框架只增加样板;`_FallbackChainLLM` 手写重试包装,而 LangChain 原生 `with_fallbacks()` 已实现同语义 |
| B9 | **Repeated Switches** | `core/llm.py:51-63` | `LLMFactory.create` 对 provider 的 if/elif 级联,新增 provider 需改多处(配合 DEFAULT_MODELS/BASE_URLS 两张表 → Shotgun Surgery) |
| B10 | **Primitive Obsession** | `rules/__init__.py:37-64` ↔ `reviewer.py:404-477` | 静态分析结果以 `list[dict]` 在引擎与 Agent 间传递,靠 `.get()` 取字段;`severity` 用裸 `str` 而非既有 `RiskLevel` 枚举;`DetectionRule` 用 dataclass 而全仓其余模型均为 Pydantic |
| B11 | **Mysterious Name(遮蔽)** | `cli.py:904, 1554` | `run_fix` / `run_merge` 的形参 `json: bool` 遮蔽标准库 `json` 模块 |
| B12 | **不一致的策略** | `reviewer.py:583-588` | 关键路径用 `startswith` 前缀匹配,而排除规则用 `ExcludeMatcher`(gitignore 语义)——同"路径匹配"两件事两套语义 |
| B13 | **不一致的策略** | `core/cache.py` | `CacheManager.save` 原子写(tmp+replace),`FileReviewCache.save` 直接写——进程中断可留半个 JSON |

---

## 4. 重构目标与原则

**目标**
1. 代码量与主流程匹配:死代码清零或明确接线,源码从 ~9500 行收敛到 ~5000-6000 行
2. mypy 错误 9 → 0 并纳入 CI 强制;ruff/测试保持全绿
3. 修复 S2/S3 两个用户可见的逻辑 bug
4. 每个模块只有一个变更理由,核心依赖全部有类型

**原则**
- 全程以 `554 tests` 为安全网,**先补关键行为测试再动结构**(尤其 fix 流程)
- 小步快走:每个阶段独立 PR,可随时中断
- 删除优于注释保留:死代码直接从 git 历史可恢复,不留 `legacy/` 目录
- 文档与代码同步改(AGENTS.md、示例配置、DESIGN.md)

---

## 5. 分阶段实施方案

### P0 — 逻辑 bug 修复(不改结构,1 个 PR)

| 任务 | 文件 | 验证 |
|---|---|---|
| 修复确认时序:把确认 prompt 移到 `run_fix` 应用修复**之前**(或改为 `--yes` 跳过、默认 dry-run 需显式 `--apply`) | `cli.py` | 新增测试:apply 路径在确认拒绝时不写盘 |
| 修复 `--min-risk` 过滤:改为 `RiskLevel` 枚举序比较(`level_order[issue.risk] >= level_order[min_risk]`) | `cli.py:1004-1006` | 参数化测试覆盖 high/medium/low 三档 |
| `OrchestratorState` 改为 `TypedDict`(消除 7 个 mypy 错误) | `reviewer.py:92` | mypy 该文件清零 |
| `result.cache_info` 改用真正的 `CacheInfo` 模型 | `cli.py:401` | 现有 cache 测试 |
| 删掉多余引号、移除未使用的 `output_path` 形参、实现或删除 `--apply-auto-merge` | `cli.py` | ruff |

### P1 — 死代码清除(1 个 PR,删除 ~5300 行源码 + 对应测试)

1. 删除未接线模块:`core/languages/`、`core/report_generator.py`、`core/complexity_scorer.py`、`core/team_insights.py`、`core/history_tracker.py`、`github_app.py`,以及 `core/__init__.py` 中对应的 lazy-export 分支
2. 删除 `llm.py` 三个未用工具函数、`cache.py` 的 `VersionDetector`、`rules/__init__.py` 模块级 `disable_rules`
3. 同步删除 `tests/test_complexity_scorer.py` 等对应测试文件
4. **决策点**:若 `team_insights` / `history_tracker` 属于产品路线图,则改为在 DESIGN.md 补接线计划并排期,而不是保留僵尸代码
5. 预期:测试数从 554 降至 ~400,但全部测试都对应活代码

### P2 — 结构拆分(2-3 个 PR)

**P2a:拆分 `cli.py`(1751 → 约 5 个模块)**
```
python/src/codereview/cli/
├── __init__.py        # cli() 调度 + main 入口
├── review_cmd.py      # run_review + main
├── fix_cmd.py         # run_fix + main_fix(交互确认前置)
├── merge_cmd.py       # run_merge + main_merge
├── diff_parser.py     # get_git_diff / parse_git_diff_to_entries / _parse_diff
├── errors.py          # 错误分类 + 退出码(合并 _classify_error/_exit_code_for_error)
└── console.py         # 所有 emoji 富文本打印(_print_fix_output 等)
```

**P2b:`rules/__init__.py`(289 行)拆分为包**
```
rules/
├── __init__.py        # 仅 re-export 公共 API
├── models.py          # DetectionRule(改 Pydantic,severity 用 RiskLevel)+ DetectedIssue 模型
├── loader.py          # 统一 YAML/JSON 加载(合并 B4)
└── engine.py          # RuleEngine
```

**P2c:`models/__init__.py` 按域拆分**(`models/review.py`、`models/config.py`、`models/diff.py`),消除 `ReviewResult` 对后置定义 `CacheInfo` 的前向引用顺序问题。

### P3 — 去重与抽象(2 个 PR)

1. **统一语言检测**:保留一份 `EXTENSION_TO_LANGUAGE`(放 `core/language.py`),cli/reviewer/languages(若保留)全部引用
2. **静态分析结果模型化**:`rule.match()` 返回 `list[DetectedIssue]`(Pydantic),reviewer 不再 `.get()` 取字典(B10)
3. **LLM 工厂改注册表**:`PROVIDER_SPECS: dict[LLMProvider, ProviderSpec]`(默认模型、base_url、构造函数),消除 if/elif 级联(B9);fallback 优先评估替换为 LangChain `with_fallbacks()`,保留则合并 sync/async 双份逻辑(B6/B8)
4. **缓存 TTL 判定提取** `_is_expired(cached_at)` 单点实现;`FileReviewCache.save` 改原子写对齐 `CacheManager.save`(B5/B13)
5. **路径匹配统一**:`critical_paths` 复用 `ExcludeMatcher` 的 gitignore 语义(B12)
6. **评审流程去 LangGraph 化**(可选但推荐):线性三节点改为 `async def run_review` 顺序调用,移除 `StateGraph` 依赖与 `OrchestratorState`;若未来确需分支编排再引入——消除 B8 与 S6 的根基

### P4 — 类型与工具链收紧(1 个 PR)

1. `mypy` 清零后加入 CI 强制(当前 CI 只跑 ruff+pytest)
2. 核心类依赖去 `Any`:`llm: BaseChatModel`、`rule_engine: Optional[RuleEngine]`、`file_cache: Optional[FileReviewCache]`(A2)
3. **类型风格统一**:鉴于 `requires-python>=3.10` 且代码已用 PEP 604,建议**修订 AGENTS.md** 将标准改为 `X | None`,并设 ruff `target-version = "py310"`(A3/A4);若坚持 `Optional[X]` 则反向统一代码——二选一,不允许继续混用
4. `Config` 等用户输入模型设 `model_config = ConfigDict(extra="forbid")`,让 S4 类配置错误**显式报错而非静默丢弃**;同步修正示例配置字段名
5. `DetectionRule.severity` 收敛到 `RiskLevel` 枚举,删除字符串严重度
6. 修 `get_version` 的静默 `except Exception: pass`(A1)

---

## 6. 里程碑与工作量估算

| 阶段 | 内容 | 预估 | 风险 |
|---|---|---|---|
| M1 | P0 逻辑修复 + 补测试 | 0.5-1 天 | 低 |
| M2 | P1 死代码清除 | 0.5 天 | 低(需产品确认 S1 决策点) |
| M3 | P2 结构拆分 | 1-2 天 | 中(导入路径变动,需全量回归) |
| M4 | P3 去重抽象 | 2-3 天 | 中(LLM fallback 行为需对拍测试) |
| M5 | P4 工具链收紧 | 1 天 | 低 |

**每阶段验收门禁:`pytest` 全绿 + `ruff check` 全绿 + `mypy` 不劣化(M5 起要求清零)。**

## 7. 主要风险与对策

| 风险 | 对策 |
|---|---|
| P1 误删"将来要用"的模块 | 删除前在 PR 描述中列清单请 owner 确认;git 历史可恢复 |
| fix 流程测试薄弱,改确认时序引入回归 | P0 先补"确认拒绝 → 文件不变"的行为测试再改实现 |
| LLM fallback 语义在替换 `with_fallbacks()` 时漂移 | 保留 `_FallbackChainLLM` 作为对照,用 `tests/test_llm_fallback.py` 做行为对拍后再切换 |
| CLI 输出格式被外部 AI agent 依赖(schema_version 等) | console 层抽离时保持 JSON 输出字段逐字不变,用 `test_agent_friendly.py` 兜底 |

---

## 8. 双轴评审总结

- **Standards 轴**:13 项发现(4 项文档化标准硬违规 + 9 项坏味道 judgement calls);最严重为 **B1**(`cli.py` 1751 行 Long Module,6 种变更理由交织)。
- **Spec 轴**:10 项发现;最严重为 **S1**(约 55% 源码未接线,与 DESIGN.md 架构不符)与 **S2**(fix 确认时序逻辑 bug,确认流于形式)。

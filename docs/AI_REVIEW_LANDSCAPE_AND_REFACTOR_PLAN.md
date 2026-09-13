# AI Code Review 业界方案调研与 crAgent 重构计划

> 调研日期:2026-09-13
> 代码基线:`python/` 包 554 tests 全绿(实测,21.45s);源码 ~12,300 行,其中约 55% 未接线(详见 [REFACTORING_PLAN](REFACTORING_PLAN.md "citation"))
> 本文档分两部分:**Part 1 业界成熟方案调研** · **Part 2 本项目重构计划**

---

# Part 1 · 业界成熟方案调研

## 1.1 市场格局(2026)

AI 代码评审已从"LLM 读 diff 写评论"的玩具阶段进入成熟期,头部产品分化出三条清晰路线:

| 产品 | 路线 | 检出率(独立基准) | 误报 | 平台覆盖 | 定价 |
|---|---|---|---|---|---|
| **CodeRabbit** | 精度优先:LLM + 40+ 确定性 linter/SAST 过滤噪声 | ~44-46% | 最低(~2 FP/run,Signal65 精度 95.88%) | GitHub/GitLab/Bitbucket/Azure DevOps(唯一四家全覆盖) | $24-48/seat |
| **Greptile** | 召回优先:全库图索引 + agent swarm | ~82-85% | 最高(~11 FP/run) | GitHub/GitLab | $30/seat + credits |
| **Qodo**(原 CodiumAI) | 多智能体 + 开源核心(PR-Agent) | F1 60.1%(8 工具基准第一,recall 56.7%) | 可配置 | 四家全覆盖 | 免费层 / $19-30 |
| **GitHub Copilot Review** | 平台捆绑,diff-only;2026-03 起支持 agentic 跨文件探索 | ~54% | 中等 | 仅 GitHub | 随 Copilot $10-39 |
| **Cursor Bugbot** | 速度+精度:多轮 diff + 仓库上下文,~90s 出结果 | ~58% | 极低(精度 95.95%) | GitHub/GitLab | 按次 ~$1-1.5 |
| **Sourcery / Kodus Kody / Graphite Agent** | 细分:IDE 实时 / 开源自托管 / stacked-PR 工作流 | — | — | 各异 | $10-24 |

来源:[PromptQuorum](https://www.promptquorum.com/prompt-engineering/ai-code-review "citation") · [screencli 基准对比](https://screencli.sh/blog/best-ai-pr-review-tools-2026 "citation") · [getoptimal 9 工具横评](https://getoptimal.ai/blog/best-ai-code-review-tools "citation") · [Qodo 2.0 架构](https://aicodereview.cc/blog/qodo-vs-coderabbit/ "citation")

**开源/自托管阵营**(与本项目定位最相关):

- **PR-Agent(Qodo)** — 最强开源选项,Apache 2.0,已捐赠社区;LiteLLM 路由任意模型(含本地 Ollama),PR Compression 策略处理超大 diff,单命令 30 秒一次 LLM 调用。11k+ stars。[appsecmaster](https://www.appsecmaster.net/blog/best-ai-code-review/ "citation"), [wenexgensolutions](https://wenexgensolutions.com/compare/coderabbit-vs-qodo/ "citation")
- **Kodus Kody** — AGPL-3.0,自然语言自定义规则,从团队反馈学习,BYOK 零 token 加价。[qodo.ai](https://www.qodo.ai/blog/ai-code-review/ "citation")
- **OpenCodeReview(阿里)** — 混合架构代表:**确定性流水线先做筛选和规则检查,LLM 只裁决剩下的**——precision over recall。[tomrochette](https://tomrochette.com/agents/ "citation")
- **code-graph-rag** — Tree-sitter 多语言解析 → 知识图谱(Memgraph)→ Cypher 检索,开源的"全库上下文"参考实现。[GitHub](https://github.com/vitali87/code-graph-rag "citation")

## 1.2 关键结论:成熟方案的五个架构共识

### 共识 1:diff-only 单 prompt 已死,全库上下文是分水岭

独立基准反复证明:只读 diff 的工具(Copilot Review、CodeRabbit 基础模式)检出率天花板 ~45-55%;索引全库的 Greptile 达 82-85%。**最重要的差异化不是模型,而是上下文窗口里装了什么。** [getoptimal](https://getoptimal.ai/blog/best-ai-code-review-tools "citation")

Greptile 的全库上下文实现(事实上的行业标准做法):

```
源码 → Tree-sitter/AST 解析 → 函数/类/依赖图
     → 递归生成 docstring → embedding
     → 混合检索 = 向量相似 + 关键词 + agentic search(agent 沿引用链追踪)
PR 评审时:diff → 沿图向外追踪 caller/被改函数的依赖方/git history → 注入上下文
```

来源:[Greptile 官方文档](https://www.greptile.com/docs/introduction "citation") · [Hatchet 案例](https://hatchet.run/customers/greptile "citation") · [Launch HN](https://bestofai.com/article/launch-hn-greptile-yc-w24-rag-on-codebases-that-works "citation")

### 共识 2:确定性工具与 LLM 分层,而不是 LLM 包打天下

- CodeRabbit 把 40+ linter/SAST(Biome、ESLint、Ruff、golangci-lint、TruffleHog、Trivy)放在 LLM **之下**做噪声过滤,换来全场最低误报。[screencli](https://screencli.sh/blog/best-ai-pr-review-tools-2026 "citation")
- GitHub 在 Universe 2025 把 Copilot Review 重构为 LLM 推理 + 确定性 ESLint/CodeQL 融合。[Dabl Club](https://dablclub.com/research/tenki "citation")
- 阿里 OpenCodeReview:确定性流水线决定"什么值得给 LLM 看"。

**模式:静态分析做召回兜底和噪声闸门,LLM 只做需要推理的裁决。**

### 共识 3:多智能体专门化 > 单 prompt 全知视角

Qodo 2.0(2026-02)用并行专门 agent(bug 检测 / 质量与可维护性 / 安全 / 测试覆盖缺口)拿下基准 F1 第一;Greptile v3 用 agent swarm 带搜索工具循环追踪嵌套调用。单 LLM 调用是"单镜头盲区"——一个视角必然漏掉其他维度。[aicodereview.cc](https://aicodereview.cc/blog/qodo-vs-coderabbit/ "citation"), [niteagent](https://niteagent.com/blog/building-ai-code-review-agent/ "citation")

典型编排:Orchestrator(收 PR 载荷 → 装配上下文 → 分发)→ 专门 agent(各自带工具:SAST、依赖扫描、grep/AST 读取)→ 合成器(去重、排序、置信度打分)。

### 共识 4:噪声治理是生死线,反馈学习是护城河

- 2026 独立基准(c-CRAB、CR-Bench):顶级 agent 误报率 40-70%;真实世界研究显示开发者拒绝 56.3% 的 AI 评论;**评论接受率低于 ~30% 时工具在做负功**。[screencli](https://screencli.sh/blog/best-ai-pr-review-tools-2026 "citation")
- 头部产品的对策:每条发现带置信度分 + 高置信阈值 + 👍/👎 反馈学习(Greptile 称 2-3 周后停止评论团队不在乎的东西)+ 自然语言 house rules。[Greptile docs](https://www.greptile.com/docs/introduction "citation")

### 共识 5:评审的终点是修复,闭环交给 coding agent

Greptile 每条评论带 "Fix with your Agent" 按钮(把文件路径、行号、建议代码直接发给 Claude Code/Codex/Cursor/Devin);Copilot Review 可交接给 Copilot coding agent 开修复 PR。评审工具本身越来越聚焦"发现",修复交给通用 agent。[Greptile docs](https://www.greptile.com/docs/introduction "citation")

**边缘趋势(尚未成为标配)**:运行时验证——Greptile TREX 自动写并执行测试验证 PR 行为;screencli 在真实浏览器里跑 preview deploy。静态工具的共同盲区是"从不运行代码"。

## 1.3 对本项目的启示对照表

| 业界共识 | crAgent 现状 | 差距 |
|---|---|---|
| 全库上下文索引 | 仅把 diff + 项目级 `ProjectContext` 摘要喂给 LLM | 🔴 无 AST/图索引,跨文件影响分析缺失 |
| 确定性+LLM 分层 | 有 OWASP 静态规则引擎,但与 LLM 评审**并列**而非**分层过滤** | 🟡 规则结果直接进 prompt,无噪声闸门 |
| 多智能体专门化 | 单次 LLM 调用全维度评审(LangGraph 线性三节点,无分支) | 🔴 线性图是伪编排(REFACTORING_PLAN B8) |
| 噪声治理/反馈学习 | 置信度评分有(按严重度加权),但无反馈回路、无接受率追踪 | 🟡 有评分无学习 |
| 评审→修复闭环 | 有 `fix` 命令(自研修复器) | 🟢 方向正确,但应优先对接外部 coding agent |
| 运行时验证 | 无 | ⚪ 可作远期差异化 |

**本项目已有的差异化资产(不要丢)**:Agent 友好 CLI(结构化 JSON + 语义退出码 + schema_version)、6 家 LLM 含国产模型、自托管/数据不出网、OWASP 规则引擎、双层缓存。这些恰好命中"开源/自托管 + agent 生态"生态位——与 PR-Agent、Kodus 同赛道。

---

# Part 2 · crAgent 重构计划

## 2.1 重构总思路:双轨制

- **Track A · 代码健康轨**(0-2 周):以 `docs/REFACTORING_PLAN.md` 为准——修逻辑 bug、清死代码、拆 `cli.py`、类型收紧。**该文档已经过双轴评审,本文不重复,只修订其中一个关键决策(见 2.3)。**
- **Track B · 能力升级轨**(2-8 周):按业界五个共识,把架构从"diff-only 单 prompt"升级为"**全库上下文 + 分层过滤 + 专门化评审**",守住自托管/Agent 友好生态位。

**原则**:Track A 先行,因为它把 554 个测试变成可靠安全网;Track B 的每一步都独立可交付、可回滚。

## 2.2 Track A · 代码健康(继承现有方案,压缩为 3 个里程碑)

| 里程碑 | 内容 | 依据 |
|---|---|---|
| **A1**(0.5-1 天) | P0 逻辑 bug:fix 确认时序(S2)、`--min-risk` 过滤失效(S3)、`OrchestratorState` 改 TypedDict(S6)、`cache_info` 动态类(S7) | REFACTORING_PLAN §5 P0 |
| **A2**(1-2 天) | P1 死代码清除(**修订版,见 2.3**)+ P2 结构拆分:`cli.py` 1751 行 → `cli/` 包 5 模块;`rules/` 拆包 | REFACTORING_PLAN §5 P1/P2 |
| **A3**(2-3 天) | P3 去重:语言检测表三分归一、LLM 工厂改注册表、缓存 TTL 单点化、原子写对齐;P4:mypy 清零入 CI、`Config` 设 `extra="forbid"` | REFACTORING_PLAN §5 P3/P4 |

## 2.3 ⚠️ 对现有方案的关键修订:`core/languages/` 不要删,要"复活"

现有 REFACTORING_PLAN 的 P1 建议删除 `core/languages/`(7 种语言分析器,~2438 行,主流程未接线)。**调研结论改变了这笔账**:

- 业界共识 1 要求的全库上下文,其地基正是"多语言 AST 解析 → 符号/依赖提取"——这正是 `core/languages/*/analyzer.py` 已经写好的能力,只是从未接线。
- 删除省 2438 行;复活并接线,换来 Track B 最重要能力的起点,避免重写。

**修订建议**:
1. `core/languages/` 从"删除清单"移到"接线清单":保留 Python/Go/Java/Rust/JS-TS 五个 analyzer,裁剪为统一的 `SymbolIndex` 接口(提取函数/类/导入/调用关系)。
2. 仍删除:`report_generator.py`、`team_insights.py`、`history_tracker.py`、`github_app.py`(纯僵尸,且与业界方向无关);`complexity_scorer.py` 可作为评审上下文的一个信号源保留评估。
3. 若评估后确认 analyzer 质量不及 tree-sitter 方案,再删不迟——但先用它跑通全链路验证价值,再决定替换实现。

## 2.4 Track B · 能力升级(按业界共识排优先级)

### B1 · 全库上下文层(共识 1)— 最高优先级

```
core/context/
├── indexer.py      # 全库扫描:调用 languages/ analyzer 提取符号与依赖,落盘为索引
├── graph.py        # 轻量依赖图(暂不引入 Memgraph 等外部依赖,先用 networkx/纯 dict)
└── retriever.py    # 给定 diff → 找出变更符号 → 沿图取 caller/callee/相关文件 → 注入 prompt
```

- 增量更新:复用现有 `cache.py` 的失效机制,按文件 mtime/hash 重建局部索引。
- 验收:构造"改了 A 文件的函数签名、B 文件调用方未同步"的测试用例,评审必须报出跨文件问题——这是 diff-only 模式必然漏掉的。

### B2 · 分层评审流水线(共识 2)

把现有的"静态规则 ∥ LLM"并列结构改为**三层漏斗**:

```
diff → [L0 确定性层] OWASP 规则 + 语言 analyzer 命中 → 直接产出高置信发现,不进 LLM
     → [L1 上下文装配] B1 的 retriever 注入受影响文件
     → [L2 LLM 裁决] 只对 L0 未覆盖、且 L1 判定有上下文风险的 hunk 调用 LLM
```

收益:token 成本下降、误报率下降(确定性层零幻觉)、LLM 专注于真正需要推理的部分——与 CodeRabbit/OpenCodeReview 的精度优先路线对齐。

### B3 · 专门化评审视角(共识 3,轻量实现)

不急于上多 agent 框架。把单次全维度 prompt 拆为 **3 个并行专门 prompt**(安全 / 逻辑正确性 / 可维护性),各自带精简上下文,结果由合成器去重、按置信度排序。`asyncio.gather` 即可,无需引入新编排框架——同时顺势完成 REFACTORING_PLAN 中"去 LangGraph 化"(B8:线性三节点图本就无编排价值)。

### B4 · 噪声治理与反馈回路(共识 4)

- 每条发现输出 `confidence` 字段(LLM 自评 + 规则来源加权),CLI 增加 `--min-confidence` 阈值。
- JSON 输出增加 `finding_id`(文件+行+规则+内容 hash),为反馈学习留接口。
- 新增 `codereview feedback <finding_id> <accept|reject>` 命令,落盘本地反馈库;评审时把历史 reject 模式注入 negative examples。这是 Greptile/Kodus 验证过的护城河,且自托管场景下实现成本极低(无需服务端)。

### B5 · 修复闭环对接外部 agent(共识 5)

- 保留现有 `fix` 自研修复器,但 JSON 输出增加 `fix_handoff` 字段:结构化的问题位置 + 建议代码,格式对齐 Claude Code/Codex 等 coding agent 的输入习惯——把"Agent 友好 CLI"的既有优势延伸到修复环节。
- 这比继续投入自研 fixer 更符合业界分工(评审工具聚焦发现)。

### B6 · 评测基线(贯穿 Track B 全程)

业界用 seeded-bug 基准(c-CRAB、CR-Bench 思路)量化 recall/precision。本项目应建 `tests/eval/`:

- 一个小型"含已知 bug 的 PR 语料"(可手工种 20-30 个跨文件/安全/逻辑 bug);
- 每次 Track B 改动后跑 eval,报告 recall / precision / token 成本三项指标;
- **没有 eval 的能力升级都是盲改**——这是调研中最清晰的方法论教训。

### B7 ·(远期)运行时验证

对齐 TREX/screencli 方向:对修复建议或高风险变更,自动生成并执行针对性测试。投入大,建议在 B1-B4 落地、eval 指标稳定后再评估。

## 2.5 里程碑总表

| 阶段 | 内容 | 预估 | 验收门禁 |
|---|---|---|---|
| M1 | A1 逻辑 bug 修复 | 1 天 | 554 tests 全绿 + 新增行为测试 |
| M2 | A2 死代码处理(修订版)+ cli.py 拆分 | 2 天 | 全绿 + mypy 不劣化 |
| M3 | A3 去重与类型收紧 | 3 天 | mypy 清零入 CI |
| M4 | B6 eval 基线先行 + B1 全库上下文 | 1-2 周 | eval 跨文件用例 recall 显著提升 |
| M5 | B2 分层流水线 + B3 专门化评审 | 1-2 周 | eval precision 不劣化、token 成本下降 |
| M6 | B4 反馈回路 + B5 修复对接 | 1 周 | finding_id/feedback 命令可用 |

## 2.6 风险与对策

| 风险 | 对策 |
|---|---|
| 复活 `core/languages/` 后发现实现质量差 | 先接 1-2 种语言验证价值,差则换 tree-sitter 重写(接口不变) |
| 全库索引在大仓库上慢/占内存 | 索引落盘 + 增量更新;首版只索引符号级,不索引全文 embedding |
| 分层流水线改变现有 JSON 输出结构,破坏外部 agent 依赖 | `schema_version` 升 1.2,旧字段保留;`test_agent_friendly.py` 兜底 |
| 专门化 prompt 导致 token 成本上升 | B2 漏斗先行减少进入 LLM 的 hunk 量,用 eval 的成本指标把关 |
| Track A/B 并行导致冲突 | 严格串行:A 全部合入后才动 B;B 的每个阶段独立 PR |

---

## 附:主要信息来源

- 工具横评与基准:[PromptQuorum AI Code Review 2026](https://www.promptquorum.com/prompt-engineering/ai-code-review "citation") · [screencli Best AI PR Review Tools 2026](https://screencli.sh/blog/best-ai-pr-review-tools-2026 "citation") · [getoptimal 9 Tools Ranked](https://getoptimal.ai/blog/best-ai-code-review-tools "citation")
- 架构模式:[Greptile 官方文档](https://www.greptile.com/docs/introduction "citation") · [Building an AI Code Review Agent (NiteAgent)](https://niteagent.com/blog/building-ai-code-review-agent/ "citation") · [Qodo 2.0 多智能体](https://aicodereview.cc/blog/qodo-vs-coderabbit/ "citation")
- 开源方案:[PR-Agent 实测(Augment)](https://www.augmentcode.com/tools/open-source-ai-code-review-tools-worth-trying "citation") · [code-graph-rag](https://github.com/vitali87/code-graph-rag "citation") · [自托管指南(AppSecMaster)](https://www.appsecmaster.net/blog/best-ai-code-review/ "citation")
- 内部依据:[REFACTORING_PLAN](REFACTORING_PLAN.md "citation") · [DESIGN](DESIGN.md "citation") · [MISSION](../MISSION.md "citation")

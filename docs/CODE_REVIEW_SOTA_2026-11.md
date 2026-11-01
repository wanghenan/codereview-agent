# AI Code Review 现状调研（2026-11）

> 调研范围：2026 年在产的商业产品 + 主力开源实现 + 2026-08~10 的论文。
> 原则：只采信厂商官方文档、仓库源码与论文原文，二手评测文章一律不作为证据。
> 与 2026-09 版 `AI_REVIEW_LANDSCAPE_AND_REFACTOR_PLAN.md` 的区别：那一版大量引用 SEO 评测博客；本文档只保留可核验的一手来源，并补齐 2026 Q3/Q4 的新变化（验证式评审、把评审接进 coding agent、按轮次的基准）。

---

## 1. 结论先行

1. **评审对象变了。** 2026 年的 PR 里 agent 生成的改动占比显著上升，评审工具的评价标准从"能发现问题"转向"发现的问题可信、可修"。学术侧同步出现专门的"评审评论可信度"基准（CRJudgeBench）和"多轮缺陷状态"基准（MCR-Bench）。
2. **上下文是分水岭，但不再是"全库索引 vs diff"二选一。** 头部产品都在把"按需取上下文"做成 agent 工具循环：GitHub Copilot code review 用 Actions 跑全库上下文收集（agentic capabilities），Greptile 建全库代码图，CodeRabbit 用路径/规则/工具三层收窄。
3. **确定性工具回到架构主干。** CodeRabbit 在沙箱里跑 50+ linter/安全工具；Semgrep 的 AI 能力明确"主要作用于 Semgrep Code 已经产出的 finding"。LLM 负责裁决和解释，不负责全量发现。
4. **噪声治理是产品能力的核心，且开始量化。** Cursor Bugbot 给每条自定义规则算"接受率"；Copilot 用 Lite/Balanced/Max 三档控制成本与深入程度；研究侧（CIVER）在专门解决"评论很长但证据不足"。
5. **闭环从"评论"延伸到"修复 PR"。** Greptile 的 Fix with your Agent、Copilot 把建议交给 cloud agent 开修复 PR、Bugbot 的 Fix in Cursor/Web——评审工具越来越只做"发现+定位"，修复交给通用 coding agent。
6. **评审的产物正在满足机器消费者。** Copilot 从 PR 的 head 分支读 custom instructions / agent skills / MCP servers；CodeRabbit 的 Code Guidelines 会读 `AGENTS.md`、`.cursorrules`。仓库里的 agent 指令文件成为评审配置的事实标准入口。

---

## 2. 一条 PR 的完整链路：当前主流实现的六个阶段

### 2.1 触发与准入
- 自动（每次 push/PR 更新）vs 手动（评论命令）。Bugbot：`cursor review` / `bugbot run`，且会忽略 bot 账号或 GitHub App 发出的这些命令。[Bugbot](https://cursor.com/docs/bugbot)
- **准入闸门先于模型**：Bugbot 对超出体积上限的 PR 直接跳过并提示拆分（按变更行数 + diff 字符计），`linguist-generated` 文件不计入；对 bot 作者开的 PR 还有人头上限。[Bugbot](https://cursor.com/docs/bugbot)
- 路径过滤是标配：CodeRabbit 的 path filters 默认排除 lock 文件、二进制、生成代码，可覆盖。[CodeRabbit](https://docs.coderabbit.ai/guides/review-instructions)

### 2.2 上下文构建（差异化最大的一层）
三种可组合的做法，2026 年的产品普遍同时用两种以上：

| 做法 | 代表 | 实现要点 |
|---|---|---|
| 全库代码图 | Greptile | 建"每个函数、类、依赖"的图，用它判断改动对系统的影响；官方文档明确这是与"孤立看文件的 linter"的区别。[Greptile](https://www.greptile.com/docs/introduction) |
| Agent 工具循环按需取 | GitHub Copilot review | "full project context gathering" 由 GitHub Actions 跑，取不到就回落到受限评审；成本按 Lite/Balanced/Max 三档（平均 $0.25 / $1.50 / $10 每次）。[GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review) |
| 结构化收窄 | CodeRabbit | glob 路径指令 + `ast-grep` 的 AST 级规则（语法感知，不是正则）+ 读取仓库既有规范文件。[CodeRabbit](https://docs.coderabbit.ai/guides/review-instructions) |

补充：学术侧给出"改动本身可能跨文件"的量化证据——约 40% 的 PR 中，超过一半的被改函数由调用图相连，且必要的 callee 常在别的文件里，因此主张按调用图重组 diff（CG-Diffs）。[CG-Diff, arXiv 2609.32057](https://arxiv.org/abs/2609.32057)

### 2.3 分析编排
- **单调用 + 压缩**（成本最优）：PR-Agent 每个工具（`/review`、`/improve`、`/ask`）一次 LLM 调用，约 30 秒；大 PR 走 compression：按仓库主语言排序、优先 additions、tiktoken 计预算、装不下时降级为"其他改动文件列表"。[PR-Agent](https://github.com/qodo-ai/pr-agent) · [压缩策略](https://docs.pr-agent.ai/core-abilities/compression_strategy/)
- **确定性工具 + LLM 裁决**：CodeRabbit 的 50+ 工具在"secure sandboxed environments"里跑，且按仓库实际文件类型自动启用（PHP linter 不会跑在 Java 仓库）。[CodeRabbit Tools](https://docs.coderabbit.ai/tools)
- **多专门 agent**：学术侧的工业实践把评审拆成 readability / maintainability / reliability / performance 四个维度的专门技能，并注入项目专属知识；在 Ericsson 的真实仓库上做设计科学研究评估。[Ericsson, arXiv 2609.15877](https://arxiv.org/abs/2609.15877)
- **AI 叠加在既有扫描之上**：Semgrep Multimodal 的 AI detection 主要作用于 Semgrep Code 的 finding，另配 autotriage、noise filtering（beta）、memories。[Semgrep](https://semgrep.dev/docs/semgrep-assistant/overview)

### 2.4 噪声治理（决定"是否有用"）
- 规则/维度化：只报"真 bug"而不是风格建议，是 Graphite AI Reviews 的显式定位。[Graphite](https://graphite.dev/docs/diamond)
- 证据化：CIVER 用因果干预（对 finding 做干预验证）区分"核心问题"与"无证据的声称"，直接针对"评论长、误报多"。[CIVER, arXiv 2610.36010](https://arxiv.org/abs/2610.36010)
- 判决式质检：CRJudgeBench 专门判断"一条评审评论的技术主张是否成立"（1199 条，真 PR + 专家扰动），并给出仓库接地的 agent 判官（Sentinel）。[CRJudgeBench, arXiv 2609.37216](https://arxiv.org/abs/2609.37216)
- 去重：Bugbot 把已连接 PR 的顶层与行内评论作为上下文，避免重复建议、并在既有反馈上继续。[Bugbot](https://cursor.com/docs/bugbot)

### 2.5 输出与交互
- 行内评论 + 一键建议修改（CodeRabbit / Copilot / Bugbot / Graphite 都有）。
- **可观测的成功指标**：Bugbot 的每条自定义规则带"issues found / PRs reviewed / accepted / acceptance rate"。[Bugbot](https://cursor.com/docs/bugbot)
- **作为 CI 门禁**：Bugbot 为每次评审发一个 check（`Cursor Bugbot`），结论 success / neutral / failure，可配置为"有未解决 finding 就 fail"；GitHub Code Quality 可对 CodeQL 规则类 finding 与覆盖率阈值做 merge gating。[Bugbot](https://cursor.com/docs/bugbot) · [GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review)

### 2.6 闭环修复
- Greptile：每条评论带 "Fix with your Agent"，把文件路径、行号、建议代码交给 Claude Code / Codex / Cursor / Devin，另有 Fix All。[Greptile](https://www.greptile.com/docs/introduction)
- Copilot：把建议交给 Copilot cloud agent，直接对当前分支开修复 PR（public preview）。[GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review)
- Bugbot：Fix in Cursor（IDE）/ Fix in Web（cursor.com/agents）。[Bugbot](https://cursor.com/docs/bugbot)

---

## 3. 产品侧的新形态（2026 Q3/Q4）

- **CodeRabbit：从"评审"扩到"变更管理"。** Agentic Change Management = AI reviews + Triage（按价值/风险排 PR 队列并分派人）+ Change Stack（把大 diff 拆成逻辑分层，带区间摘要与图）+ Security（仓库扫描、泄露密钥、依赖漏洞）。[CodeRabbit](https://docs.coderabbit.ai/)
- **GitHub：把评审能力做成平台原语。** 评审可从仓库内 agent skills / MCP servers 取上下文；**从 PR 的 head 分支读指令**（因此能在一个 PR 里试验指令改动而不先合并）；可与 Code Quality（CodeQL 规则分析、覆盖率指标、一键修复、merge gating）组合。[GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review)
- **成本分级成为产品参数。** 同一产品用 effort level 在"便宜快"与"贵但深"之间取舍，并给出用量估算。[GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review)
- **厂商自己也提示可信度边界。** GitHub 文档明确"Copilot 不保证发现全部问题，可能出错，需人工复核"。[GitHub Docs](https://docs.github.com/en/copilot/concepts/code-review/code-review)

---

## 4. 研究侧的关键数字（截至 2026-10）

| 结论 | 数字 | 来源 |
|---|---|---|
| 前沿模型在真实引入 bug 的提交上做安全评审，召回跨度大 | 8 个模型 recall 32.5%–78.1%，265 个任务，覆盖 Firefox / V8 / OpenSSL | [SecPRBench, arXiv 2610.33509](https://arxiv.org/abs/2610.33509) |
| 真实评审是多轮的，单轮静态判定不成立 | 2269 个多轮任务、5 种语言、带跨轮缺陷状态标注 | [MCR-Bench, arXiv 2608.27442](https://arxiv.org/abs/2608.27442) |
| "评论看起来合理但技术主张错误"是可测的独立问题 | 1199 条实例（真 PR + 专家扰动） | [CRJudgeBench, arXiv 2609.37216](https://arxiv.org/abs/2609.37216) |
| 跨文件耦合普遍，按文件平铺 diff 不利理解 | 约 40% 的 PR 中过半被改函数由调用图相连 | [CG-Diff, arXiv 2609.32057](https://arxiv.org/abs/2609.32057) |

---

## 5. 落地清单（按投入产出排序）

1. **准入先行**：路径过滤 + 体积上限 + 生成文件排除。没有这一层，后面所有成本都会放大。
2. **确定性工具做发现主干**：语言检测 → 选工具 → 沙箱跑 → 归一化成 finding；LLM 只做"是否成立 + 为什么 + 怎么改"。
3. **上下文按需取**：先给 diff + 邻域，再让 agent 用工具（grep / AST / 调用图 / git history）追一层；不要一次性塞全库。
4. **每条 finding 必须有证据锚点**：文件、符号、行、触发它的规则或调用链；无锚点的降级为摘要而不是行内评论。
5. **去重与记忆**：读已有评论；跨 PR 记住团队反复否决的意见（"memories" / 反馈学习）。
6. **输出机器可用的修复载荷**：路径 + 行 + 建议 patch，便于交给 coding agent 直接开 PR。
7. **量化**：每条规则/每类 finding 的接受率、CI 阻断率、平均评审成本。
8. **配置入口对齐生态**：读 `AGENTS.md` / `.cursorrules` / 既有规范文件，而不是自造一套配置方言。

---

## 6. 对本仓库（crAgent）的对照

> 仅列结构性差距，细节见 `REFACTORING_PLAN.md`。以下判断基于本仓库当前源码（`python/src/codereview/`）。

- 现在是 LangGraph 的 `analyzer → reviewer` 逐文件评审，配 `FileReviewCache`；上下文是项目摘要 + 单文件 diff，**没有跨文件调用图/依赖检索**——对应第 2.2 节最弱的一档。
- `rules/` 规则引擎与 LLM 复核是**并列**关系，不是"确定性发现 → LLM 裁决"的分层；也没有第三方 linter 沙箱执行。
- 输出是 PR 评论 + Markdown 报告，**没有可交给 coding agent 的结构化修复载荷**，也没有 finding 级别的接受率统计。
- 配置走自有的 `.codereview-agent.yaml`，**不读 `AGENTS.md` 等生态约定文件**。
- 有 `--fix` 能力，但缺少"评审→修复→再评审"的闭环与门禁语义（CI check / merge gating）。

> 具体改造路径、优先级与验收方式见 [`CODE_REVIEW_UPGRADE_PLAN.md`](CODE_REVIEW_UPGRADE_PLAN.md)。

---

## 7. 来源

产品与文档
- CodeRabbit: <https://docs.coderabbit.ai/> · <https://docs.coderabbit.ai/guides/review-instructions> · <https://docs.coderabbit.ai/tools>
- Greptile: <https://www.greptile.com/docs/introduction>
- GitHub Copilot code review: <https://docs.github.com/en/copilot/concepts/code-review/code-review> · <https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions>
- Cursor Bugbot: <https://cursor.com/docs/bugbot>
- Graphite AI Reviews: <https://graphite.dev/docs/diamond>
- Semgrep Multimodal: <https://semgrep.dev/docs/semgrep-assistant/overview>
- PR-Agent（开源，MIT，13.8k stars）: <https://github.com/qodo-ai/pr-agent> · <https://docs.pr-agent.ai/core-abilities/compression_strategy/>

论文（arXiv，2026）
- SecPRBench: <https://arxiv.org/abs/2610.33509>
- CRJudgeBench: <https://arxiv.org/abs/2609.37216>
- CIVER: <https://arxiv.org/abs/2610.36010>
- MCR-Bench: <https://arxiv.org/abs/2608.27442>
- CG-Diff: <https://arxiv.org/abs/2609.32057>
- Ericsson agentic review: <https://arxiv.org/abs/2609.15877>

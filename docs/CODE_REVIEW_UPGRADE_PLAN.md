# crAgent 改造方案 v2（已收敛）

> 依据：`docs/CODE_REVIEW_SOTA_2026-11.md`（一手来源调研）。
> 约束：**单人维护，每周约 1 天**。工期按"每个切片 ≤ 2 个工作日、可独立合并"切分。
> 版本：v2（2026-11-01，按讨论结论重排；v1 的顺序作废）

---

## 0. 已定决策

| # | 决策 | 理由 | 代价 |
|---|---|---|---|
| 1 | 定位 **A → C**：先把评审做准，再产出可被 coding agent 直接使用的修复载荷；**不做 merge gating** | 门禁需要可信的精确率数字，现在没有；先做门禁等于赌博 | 没有"阻断"能力，短期靠人判断 |
| 2 | **保留 LangGraph** | 后续裁决驳回→重问、找上下文都长成分支 | 线性阶段多一层状态机，测试要覆盖节点边界 |
| 3 | 上下文用 **符号索引 + 少量工具循环**，不做全库 embedding | 现在连"改的函数被谁调用"都拿不到，先补 0→1；embedding 是精度优化 | 语义召回弱于 embedding |
| 4 | 输出以 **GitHub PR 页面** 为主：行内评论优先，`findings.json` 次之（服务 C） | 评审发生在 PR 页面 | 行内评论有刷屏风险，必须限量排序 |
| 5 | 先建 **30 正例 + 30 负例** 的评估集 | 没有基线，后面所有优化都无法判断是否变好 | 半天到一天的人工整理 |
| 6 | 规则层改为 **外部 linter 主干**（ruff / eslint / semgrep / trufflehog），`owasp_rules.yaml` 降为补充；**删掉** `core/languages/*` 与 `complexity_scorer.py` | 正则规则天然高误报，会拖垮裁决层；七套包无任何生产调用方 | 引入子进程与工具版本管理 |

> 决策 1 的直接后果：`findings.json`、patch 产出属于"做"，但要排在"看得准"之后；CI check / merge gate 语义从方案里删除。

## 1. 规则层（已定）

**结论**：外部工具做发现主干，自建规则只做补充。

- 新增 `core/tool_runner.py`：子进程执行 `ruff` / `eslint` / `semgrep` / `trufflehog`，按仓库语言选择、带超时与输出归一化（→ 候选 `Finding`，`source="tool"`）。
- `rules/owasp_rules.yaml` + `RuleEngine` 保留，作为语言无关的补充规则（如硬编码密钥模式）。
- **删除** `core/languages/*`（2759 行，七套正则规则包，`python/src` 零引用）与 `core/complexity_scorer.py`（546 行，无调用方），连同只服务它们的测试。
- 顺序：删除放在 S4 之前作为独立小 PR（避免与新代码混在一起看 diff）。

---

## 2. 切片顺序与工期（按 1 天/周折算）

| 切片 | 内容 | 估时 | 累计 |
|---|---|---|---|
| S0 | 评估集：30 个历史 PR 正例 + 30 条人工负例，跑成一条命令 | 1–2 天 | 2 周 |
| S1 | `Finding` 模型（证据锚点 + patch 字段）+ 兼容迁移 | 2 天 | 4 周 |
| S2 | 行内评论输出 + `findings.json` | 2 天 | 6 周 |
| S3 | 准入层：过滤 + 预算 | 1 天 | 7 周 |
| S4 | 工具接入 + 规则裁决层 | 2 天 | 9 周 |
| S5 | 符号索引 + 一层调用邻域 | ✅ 已合入 `7ce017a` / `967042c` | stdlib `ast`（零新依赖），29 文件 / 290 符号 / 0.08s；跨文件用例上「点名调用方」从 0/6 提升到 3/6 |
| S6 | 去重 + 团队记忆 | 2 天 | 15 周 |
| S7 | 读 `AGENTS.md` / `.cursorrules` + `path_instructions` | 1 天 | 16 周 |
| S8 | `fix` 产出 unified diff | 1 天 | 17 周 |

**最小可用版本 = S0 + S1 + S2（约 5–6 天 ≈ 6 周）**：评审结果变成"PR 页面上的行内评论，每条带证据锚点"，且有可复现的对照基线。S3 之后是降噪与上下文，S4 之后才是"做准"。

> 4 个月是乐观值。1 天/周的真正成本是上下文切换：每片必须自带测试和一段 README 说明，否则第二周回来要重新读代码。宁可切片更小，不可跨片重构。

---

## 3. 各切片技术要点

### S0 · 评估集（最先做）
- 数据：从仓库历史 PR 里挑 30 个"真人 reviewer 提过实质问题"的，把当时评论整理成 `{pr, file, line, expected_issue}`；再人工写 30 条"看似合理但错"的评论当负例（CRJudgeBench 的思路）。
- 形态：`python/tests/benchmark/` 下一个 `bench.py`，输出 `hit / miss / fp` 与逐条 diff，跑真实 LLM（走环境变量，CI 里跳过）。
- 验收：一条命令产出可对照的分数；每次改动前后跑一次。

### S1 · Finding 模型
- `models/__init__.py:38` 的 `FileIssue` 扩展为 `Finding`：`category / severity / confidence / title / body / evidence[] / suggested_patch / source`。
- 去重键：`(file_path, line_bucket, title_normalized)`。
- 兼容：保留 `FileIssue` 别名一版，用 `model_validator` 接受旧 JSON。
- 验收：旧 fixtures 全部仍可解析；新 schema 有独立单测。

### S2 · 行内评论
- `output/` 新增 `InlineCommentBuilder`：`Finding → {path, line, body}`；`github_client.post_comment` 之外新增 `create_review`（一次提交多条行内评论）。
- 单 PR 上限 25 条，按 `severity × confidence` 排序，其余折叠进 summary。
- 同时落 `findings.json`（就是 `Finding` 列表），为 C 准备。
- 验收：payload 结构单测 + 本地 dry-run 断言，不实际提交。

### S3 · 准入层
- 新增 `core/diff_filter.py`：二进制/生成文件/锁文件 → `exclude_patterns` → 单文件与整 PR token 预算（现在仓库里没有任何 token 计数，需要引入）。
- 跳过原因进 `ReviewResult.skipped`，PR 评论里一行汇总。
- 验收：fixture 断言 kept/skipped 与排序；大 PR 不改变小 PR 的输出（golden）。

### S4 · 规则裁决层
- 候选 finding（规则/工具产出）→ 模型逐条 `accept / reject(reason) / rewrite(patch)`；模型自发现另走一段，必须带证据。
- 归因字段：`Finding.source ∈ {rule, tool, llm}`，驳回记录进 `rejected[]`，用于算规则误报率。
- 验收：20 条规则命中样本 + 10 条已知误报，断言 FP 下降且 FN 不增。

### S5 · 符号索引
- `core/symbol_index.py`：tree-sitter 解析 → SQLite（`symbols(path,name,kind,start,end)`、`refs(from_path,to_name)`），按 commit 增量更新，落 `.codereview-agent/index.db`。
- 先支持 Python/TypeScript/Go；未解析语言显式标注"未索引"，不静默降级。
- 注入：每文件一层 caller/callee 邻域，受 S3 的预算约束。
- 验收：索引构建 < 60s（10 万行）；固定 case 集前后对比（人工盲评 20 例）。

### S6 · 去重与记忆
- 读 PR 已有评论（`github_client` 现只有 `post_comment`，需加列表接口），按去重键 + 轻量相似度跳过。
- `.codereview-agent/memory.json`：记录被 dismiss / 👎 的 finding 指纹，下次降权。
- 验收：同一 PR 连跑两次，第二次行内评论为 0。

### S7 · 配置对齐
- `ConfigLoader` 增加 `code_guidelines`：探测 `AGENTS.md` / `CLAUDE.md` / `.cursorrules` / `CONTRIBUTING.md`，截断注入。
- `path_instructions`（glob → 指令），复用 `core/path_matcher.py` 的 pathspec 匹配。
- 验收：拼错字段报错（`extra="forbid"` 已有，别退化）；能读到 `AGENTS.md` 并进 prompt。

### S8 · patch 产出
- `fix_cmd` 已有 dry-run 与写盘前确认（`c1a3f3e` 修掉了 S2 缺陷）；缺的是**默认输出 unified diff**，`--apply` 才落盘。
- 验收：`git apply --check` 全通过；未加 `--apply` 时工作区不变。

---

## 4. 明确不做

- **全库 embedding 检索**——S5 之后再评估。
- **四维多 agent**（readability / security / perf）——裁决层稳定前做，只是把噪声乘以 4。
- **merge gating / CI check 阻断**——没有可信精确率前不做。
- **评审侧自动开修复 PR**——只产出载荷，执行交给 coding agent 或人。
- **继续扩自建正则规则**——见 §1。

---

## 5. 风险

| 风险 | 应对 |
|---|---|
| 1 天/周导致切片烂尾 | 每片 ≤ 2 天；不做跨片重构；完成即合并 |
| 评估集主观、样本少 | 先 30+30，跑通流程比样本量重要；后续按需扩 |
| 行内评论刷屏被团队关掉 | S2 就限量 + 排序；S6 补去重 |
| 外部工具引入沙箱复杂度（S4） | 先子进程 + 超时，容器化留到需要时 |
| LangGraph 状态难测 | 每个节点独立单测，节点间只传显式字段 |

---

## 6. 进度

| 切片 | 状态 | 说明 |
|---|---|---|
| S0 评估集 | ✅ 已提交 `cea5326` | 24 注入正例 + 6 负例 + `gen_cases.py` / `bench.py` |
| S1 Finding 模型 | ✅ 已提交 `2c15c60` | `FileIssue` 增加 `title/end_line/category/confidence/evidence/suggested_patch/source` + `dedupe_key()`；LLM 输出经 `_to_finding` 归一化；规则命中标记 `source="rule"` 并带规则证据；prompt 已要求 category/confidence/evidence |
| S2 行内评论 | ✅ 已合入 `230e38e` + 接线 `4ea859a` | 25 条上限、severity×confidence 排序、折叠摘要、`findings.json` |
| S3 准入层 | ✅ 已合入 `4b926a5` + 接线 `4ea859a` | filter + token 预算 + `ReviewResult.skipped` |
| S4 工具接入 | ✅ 已合入 `e7ef370` + 接线 `4ea859a` + 过滤 `6d4617a` | tool_runner；删除 7 套正则语言包与 complexity_scorer（净 -3158 行）；`min_confidence=0.5` 降噪 |
| S0+ 真实语料 | ✅ 8 条，见 `docs/EVAL_SET_DESIGN.md` | `collect_real_prs.py` 抓 6 个公开仓库的真人 review 评论；`bench.py --origin real-pr` 在 base commit 的 tarball 上评审。语义命中 **2/8**（注入样本是 24/24）——首次得到可信的真实语料数字 |
| S0+ 评测口径 | ✅ 同 PR | 新增 `strictness`（defect/design/nit）与 `review_comment` 溯源；明确「±3 行只作候选，真实语料必须人工判是否同一问题」 |

### 并行实施（worktree 分工）

S2 / S3 / S4 文件集不相交，可并行；接线留在主线按序完成：

| 分支 | 目录 | 范围 | 集成动作 |
|---|---|---|---|
| `agent/s2-wt` | `crAgent-wt-s2` | `output/inline.py`、`github_client.create_review` | `run_review` 输出同时产出 comments + findings.json |
| `agent/s3-wt` | `crAgent-wt-s3` | `core/diff_filter.py`、`models.SkipRecord` | `review_files` 前调用 `filter_entries`，跳过原因进 `ReviewResult.skipped` |
| `agent/s4-wt` | `crAgent-wt-s4` | `core/tool_runner.py`、删正则语言包 | 裁决层把 tool finding 当候选，LLM 只裁决 |

集成顺序：S3 → S2 → S4（冲突面从小到大）。

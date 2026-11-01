# S0 评估集设计（v0.1，供确认）

> 目的：给 crAgent 一个**可重复的对照分数**，回答"这次改动让评审变好还是变坏"。
> 位置：`python/tests/benchmark/`。不进 CI（要真实模型调用），`make bench` 手动跑。
> 依赖：无（先于 S1 落地，正因为要它来给 S1 之后的改动当基线）。

---

## 1. 设计取舍

| 问题 | 选择 | 理由 |
|---|---|---|
| 样本从哪来 | **注入缺陷为主（24 条），真实历史 PR 为辅（6 条）** | 单人项目历史 PR 数量与标注质量都不稳定；注入样本真值精确、可无限补 |
| 判分靠谁 | v0 **人工 10 分钟打分**，S1 之后接 **LLM 判官** | 现在 Finding 还是自由文本，自动匹配不可靠；先把流程跑通 |
| 匹配粒度 | 文件相同 + 行号 ±3 + 人工确认语义 | 行号会被模型算偏，但不能偏太远 |
| 规模 | 30 正例 + 30 负例 | 半天能做完；够发现"改坏了"的量级变化 |

**不做**：不做百分制、不做跨语言全覆盖、不做模型间横评——这些等评估集稳定到 100 条再说。

---

## 2. 样本 schema

`python/tests/benchmark/cases/<id>.yaml`：

```yaml
id: mut-llm-retry-counter
kind: positive              # positive=应报出；negative=不应报出
origin: injected            # injected | real-pr
language: python
base: python/src/codereview/core/llm.py     # 被改文件
diff: |                     # unified diff，可直接喂给 CLI
  --- a/... 
  +++ b/...
expect:
  file: python/src/codereview/core/llm.py
  line: 88                  # 参考行，允许 ±3
  category: bug             # bug | security | perf | maintainability | style
  severity: high
  summary: "重试后未重置计数器，导致无限重试"
  why: |
    循环里 retry_count 只在成功分支重置……
tags: [control-flow, retry]
# negative 样本额外要求：这条评论"看起来合理但实际不成立"的理由
invalid_reason: null
```

字段约束：
- `kind: negative` 必须填 `invalid_reason`（否则无法复核负例本身对不对）。
- `expect.line` 允许省略，此时按文件级匹配。
- `diff` 必须能 `git apply`（runner 会先 `--check`）。

---

## 3. 目录与运行

```
python/tests/benchmark/
├── cases/                    # 60 个 yaml
├── bench.py                  # 入口：load → run → score → report
└── reports/                  # 输出（gitignore）
```

```bash
# 单条调试
python -m tests.benchmark.bench --case mut-llm-retry-counter

# 全量：生成并排对照报告，不判分
python -m tests.benchmark.bench --all --out reports/2026-11-15.md

# 只跑正例 / 只跑负例
python -m tests.benchmark.bench --kind positive
```

`bench.py` 做四件事：
1. 校验每个 case 的 diff 可应用；
2. 调现有 `run_review`（走真实 LLM，key 从环境变量取）；
3. 按"文件 + ±3 行"把模型输出与 `expect` 做**候选配对**；
4. 生成 Markdown：每条 case 一栏，左侧 `expect`，右侧模型 finding，末尾汇总表。

**v0 的分数由人填**：报告底部给一张空表，跑的人勾 `hit / partially / miss / fp / tn`，10 分钟。这一步故意不自动化——先看模型到底怎么错的，再决定判官怎么写。

---

## 4. 指标（v0 用人工勾选汇总）

| 指标 | 定义 |
|---|---|
| Recall@30 | 24 条注入 + 6 条真实中，命中的比例 |
| FP@30 | 30 条负例里被报出的比例（越低越好） |
| Noise | 每个 PR 平均 finding 数（噪声代理） |
| Cost | 每次评审 token 数 / 耗时（runner 打印） |

后续（S1 之后）：用 `Finding.title + category` 做结构化匹配，把人工勾选换成 LLM 判官 + 10% 抽样人审。

---

## 5. 24 条注入样本的缺陷配方（初版）

按当前代码库真实形态选，避免"教科书缺陷"：

| 类别 | 例子 | 条数 |
|---|---|---|
| 控制流 | 重试计数未重置、`except` 吞异常后继续 | 6 |
| 资源 | 打开文件未关闭、subprocess 未设超时 | 4 |
| 并发 | `asyncio.Semaphore` 用在错误的层级、共享可变状态 | 4 |
| 安全 | 路径拼接未规范化、日志打印密钥 | 4 |
| 边界 | 空 diff / 超长行 / 编码非 UTF-8 | 3 |
| 数据 | 配置字段默认值覆盖用户值 | 3 |

每条注入 = 一段最小 diff（≤ 20 行），从当前 `python/src` 的真实函数改出来，保证上下文真实。

**6 条真实 PR 样本**：优先从本仓库有真人 review 评论的 PR 取；不足则从 `qodo-ai/pr-agent` 等公开仓库取（评论公开可引用），标注来源链接。

---

## 6. 工作量

| 天 | 事项 |
|---|---|
| 第 1 天 | 写 24 条注入 diff + 6 条真实样本；`bench.py` 骨架（load + 校验 + 跑通单条） |
| 第 2 天 | 接 `run_review` 全量跑、生成报告、首轮人工打分，得到基线数字 |

产出：一个能跑的命令 + 一份基线报告（含首轮分数与最典型的 3 个失败案例）。

---

## 7. 待你确认

1. 采样口径：**注入为主 + 真实为辅**（见 §1），还是坚持全用真实 PR？
2. 负例来源：人工写 30 条"看似合理但错"的评论，是否可以接受由我先起草、你复核？
3. 基准跑在哪个模型：`config` 默认模型，还是固定成你现在线上用的那一个（便于和历史对比）？

---

## 8. 现状（2026-11-01，第一版已落地）

| 项 | 状态 |
|---|---|
| `python/tests/benchmark/gen_cases.py` | ✅ 30 条配方，`--check` 校验、`--write` 生成 |
| `python/tests/benchmark/bench.py` | ✅ `--validate` / `--case` / `--all` / `--kind`，输出并排报告 |
| 正例 | ✅ 24 条（注入，覆盖 cache / path_matcher / github_client / diff_parser / reviewer / llm） |
| 负例 | ✅ 6 条（重命名、补类型标注、补注释、等价改写——应零 finding） |
| 真实 PR 样本 | ⏸ 暂缓：本仓库 18 个 PR 全是 dependabot 与 chore，无实质人工 review 评论（`gh api` 核过） |
| 真实 LLM 跑通 | ⏳ 未验证：`.codereview-agent.yaml` 里 key 是 `${{ secrets.LLM_API_KEY }}` 占位，需要在本地凭据下跑第一次 |

**校验结果**：`bench.py --validate` → 30/30 diff 可应用到 HEAD；`ruff check` 全绿；模块可导入。

**基线口径**：`gen_cases.py` 用 `git show HEAD:<file>` 读取文件，diff 因此总是相对 **HEAD** 生成；`bench.py` 用 `git apply --check --cached` 校验，不受本地未提交改动影响。改完源码后重新生成即可：`python -m tests.benchmark.gen_cases --check --write`。

第一次真实运行：

```bash
cd python && .venv/bin/python tests/benchmark/bench.py --all --config ../.codereview-agent.yaml
# 报告写到 python/tests/benchmark/reports/run-YYYYMMDD-HHMM.md，人工勾 verdict
```

成本预估：30 次单文件评审。若模型按文件计费，一天跑 2 轮仍在可控范围；报告里会打印每例耗时。

**真实 PR 样本的替代路径**（等你确认）：从 `qodo-ai/pr-agent` 这类公开仓库取 6 个含实质 review 评论的 PR，评论公开可引用，代码也是 Python——比自造样本更能反映真实评审语料。需要时我可以补 6 条。

### 首轮基线（2026-11-01）

配置：`deepseek-chat`，温度 0.2，单文件评审，项目分析缓存复用。报告：`python/tests/benchmark/reports/baseline.md`。

| 指标 | 结果 |
|---|---|
| 正例命中（文件一致 + 行号 ±5） | **24 / 24** |
| 负例误报 | **2 / 6（33%）** |
| 每例平均 finding 数 | ~1.4 |
| 每例耗时 | 1.5–4.6 s（均值 ~3 s） |

两条误报都是"低风险、带条件的猜测"，而不是明显错误：

- `neg-cache-rename-local`：模型说"如果函数后面还有代码引用 `data`，这里会报错"——diff 里看不到函数全体，属于合理的谨慎，但对 PR 评审是噪声。
- `neg-llm-kwargs-unpack`：模型指出"多了一层字典解包"，属于风格评论而非缺陷。

**解读**：注入样本的召回已经是满分，说明当前的 Prompt 在"看得见的缺陷"上够用；真正的差距在**噪声**——这正是 S4 裁决层（按 confidence 过滤 LOW 级 finding）要解决的问题。下一轮基线应在接入 confidence 阈值后重跑，看误报能否降到 1/6 以下、同时保持正例命中。

### 阈值扫描（同日，带 confidence 的第二轮）

第二轮基线在报告里渲染了 `conf` 与 `source`，据此对 `min_confidence` 做扫描（正例 = 文件一致且行号 ±5；负例只要有任何 finding 即算误报）：

| 阈值 | 正例命中 | 负例误报 | 丢掉的正例 | 过滤掉的负例 |
|---|---|---|---|---|
| 0.00 | 24 | 2 | 0 | 0 |
| 0.40 | 24 | 2 | 0 | 0 |
| **0.50** | **24** | **1** | **0** | **1** |
| 0.60 | 23 | 1 | 1 | 1 |
| 0.75 | 20 | 0 | 4 | 2 |
| 0.90 | 11 | 0 | 13 | 2 |

两条误报的 confidence 分别是 **0.40**（`neg-cache-rename-local`）和 **0.70**（`neg-llm-kwargs-unpack`，LOW / 风格建议）；正例的 confidence 区间是 0.50–0.98。

**决定：`min_confidence = 0.50`，`drop_low_risk_llm` 默认关闭。**

理由：0.50 用零召回代价去掉一条误报；再往上（0.60+）开始伤正例。剩下的 0.70 那条是 LOW 级风格意见，用 `drop_low_risk_llm` 能清掉，但代价是唯一一条依赖 LOW 命中的正例（`llm-provider-failure-hidden`，conf 0.55）也会被丢——用一条真问题换一条无关痛痒的噪声不划算。需要更激进降噪的团队可以在配置里自行打开。

### 过滤后确认基线（同日，`min_confidence = 0.5` 生效）

报告：`python/tests/benchmark/reports/after-filter.md`。

| 指标 | 过滤前 | 过滤后 |
|---|---|---|
| 正例命中（文件 + 行号 ±5） | 24 / 24 | **24 / 24** |
| 负例误报 | 2 / 6 | **1 / 6** |
| 每例耗时 | ~3 s | ~3 s |

被去掉的是 `neg-cache-rename-local`（confidence 0.40 的"如果后面还有代码引用…"式猜测）；剩下的一条是 `neg-llm-kwargs-unpack`（confidence 0.75，LOW，风格建议"多了一层字典解包"）。

**这条剩余误报怎么处理**：它属于 `maintainability` 类别的风格意见。两条路——`drop_categories: [maintainability]` 会连真正的可维护性问题一起丢，太粗暴；`drop_low_risk_llm: true` 能精准去掉它，但同样会丢掉唯一依赖 LOW 命中的正例（`llm-provider-failure-hidden`，conf 0.55）。当前选择保留：一条 LOW 级风格评论的代价，小于丢掉一条真实问题。

### 加入跨文件上下文后（S5，同日）

报告：`python/tests/benchmark/reports/with-context.md`。

| 指标 | 过滤前 | 过滤后 | 跨文件上下文 |
|---|---|---|---|
| 正例命中 | 24 / 24 | 24 / 24 | **24 / 24** |
| 负例误报 | 2 / 6 | 1 / 6 | **1 / 6** |
| 每例耗时 | ~3 s | ~3 s | ~3–4 s |

**结论：这套基准测不出跨文件上下文的价值。** 原因是构造使然——24 条注入缺陷都是单文件局部改动（超时缺失、信号量被删、计数偏移），仅凭 diff 就能定位；`neighbors` 注入的是"谁调用我"，对这类缺陷没有信息增量。

它也不是免费的：每个文件最多 2400 字符（≈600 tokens）。按 3 条邻居 / 2400 字符的默认值，评审输入成本上升约 20–30%。

**因此这条能力需要专门的用例才能验证**，下一步应补 6 条"跨文件缺陷"样本，形态是：改 A 的函数签名/返回值语义，而破坏发生在 B 的调用点——只读 diff 看不出，只有读到 caller 才能判断。在此之前，默认值保持开启（真实 PR 的跨文件改动比这套注入样本复杂），但不应宣称它已被基准证明有效。

### 跨文件用例（6 条）与特异性指标

行号命中这个指标测不出上下文的价值：任何签名改动，模型都会"猜"调用方可能坏掉，于是照样命中。为此补了 6 条**跨文件用例**（tag `cross-file`）：改动在 A 文件内自洽，破坏发生在 B 的调用点——改必填参数、调换参数顺序、改方法名、改关键字参数、改返回形态。

跑 `bench.py --tag cross-file` 两次（`context.neighbors` 开/关），再用 `tests/benchmark/cross_file_score.py` 统计"finding 是否点名了真实调用方的文件"：

| 指标 | 上下文关 | 上下文开 |
|---|---|---|
| 行号命中（原有指标） | 6 / 6 | 6 / 6 |
| **点名调用方文件** | **0 / 6** | **3 / 6** |
| 平均最高置信度 | 0.80 | **0.91** |

同一条 `xfile-inline-build-renamed` 的两种输出：

- 关：`The method build ... was renamed ... Any caller, base class contract, or interface that invokes .build(...)`——**泛泛猜测**，conf 0.70
- 开：`The cross-file context shows cli/review_cmd.py:215 still calls inline_builder.build(result)`——**具体证据**，conf 0.95

**结论：上下文的价值体现在"证据具体化"，不在命中率。** 决策：`context.neighbors` 保持默认开启；行号命中作为回归指标继续用，但跨文件能力必须看特异性指标，否则会误判为"没用"。

**仍未解决**：6 条里只有 3 条点名调用方（`filter-findings-order`、`create-review-body`、`toolrunner-cwd` 仍是笼统表述）。下一步可查这三条是否因为邻域截断（3 条 / 2400 字符）把调用方挤掉了。

### 跨文件指标修正（同日，第三轮）

上一节的 3/6 是**测量错误**，不是模型行为：`bench.py` 渲染 finding 时把正文截断到 160 字符，调用方路径正好被截掉。把截断放宽到 600 字符、并修掉索引里的一个真 bug（改动落在方法内时，外层类也被当成目标符号，于是 `ToolRunner(...)` 这种实例化被误判成方法的调用方，把真正的调用点挤出邻域）之后重跑：

| 指标 | 上下文关 | 上下文开 |
|---|---|---|
| 行号命中 | 6 / 6 | 6 / 6 |
| **点名调用方文件** | **0 / 6** | **6 / 6** |
| 点名调用方行号 | 0 / 6 | 2 / 6 |
| 平均最高置信度 | 0.80 | **0.95** |

结论不变但强度大得多：**上下文把"某处调用方可能坏"变成"某个文件里的调用方会坏"**，6 条用例全部如此。

**这次踩的坑值得记住**：指标实现本身会撒谎。截断、排序、渲染都会改变被测对象；改完评分器必须先用已知样本验证它能识别出正确答案，否则"0/6"到底是模型不行还是尺子坏了无法区分。

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

每条注入 = 一段最小 diff（≤ 20 行），从当前 `python/src` 的真实函数改出来，保证上下文真实。recipe 与 `src/` 的同步由 CI 的 `gen_cases --check` 保证（这条回归就是它该挡住的）。

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

### 结构化 caller 字段（同日，第四轮）

自然语言里的"点名调用方"只能做到 6/6 文件、2/6 行号。把断言变成结构字段后稳定了：

- `FileIssue` 新增可选 `caller: "path:line"`；模型在 prompt 里被要求只在跨文件上下文确实给出调用方时填写
- 解析侧校验格式（`path:line`，超长或乱写一律丢弃），不让脏字符串进入结果
- 上下文片段的每行加了真实行号前缀（` 1214 | kept, dropped = filter_findings(...)`），模型可以照抄，而不是自己数行

**结果（6 条跨文件用例，上下文开）**

| 指标 | 自然语言 | 结构化 caller |
|---|---|---|
| 点名调用方文件 | 6 / 6 | **6 / 6** |
| 点名调用方行号 | 2 / 6 | **6 / 6**（含 ±5 行容差，允许指向参数行） |
| 平均最高置信度 | 0.95 | 0.95 |

顺带修掉一个基准自身的错误：`cross_file` 里记录的调用方行号是早期版本的行号，S5 接线后代码下移了 20–30 行，导致"模型说对了却判错"。刷新元数据后，模型此前输出的 `1084 / 1242 / 661 / 228` 全部命中。**又一个尺子坏掉的例子——这次是基准数据过期。**

### 真实 PR 语料（20 条，2026-11-02）

前面所有数字都建立在**注入样本**上：我们照着当前代码把缺陷重新敲进去，再让模型读 diff。它能证明"看得见的问题不会漏"，但回答不了评审真正的难题——**真人 reviewer 会不会认为这里有问题**。本仓库历史 PR 没有实质人工 review，所以语料取自公开仓库。

**采集（`collect_real_prs.py`）**

```bash
python tests/benchmark/collect_real_prs.py --repo django/django --min-comments 10 --max-prs 8
python tests/benchmark/collect_real_prs.py --from-cache   # 重放 .cache/gh 里已有的 PR
python tests/benchmark/collect_real_prs.py --list          # 回看已抓的草稿
```

- 用 search API 找"已合并、非 bot 作者、讨论多（`comments:>=N`）"的 PR，再取它的 inline review comment（`subject_type=line`）；
- 排除：回复串、PR 作者自评、bot（含 AI reviewer）、` ```suggestion ` 开头的纯改写建议；
- 按"缺陷词表"（`breaks/crash/None/race/raises/...`）给评论打分排序，减掉"加测试/补文档"这类过程性意见；
- 每条评论只切出它所在的 hunk（+前一个 hunk 作上下文），保留原始 `@@` 行号——**diff 仍能 `git apply`**，但体积可控；
- 草稿写进 `drafts/`（gitignore），人读一遍后把 `expect` 填实、补 `strictness`，才晋升到 `cases/`。

**用例格式**：在原有 schema 上增加四个字段。

```yaml
origin: real-pr
repo: django/django
base_commit: d44ee518c4…      # 评论所在提交的父提交（--final-diff 时仍是 PR base）
pr: 15687
strictness: defect            # defect=具体故障 / design=设计或语义缺陷 / nit=API 细节
review_comment: {author: bluetech, url: "…discussion_r1161316259", body: "…"}
```

**跑在别人的树上**：`real_pr.py` 用 `gh api repos/<repo>/tarball/<sha>` 把 base commit 解到 `.repos/`（gitignore），`bench.py` 评审时 chdir 进去。必须这样——项目分析、符号索引、外部工具全读 `cwd`，否则读到的是 crAgent 自己的代码，等于拿错仓库评审。

```bash
python tests/benchmark/bench.py --all --origin real-pr --config <bench.yaml> --out reports/real-pr-8.md
python tests/benchmark/bench.py --validate --origin real-pr     # 校验 20 条 diff 都能应用到 base
```

**语料（20 条，9 个仓库）**

| 用例 | 位置 | 类别 | strictness |
|---|---|---|---|
| `real-django-psycopg3-tzloader` | django#15687 `psycopg_any.py:34` | bug/high | defect |
| `real-drf-datetime-local-none-format` | drf#9365 `renderers.py:352` | bug/medium | defect |
| `real-pandas-series-extension-dtype-check` | pandas#19520 `series.py:217` | bug/medium | defect |
| `real-pandas-timedeltaarray-freq-no-validation` | pandas#24024 `timedeltas.py:188` | maintainability/low | design |
| `real-matplotlib-hist-colors-sequence` | matplotlib#28073 `_axes.py:7222` | bug/medium | defect |
| `real-django-enqueue-on-commit-single-db` | django#18627 `backends/base.py:50` | bug/medium | design |
| `real-aiohttp-cause-without-traceback` | aiohttp#8089 `helpers.py:830` | maintainability/low | design |
| `real-requests-timedcache-keyerror` | requests#3885 `structures.py:169` | maintainability/low | nit |
| `real-django-migrate-install-error-swallowed` | django#376 `migrate.py:239` | bug/medium | defect |
| `real-black-3219-invalid-specifier` | black#3219 `files.py:216` | bug/medium | defect |
| `real-flask-3412-asgiref-import` | flask#3412 `helpers.py:15` | bug/medium | defect |
| `real-black-2357-token-loop` | black#2357 `handle_ipynb_magics.py:135` | bug/low | defect |
| `real-django-9622-cot-precision` | django#9622 `sqlite3/base.py:185` | bug/low | defect |
| `real-aiohttp-9732-middleware-default` | aiohttp#9732 `client.py:458` | maintainability/low | design |
| `real-aiohttp-9732-redundant-check` | aiohttp#9732 `client_middlewares.py:31` | maintainability/low | nit |
| `real-drf-8532-duration-format` | drf#8532 `fields.py:1392` | maintainability/low | design |
| `real-flask-1291-error-handler-spec` | flask#1291 `app.py:1166` | maintainability/low | design |
| `real-aiohttp-8063-optional-type` | aiohttp#8063 `web_fileresponse.py:136` | maintainability/low | nit |
| `real-django-18056-aggregate-null` | django#18056 `aggregates.py:190` | maintainability/low | design |
| `real-redis-1660-cluster-wait` | redis#1660 `conftest.py:80` | maintainability/low | design |

> 2026-11-02 扩到 20 条；下面「结果」里的 `2/8`、`5/8` 是 8 条/9 条时的历史实测，本轮没有重跑，保持原样。新增的 11 条里 `defect` 为 4 条，全语料 `defect` 共 9 条——缓存里剩下的候选要么是过程性/风格意见，要么评论时的证据不在切片内，没有为了凑 `defect ≥ 10` 而升级严重度。

**结果（deepseek-chat，单文件切片，上下文开）**

| 指标 | 数字 |
|---|---|
| 行号 ±3 有 finding 落到同一位置 | 5 / 8 |
| **语义命中（人工判"同一问题"）** | **2 / 8**（drf、pandas-series；后者措辞含糊，只说"is_dtype 语义可能不符"） |
| 报在同块、但不是同一问题（部分） | 2 / 8（matplotlib、pandas-timedeltas） |
| 完全没碰到 | 4 / 8 |
| 每例 finding 数 | 5–39，均值 ~17 |

对照注入样本的 24/24，这个落差是本轮最重要的结论：**注入基准测的是"读 diff 的能力"，真实评审要的是"知道这段代码在真实世界会怎么坏"**。psycopg 那条例子的正确答案依赖 `TimestamptzLoader` 返回 UTC 这一外部知识；requests 那条是 API 契约细节；django 多库那条是框架级设计约束——三者都不在 diff 里。

**这一轮暴露的产品缺陷（都已修/记录）**

1. 工具输出的路径是绝对路径（ruff 在无法确定项目根时会这样报）。行内评论和 diff 匹配都要仓库相对路径，GitHub 也会拒。→ `tool_runner._relativise_findings()` 在 normalise 边界统一转相对。
2. 工具**诊断**被当成评审意见：新文件的 diff 在 base 上不存在，ruff 报 `os error 2`，流水线把它变成一条 MEDIUM finding。→ `reviewer.TOOL_DIAGNOSTIC_RULES` 丢弃 `tool_error`/`tool_timeout`/`tool_unavailable`。
3. 自建规则层误报：SQL 注入规则把 docstring 里的 "executed" 当成 SQL（`if task_func_args[0] != "context"` 那条的实际原因是规则命中了附近的文档字符串），且 finding 行号取自拼接后的新增行下标而非新文件真实行号，行内评论会贴到错误位置。→ 收紧 `OWASP-A01-003` 至真实 SQL 调用点，`detect_in_diff()` 解析 hunk 头映射新文件行号（**已修**：#34 / PR #36）。规则层现在先剥离注释与 docstring 再匹配（保留行号与行内字符串），同类散文误报不必再逐条收紧正则。
4. finding 锚在块首而非出错行：drf 那条最准的 finding 报在 343 行，人类评论在 352 行（Δ9）。行内评论会贴错位置，行号指标也把它判成 miss（**未修**）。

#### 切片基准：最终 diff ≠ 评论时 diff（2026-11-02）

上一轮把 43 条草稿对照 **PR 最终 diff** 逐条核，结论是 0 条可晋升；这不是语料差，是尺子切错了地方。真人评论锚在**某个中间提交**上，PR 最终 diff 是另一棵树：

- black#3219：评论时 `strip_specifier_set` 还没有 `except (InvalidSpecifier, InvalidVersion)`，最终代码已补上；
- flask#3412：评论时 `asgiref` 在模块顶部导入（最终改成 `run_async` 内延迟导入 + extras）；
- urllib3#5330：评论时 `Retry.from_int(retries, redirect=redirect)` 没有 `default=response.retries`，最终加了该参数。

采集器现在的默认行为（`collect_real_prs.py`）：

1. 用评论的 `original_commit_id`（没有则 `commit_id`）取 `GET /repos/{repo}/commits/{sha}` 的 `files[].patch`，只保留评论文件 + 相邻 hunk；
2. `base_commit` 改成该提交的 `parents[0].sha`，`pr` 保留用于追溯；
3. 提交不包含评论文件时（review 发生在后续 push 之后）用评论自带的 `diff_hunk` + 文件头拼最小 diff；`diff_hunk` 被 GitHub 截断时重算 hunk 行数；
4. `--final-diff` 保留旧的 PR-head 切片，默认关闭。

用 `.cache/gh/` 里的 316 个 PR 重放（`--from-cache`）产出 28 条草稿，人工按"评论当时确实有问题、能从代码本身证明"晋升 11 条（9→20）。其中 4 条是新 `defect`（black#3219 的崩溃、flask#3412 的硬依赖、black#2357 的无限循环、django#9622 的 COT 精度），其余是 design/nit。`defect` 总数 9，差目标 1 条：剩余候选大多是"加测试/拆函数/改风格"，或证据落在评论 hunk 之外（如 urllib3#5330 的 `Retry.from_int` 在评论锚点上方约 30 行），没有强行升级。

**这条修正也适用于下面的"采集时踩的坑 #1"**：确认缺陷是否还在，要对照**评论所在提交**的代码，而不是最终 diff。

**采集时踩的坑（都是"语料本身会撒谎"）**

1. 评论可能已被后续提交修掉：django#18056 最终已加 `field.generated` 检查、redis#1660 最终已在循环后 raise。**必须对照评论所在提交的代码逐条确认缺陷仍在**（见上一小节；2026-11-02 修正）。
2. 过程性意见不是缺陷："add unittests"、"move this comment down"占比很高。
3. AI reviewer 混在真人里：celery#10346/#9799 是 Copilot，pydantic#9459 是 AI 中文评审（`author_association: NONE` + 固定 emoji 前缀），按 `user.type` 与文风剔除。
4. 证据落在切片外：pip#5952 的矛盾点在 `handle_401`，而评论锚在 `_get_new_credentials`——案例对模型不公平，弃用。
5. 行号锚在 outdated diff（`line: null`）的评论无法用，直接丢。

**判分口径**：行号 ±3 只作候选，不看语义。真实语料必须人工判"是不是同一问题"，否则像上面 drf 那条会被尺子判成 miss，而 requests 的 Δ3 命中其实是另一件事。

### `context.neighbors` 在真实语料上的对照（3 轮 × 2 臂）

跨文件用例证明上下文能让"某处调用方"变成"review_cmd.py:215"，但那些用例是**专门造出来考验跨文件**的。真实语料里上下文值不值它 20–30% 的 token，得在 8 条真实用例上实测，每臂跑 3 轮（temperature 0.2，单次运行波动明显）。

| 指标 | 上下文开 | 上下文关 |
|---|---|---|
| 行号 ±3 有 finding（3 轮中任一） | 4 / 8 | 4 / 8 |
| 关键词代理命中（24 次运行中） | 16 / 24 | **20 / 24** |
| 每次评审平均 finding 数 | 15.4 | 16.0 |

**单条最有说服力的差异**是 django/psycopg3：

| 用例 | 上下文开 | 上下文关 |
|---|---|---|
| `real-django-psycopg3-tzloader` 最近行号 | Δ21（3 轮都没落到 `replace(tzinfo=)`） | **Δ4（3/3 轮都落到）** |
| `real-pandas-series-extension-dtype-check` | 关键词出现 1/3 轮 | 3/3 轮 |

也就是说：**在正文级改动上，注入的"谁调用我"没有信息增量，反而会挤掉本来会出现的 finding**——prompt 变长后模型把注意力放在跨文件关系上，忽略了眼前那行 `res.replace(tzinfo=...)`。

**关键词代理的局限**：它只看同文件 finding 里有没有出现 `tzinfo / is_dtype / freq` 这类词，模型"提一嘴"就算命中，比行号宽松、比人工判读宽松。所以上表第二行只能当趋势，不能当结论。

> **2026-11-02 更正**：上面把 psycopg 当成"注入挤掉正文 finding"的证据，复测不成立——同一用例、同一份配置，上下文开的 3 轮全部落在 `psycopg_any.py:30`（Δ4，finding 正文就写着 `res.replace(tzinfo=self.timezone)`），见下一节。这一条大概率是当日模型侧波动，不应再作为"注入有害"的依据。

**决定**：`context.neighbors` 默认**保持开启**。理由是跨文件用例上的收益是具体且大的（点名调用方 0/6 → 6/6），而真实语料的损失目前只观察到一处、且样本 8 条不足以推翻。但把代价写在这里，并且记下下一步该做什么：

1. **按改动形态开关**：只当改动的行落在函数签名 / 装饰器 / 参数列表时注入邻域；正文级改动不注入。这样既能保住签名变更的收益，又不为"改个 if"付 token 和注意力成本。
2. 语料扩到 20 条后再跑一次 3×2，并按 `strictness` 分层统计——8 条里只有 4 条是 `defect`，剩下的是 design/nit，混在一起算命中率会被软用例稀释。

### `neighbors_trigger: signature` 的三臂对照（3 轮 × 3 臂，2026-11-02）

上一条"按改动形态开关"已实现为 `context.neighbors_trigger: always | signature`（默认 `always`，行为不变）。`signature` 的判定比"有改动行落在头部区间"更严：**只有当某个定义自身的改动全部落在头部**（装饰器 / `def` / `class` / 参数列表 / 返回注解）才注入；同一定义里改了正文就不算，模块层改动（import、常量）也不算。头部区间由 `symbol_index.definition_spans()` 用 stdlib `ast` 算，不给 `Symbol` 加字段、不改索引 JSON schema。

方法：8 条真实用例 × 3 臂（`always` / `signature` / `off`）× 3 轮，`deepseek-chat`、temperature 0.2，用例为行号修正后（#29/#31）的版本。Δ = 同文件 LLM finding 与期望行的最近距离，工具 finding 不计。

| 用例 | `always` Δ中位（±3 命中/3 轮） | `signature` | `off` |
|---|---|---|---|
| `real-aiohttp-cause-without-traceback` | 7（0/3） | **3（2/3）** | 12（0/3） |
| `real-django-enqueue-on-commit-single-db` | 4（0/3） | 4（0/3） | 4（0/3） |
| `real-django-psycopg3-tzloader` | 4（0/3） | 4（0/3） | 4（0/3） |
| `real-drf-datetime-local-none-format` | 0（2/3） | 1（**3/3**） | 1（**3/3**） |
| `real-matplotlib-hist-colors-sequence` | 1（3/3） | 2（3/3） | 2（3/3） |
| `real-pandas-series-extension-dtype-check` | 3（2/3） | **1（3/3）** | 1（2/3） |
| `real-pandas-timedeltaarray-freq-no-validation` | 2（2/3） | 4（1/3） | 8（1/3） |
| `real-requests-timedcache-keyerror` | 6（1/3） | 8（1/3） | 8（0/3） |
| **合计** | **10/24** | **13/24** | **9/24** |

- Δ 中位：always 3.5 / signature 3.5 / off 4.0；平均 finding 数：17.4 / 17.4 / 17.6。
- 三臂**在准确率上分不开**：单条 3 轮波动能到 0→26（`real-django-psycopg3-tzloader` 在 signature 臂是 4、4、26），8 条 × 3 轮的样本撑不起"哪个更准"的结论。signature 没有回退，也谈不上提升。

**结构性差异在成本**——按用例逐条算注入的 prompt 字符数（8 条，`max_chars` 2400）：

| 臂 | 注入的用例数 | 平均每次评审的跨文件上下文字符 |
|---|---|---|
| `always` | 7 / 8 | 2100 |
| `signature` | 1 / 8（`pandas-timedelta`，正是加了 `freq` 参数的那条） | 300 |

−86%，约合每次评审省 450 token，且**跨文件 6 条构造上仍全部注入 6/6**（纯签名改名/加参数/改装饰器都会命中），"点名调用方 0/6 → 6/6"的收益不受影响。

**决定**：`always` 保持默认不动（这轮只是把开关做出来并量清楚）。下一步建议把默认切到 `signature`：零回退、成本降 86%、跨文件收益不变；但要先按 `strictness` 分层把语料扩到 20 条复核，再改默认值——那时改动只有一个字段（`ConfigContext.neighbors_trigger` 的 `default`）。

### 夜间门禁（nightly，2026-11-01）

`bench.py --json-out` 把每条用例的候选命中写成 JSON（schema 见脚本 docstring）：

```json
{"generated_at": "...", "config": "...", "cases": [
  {"id": "...", "origin": "real-pr", "kind": "positive", "strictness": "defect", "findings": 17,
   "matched": true, "best_delta": 2, "elapsed": 15.2, "error": null}]}
```

`gate.py` 读取这份 JSON 与签入的 `baseline.json`，按 origin 比较正例的候选命中数；低于基线减 `--tolerance`（默认 0）即退出码 1，并打印未命中的用例名。用例数少于基线（或多于基线，说明基线该刷新）同样判失败。

| 分组 | 基线 | 来源 |
|---|---|---|
| `real_pr` | 5 / 8 | 上面「真实 PR 语料」一轮实测（±3 行） |
| `injected` | 30 / 30 | 24 条 S0 注入（24/24，±5 行）+ 6 条跨文件用例（6/6，±5 行） |

基线是各轮实测结果的组合；首次 nightly 若与实测有出入，以实际报告刷新 `baseline.json`（同时确认差异是模型噪声还是真回归）。

`.github/workflows/benchmark.yml` 每天 18:00 UTC 跑一次（也可手动 `workflow_dispatch`）：Python 3.11、`pip install -e "python[dev]"`、`bench.py --validate`、`bench.py --all --config tests/benchmark/bench.yaml --json-out ...`、`gate.py`，报告与 JSON 作为 artifact 上传。仓库没有 `DEEPSEEK_API_KEY`（fork / 未配 secret）时整个作业跳过并输出 notice，不会红。

**门禁只看候选命中，不看语义**：它用来发现"这次改动让基准变差"的量级回归，不能代替上面 2/8 的人工语义判定。

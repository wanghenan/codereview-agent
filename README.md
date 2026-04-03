# CodeReview Agent

🤖 AI 驱动的 CodeReview 智能体，自动识别代码风险，让每一次提交都有底气的 Code Review 工具。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/wanghenan/codereview-agent)](https://github.com/wanghenan/codereview-agent/stargazers)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Discord](https://img.shields.io/discord/123456789?label=Discord)](https://discord.gg/codereview-agent)

---

## 一句话介绍

**CodeReview Agent** 利用 AI 技术自动分析代码变更，智能识别安全风险和质量缺陷，提供 0-100% 置信度评分，帮助团队快速决定哪些代码可以直接合并、哪些需要人工重点审核。

---

## ✨ 核心亮点

| 亮点 | 说明 |
|------|------|
| 🎯 **置信度评分** | 0-100% 可视化评分，50% 以下建议人工审核，50% 以上可放心合并 |
| 🌐 **6 大 LLM 支持** | OpenAI、Anthropic、智谱AI、MiniMax、阿里云、DeepSeek |
| 🔒 **自托管部署** | 支持私有化部署，数据不出网，适合安全敏感团队 |
| 🛠️ **智能修复** | 发现问题？直接生成修复代码，一键应用！ |
| 🔄 **自动合并** | 审查通过后自动合并 PR，省去人工操作 |
| 🔁 **智能重试** | 失败任务自动重试（3次 + 指数退避），不遗漏 |
| 📊 **代码复杂度评分** | 多维度量化代码复杂度，识别潜在技术债务 |
| 📈 **可视化报告** | 清晰的 Markdown 报告，风险分级一目了然 |
| 🔄 **历史回溯** | 智能缓存机制，支持历史对比和趋势分析 |
| 👥 **团队洞察** | 统计团队 review 数据，识别高频问题模式 |

---

## 🚀 新功能 - 试试看！

### 🔧 智能修复 - 一键修复代码问题

```bash
# 预览修复（风险汇总 + 文件分组 + Git Diff）
python -m codereview.cli fix --pr 123

# 应用修复（交互确认）
python -m codereview.cli fix --pr 123 --apply

# 应用修复（CI模式，跳过确认）
python -m codereview.cli fix --pr 123 --apply --yes
```

**🆕 新增特性：**
- 📊 风险级别汇总（🔴高 / 🟡中 / 🟢低）
- 📄 按文件分组显示
- 📝 Git-style Diff 预览
- ⚠️ 交互确认提示，防止误操作
- 📊 应用后显示变更汇总

**[→ 智能修复完整指南](./docs/fix-command.md)**

### 🔄 自动合并 - 审查通过自动合

```bash
# Review + Merge 预览
python -m codereview.cli review --pr 123 --auto-merge

# 单独 merge 命令
python -m codereview.cli merge --pr 123 --dry-run

# 强制合并（跳过条件检查）
python -m codereview.cli merge --pr 123 --force
```

**🆕 新增特性：**
- 🔄 `review --auto-merge` 一体化命令
- 💪 `--force` 跳过条件强制合并
- 📊 实时进度显示

**[→ 自动合并完整指南](./docs/auto-merge.md)**

### 📦 缓存优化 - Patch 规范化

相同逻辑的代码（仅格式变化）不会重复消耗 LLM token。

**[→ 缓存机制详解](./docs/cache.md)**

### 📝 自定义提示词

支持自定义 system prompt，满足团队特定审查标准。

**[→ 配置详解](./docs/configuration.md)**

---

## 🚀 3 分钟快速开始

### 第一步：创建配置文件

在项目根目录创建 `.codereview-agent.yaml`：

```yaml
llm:
  provider: minimax  # 支持: openai, anthropic, zhipu, minimax, qwen, deepseek
  apiKey: ${LLM_API_KEY}
  model: abab6.5s-chat
```

### 第二步：添加 GitHub Action

创建 `.github/workflows/codereview.yml`：

```yaml
name: CodeReview Agent
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: wanghenan/codereview-agent@v1
        with:
          config: .codereview-agent.yaml
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

### 第三步：配置 Secrets

在 GitHub 仓库 Settings → Secrets → Actions 中添加 `LLM_API_KEY`

创建 PR → 自动 review！🎉

---

## 📖 三种使用方式

### 方式一：GitHub Action（推荐）

自动化集成，PR 自动触发 review，结果直接评论到 PR 上。

```yaml
# .github/workflows/codereview.yml
name: CodeReview Agent
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: wanghenan/codereview-agent@v1
        with:
          config: .codereview-agent.yaml
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

**[→ 查看完整 GitHub Action 配置](./docs/USER_GUIDE.md)**

---

### 方式二：Docker

适合本地测试或 CI/CD 流水线：

```bash
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-key \
  wanghenan/codereview-agent --pr 123
```

**[→ 查看 Docker 部署指南](./docs/USER_GUIDE.md#方式二docker)**

---

### 方式三：本地 CLI

直接在本项目运行：

```bash
# 1. 克隆项目
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent/python

# 2. 安装依赖
uv venv && source .venv/bin/activate
pip install -e .

# 3. 配置并运行
cp /path/to/.codereview-agent.yaml ./
python -m codereview.cli --diff '{\"files\": [...]}'
```

**[→ 查看 CLI 完整用法](./docs/USER_GUIDE.md#方式三本地-cli)**

---

## 📋 功能列表

### 🔍 核心功能

| 功能 | 说明 |
|------|------|
| 智能风险识别 | 自动检测安全漏洞、SQL注入、硬编码密钥、敏感信息泄露等 |
| 置信度评分 | 基于问题严重程度计算 0-100% 置信度 |
| 风险分级 | 🔴高 / 🟡中 / 🟢低 三级风险标注 |
| 修复建议 | 每项问题提供具体修复方案 |

### 🧠 智能功能

| 功能 | 说明 |
|------|------|
| 代码复杂度评分 | 从圈复杂度、嵌套深度、函数长度等维度评分 |
| 智能缓存 | 自动缓存 review 结果，避免重复分析 |
| 自定义提示词 | 支持自定义分析 prompt，满足团队特定需求 |
| 多 LLM 路由 | 根据场景自动选择最合适的模型 |
| 智能重试 | 自动重试失败任务（3次重试 + 指数退避） |

### 🌐 多语言支持

| 语言 | 状态 |
|------|------|
| Python | ✅ 完整支持 |
| JavaScript / TypeScript | ✅ 完整支持 |
| Go | ✅ 完整支持 |
| Java | ✅ 完整支持 |
| Rust | ✅ 完整支持 |
| PHP | ✅ 完整支持 |
| C / C++ | ✅ 完整支持 |
| 更多语言 | 🔄 持续更新 |

### 🛠️ IDE 集成

| 集成方式 | 说明 |
|----------|------|
| VS Code 插件 | 实时分析当前文件， inline 显示风险提示 |
| GitHub Action | PR 自动触发，评论直达 |
| Webhook | 支持对接内部系统 |

### 📊 分析功能

| 分析类型 | 说明 |
|----------|------|
| 安全分析 | 漏洞检测、密钥泄露、依赖风险 |
| 代码质量 | 坏味道检测、代码规范 |
| 复杂度分析 |圈复杂度、认知复杂度、函数长度 |
| 历史趋势 | review 历史对比，技术债务追踪 |

### ⚙️ 自动化

| 自动化 | 说明 |
|--------|------|
| PR 自动 review | GitHub Action 自动触发 |
| 定时扫描 | 支持定时全量代码扫描 |
| CI/CD 集成 | 无缝集成现有 CI/CD 流水线 |
| 自定义规则 | 支持团队特定规则配置 |

---

## 📊 示例输出

### 高风险代码检测

```
## CodeReview Agent 🤖

**结论**: ⚠️ 需要人工审核 (置信度: 95%)

| 文件 | 风险 | 问题数 |
|------|------|--------|
| `src/auth/login.ts` | 🔴 高 | 3 |

### 问题

1. 🔴 HIGH: 硬编码 API Key
2. 🔴 HIGH: SQL 注入漏洞  
3. 🔴 HIGH: 发送凭据到外部服务
```

### 低风险代码

```
## CodeReview Agent 🤖

**结论**: ✅ 可提交 (置信度: 88%)

| 文件 | 风险 | 问题数 |
|------|------|--------|
| `src/utils/helper.ts` | 🟢 低 | 1 |

### 问题

1. 🟡 LOW: 未使用的导入 (可忽略)
```

---

## 💰 LLM Provider 选择指南

| 场景 | 推荐 | 理由 |
|------|------|------|
| 代码质量优先 | OpenAI (gpt-4o) / Anthropic (claude-sonnet) | 理解力最强 |
| 性价比优先 | 智谱AI (glm-4-flash) / DeepSeek | 免费/低价 |
| 国内访问 | MiniMax / 智谱AI / 阿里云 | 无需翻墙 |
| 安全敏感 | 自部署 + 开源模型 | 数据不出网 |

---

## ❓ 常见问题

**Q: CodeReview Agent 是免费的吗？**
> 工具本身免费，仅需支付 LLM API 调用费用，每次约 $0.01-$0.05

**Q: 我的代码会泄露吗？**
> 不会！仅上传 diff（变更内容），不上传完整源码，API 直连你的账户

**Q: 置信度是怎么计算的？**
> Critical = 100%, High = 75%, Medium = 50%, Low = 25%，无问题 = 100%

**[→ 查看更多 FAQ](./docs/USER_GUIDE.md#常见问题)**

---

## 🛠️ 技术栈

- **核心**: Python 3.10+ / LangChain / LangGraph
- **LLM**: OpenAI, Anthropic, 智谱AI, MiniMax, 阿里云, DeepSeek
- **部署**: GitHub Actions, Docker, CLI, VS Code

---

## 📚 完整文档

- [📖 文档首页](./docs/README.md) - **推荐从这里开始**
- [📖 用户指南](./docs/USER_GUIDE.md) - 完整的使用说明和配置参考
- [🔧 智能修复](./docs/fix-command.md) - 一键修复代码问题
- [🔄 自动合并](./docs/auto-merge.md) - 审查通过自动合并
- [💾 缓存机制](./docs/cache.md) - Patch 规范化，节省 token
- [⚙️ 配置详解](./docs/configuration.md) - 自定义提示词、重试机制
- [📊 AI vs 人工对比](./docs/COMPARISON.md) - 效率分析和成本对比
- [💡 使用场景](./docs/USE_CASES.md) - 真实用户故事
- [❓ 常见问题](./docs/faq.md) - FAQ 解答
- [🔧 故障排查](./docs/troubleshooting.md) - 问题诊断与解决

---

## 🤝 贡献指南

欢迎提交 Issue 和 PR！请先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 📄 License

MIT License

---

<p align="center">
  <sub>Built with ❤️ by the CodeReview Agent team</sub>
</p>

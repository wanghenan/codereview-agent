# CodeReview Agent

🤖 AI 驱动的 CodeReview 智能体，帮助程序员自动识别哪些代码可提交、哪些需要人工审核。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/wanghenan/codereview-agent)](https://github.com/wanghenan/codereview-agent/stargazers)
[![Discord](https://img.shields.io/discord/123456789?label=Discord)](https://discord.gg/codereview-agent)
[![Twitter](https://img.shields.io/twitter/follow/codereview_agent?style=social)](https://twitter.com/codereview_agent)

---

## ✨ 特性

- 🔍 **智能风险识别** - 自动检测安全漏洞、SQL注入、硬编码密钥等问题
- 📊 **置信度评分** - 基于问题严重程度计算 0-100% 置信度
- 🤖 **基于 LangChain + LangGraph** - 模块化、易扩展
- 🌐 **6 大 LLM Provider** - OpenAI、Anthropic、智谱AI、MiniMax、阿里云、DeepSeek
- 🚀 **三种使用方式** - GitHub Action / Docker / CLI
- 🔒 **代码隐私保护** - 仅上传 diff，不上传源码

## 📖 文档

**[📚 完整使用指南 →](./docs/USER_GUIDE.md)**

---

## 🤔 为什么选择 CodeReview Agent？

### 横向对比

| 特性 | CodeReview Agent | GitHub Copilot | DeepCode | SonarQube |
|------|------------------|----------------|----------|-----------|
| **AI 智能分析** | ✅ 基于 LLM | ✅ 生成式 | ✅ ML | ❌ 规则引擎 |
| **置信度评分** | ✅ 0-100% | ❌ | ❌ | ⚠️ 质量门禁 |
| **自动风险分级** | 🔴高/🟡中/🟢低 | ❌ | ✅ | ✅ |
| **多 LLM 支持** | ✅ 6家 | ❌ 仅 OpenAI | ❌ | N/A |
| **国产模型支持** | ✅ 智谱/MiniMax/阿里 | ❌ | ❌ | N/A |
| **GitHub Action** | ✅ 开箱即用 | ✅ | ❌ | ✅ |
| **本地 CLI** | ✅ | ❌ | ❌ | ❌ |
| **免费使用** | ✅ (API 成本自费) | 💰 订阅制 | 💰 企业版 | ✅ 社区版 |

### 核心优势

| 优势 | 说明 |
|------|------|
| 🎯 **精准定位** | 不仅发现问题，还告诉你严重程度和修复建议 |
| 📈 **效率提升** | 10 秒完成全量 review，人工仅需复核高风险 |
| 🧠 **智能判断** | 基于置信度评分，0-50% 建议人工审核，50-100% 可直接合并 |
| 🌏 **本土化** | 完美支持国产大模型，国内访问快、价格低 |
| 🔌 **零门槛接入** | 一行 YAML 配置，PR 自动触发 review |

---

## 🚀 快速开始

### 方式一：GitHub Action (推荐)

在 **你的项目** 中添加：

**1. `.github/workflows/codereview.yml`**

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

**2. `.codereview-agent.yaml`**

```yaml
llm:
  provider: minimax
  apiKey: ${{ secrets.LLM_API_KEY }}
  model: abab6.5s-chat
```

**3. 添加 GitHub Secrets**
- Settings → Secrets → `LLM_API_KEY`

创建 PR → 自动 review！🎉

---

### 方式二：Docker

```bash
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-key \
  wanghenan/codereview-agent --pr 123
```

---

### 方式三：本地 CLI

```bash
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent/python
pip install -e .

# 在你的项目运行
python -m codereview.cli --diff diff.json
```

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

## ❓ 常见问题 FAQ

### 基础问题

**Q: CodeReview Agent 是免费的吗？**
> A: 工具本身免费，你只需要支付 LLM API 的调用费用。每次 review 成本约 $0.01-$0.05（取决于模型）。

**Q: 我的代码会泄露吗？**
> A: 不会。我们只上传 diff（变更内容），不上传完整源代码。API 调用也通过你的账户直接调用，不经过第三方服务器。

**Q: 支持哪些编程语言？**
> A: 目前支持 Python、JavaScript、TypeScript、Go、Java。更多语言持续更新中。

### 使用问题

**Q: 如何选择 LLM Provider？**

| 场景 | 推荐 | 理由 |
|------|------|------|
| 代码质量优先 | OpenAI (gpt-4o) / Anthropic (claude-sonnet) | 理解力最强 |
| 性价比优先 | 智谱AI (glm-4-flash) / DeepSeek | 免费/低价 |
| 国内访问 | MiniMax / 智谱AI / 阿里云 | 无需翻墙 |
| 安全敏感 | 自部署 + 开源模型 | 数据不出网 |

**Q: 置信度是怎么计算的？**
> A: 基于问题严重程度加权计算。Critical = 100%, High = 75%, Medium = 50%, Low = 25%。无问题 = 100%。

**Q: 可以自定义提示词吗？**
> A: 可以。参考 `custom-prompt.template` 文件。

### 集成问题

**Q: GitHub Action 触发失败怎么办？**
> 1. 确认 `.codereview-agent.yaml` 存在且格式正确
> 2. 确认 secrets 已正确配置
> 3. 查看 Actions 日志排查

**Q: 如何禁用自动评论？**
> A: 在配置中设置 `output.prComment: false`

---

## 🛠️ 技术栈

- **核心**: Python 3.10+ / LangChain / LangGraph
- **LLM**: OpenAI, Anthropic, 智谱AI, MiniMax, 阿里云, DeepSeek
- **部署**: GitHub Actions, Docker

---

## 📄 License

MIT License - 欢迎贡献！

---

## 🔗 相关链接

- [📚 完整使用指南](./docs/USER_GUIDE.md)
- [📊 AI vs 人工对比](./docs/COMPARISON.md)
- [💡 使用场景故事](./docs/USE_CASES.md)
- [🎮 更新日志](https://github.com/wanghenan/codereview-agent/releases)
- [🐛 问题反馈](https://github.com/wanghenan/codereview-agent/issues)

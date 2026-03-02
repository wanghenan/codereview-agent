# CodeReview Agent 🤖

[🇨🇳 中文](./README.md) | [🇺🇸 English](./README_EN.md)

AI 驱动的 CodeReview 智能体，帮助程序员自动识别哪些代码可提交、哪些需要人工审核。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/wanghenan/codereview-agent)](https://github.com/wanghenan/codereview-agent/stargazers)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)
[![Version](https://img.shields.io/badge/Version-v1-green.svg)](https://github.com/wanghenan/codereview-agent/releases)
[![LangChain](https://img.shields.io/badge/LangChain-Latest-orange.svg)](https://langchain.dev)

---

## ✨ 特性

- 🔍 **智能风险识别** - 自动检测安全漏洞、SQL注入、硬编码密钥等问题
- 📊 **置信度评分** - 基于问题严重程度计算 0-100% 置信度
- 🤖 **基于 LangChain + LangGraph** - 模块化、易扩展
- 🌐 **6 大 LLM Provider** - OpenAI、Anthropic、智谱AI、MiniMax、阿里云、DeepSeek
- 🚀 **三种使用方式** - GitHub Action / Docker / CLI

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

---

## 🛠️ 技术栈

- **核心**: Python 3.10+ / LangChain / LangGraph
- **LLM**: OpenAI, Anthropic, 智谱AI, MiniMax, 阿里云, DeepSeek
- **部署**: GitHub Actions, Docker

---

## 📄 License

MIT License - 欢迎贡献！

---

<div align="center">

**如果这个项目对你有帮助，欢迎 ⭐ Star！**

</div>

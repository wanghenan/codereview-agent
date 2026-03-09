# CodeReview Agent

🤖 AI-powered CodeReview agent that automatically identifies which code is ready to merge and what requires human review.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/wanghenan/codereview-agent)](https://github.com/wanghenan/codereview-agent/stargazers)

---

## ✨ Features

- 🔍 **Smart Risk Detection** - Automatically detect security vulnerabilities, SQL injection, hardcoded keys, etc.
- 📊 **Confidence Scoring** - Calculate 0-100% confidence based on issue severity
- 🤖 **Built on LangChain + LangGraph** - Modular and extensible
- 🌐 **6 LLM Providers** - OpenAI, Anthropic, Zhipu AI, MiniMax, Alibaba Cloud, DeepSeek
- 🚀 **3 Usage Modes** - GitHub Action / Docker / CLI
- 🔒 **Code Privacy** - Only uploads diffs, not source code

---

## 📖 Documentation

**[📚 Full User Guide →](./docs/USER_GUIDE.md)**

---

## 🤔 Why Choose CodeReview Agent?

### Feature Comparison

| Feature | CodeReview Agent | GitHub Copilot | DeepCode | SonarQube |
|---------|------------------|----------------|----------|-----------|
| **AI Analysis** | ✅ LLM-based | ✅ Generative | ✅ ML | ❌ Rules |
| **Confidence Score** | ✅ 0-100% | ❌ | ❌ | ⚠️ Quality Gates |
| **Auto Risk Classification** | 🔴High/🟡Med/🟢Low | ❌ | ✅ | ✅ |
| **Multi-LLM Support** | ✅ 6 providers | ❌ OpenAI only | ❌ | N/A |
| **China Models** | ✅ Zhipu/MiniMax/Aliyun | ❌ | ❌ | N/A |
| **GitHub Action** | ✅ Out of box | ✅ | ❌ | ✅ |
| **Local CLI** | ✅ | ❌ | ❌ | ❌ |
| **Free to Use** | ✅ (API cost only) | 💰 Subscription | 💰 Enterprise | ✅ Community |

### Key Benefits

| Benefit | Description |
|---------|-------------|
| 🎯 **Precise Detection** | Not just finding issues, but also severity levels and fix suggestions |
| 📈 **Efficiency Boost** | 10 seconds for full review, humans only need to review high-risk |
| 🧠 **Smart Decision** | Based on confidence: 0-50% = human review needed, 50-100% = ready to merge |
| 🌏 **Localization** | Full support for Chinese LLM providers, fast access in China |
| 🔌 **Zero-config** | One-line YAML config, auto-review on PR |

---

## 🚀 Quick Start

### Option 1: GitHub Action (Recommended)

Add to **your project**:

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
  provider: openai
  apiKey: ${{ secrets.LLM_API_KEY }}
  model: gpt-4o
```

**3. Add GitHub Secrets**
- Settings → Secrets → `LLM_API_KEY`

Create PR → Auto review! 🎉

---

### Option 2: Docker

```bash
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-key \
  wanghenan/codereview-agent --pr 123
```

---

### Option 3: Local CLI

```bash
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent/python
pip install -e .

# Run in your project
python -m codereview.cli --diff diff.json
```

---

## 📊 Sample Output

### High Risk Detection

```
## CodeReview Agent 🤖

**Conclusion**: ⚠️ Needs Human Review (Confidence: 95%)

| File | Risk | Issues |
|------|------|--------|
| `src/auth/login.ts` | 🔴 High | 3 |

### Issues

1. 🔴 HIGH: Hardcoded API Key
2. 🔴 HIGH: SQL Injection Vulnerability
3. 🔴 HIGH: Credentials Sent to External Service
```

---

## ❓ FAQ

**Q: Is CodeReview Agent free?**
> A: The tool itself is free. You only pay for LLM API calls (~ $0.01-$0.05 per review).

**Q: Is my code secure?**
> A: Yes. We only upload diffs (changes), not full source code. API calls go directly through your account.

**Q: Which programming languages are supported?**
> A: Python, JavaScript, TypeScript, Go, Java currently. More coming soon.

**Q: How is confidence calculated?**
> A: Weighted by severity: Critical=100%, High=75%, Medium=50%, Low=25%. No issues=100%.

---

## 🛠️ Tech Stack

- **Core**: Python 3.10+ / LangChain / LangGraph
- **LLM**: OpenAI, Anthropic, Zhipu AI, MiniMax, Alibaba Cloud, DeepSeek
- **Deployment**: GitHub Actions, Docker

---

## 📄 License

MIT License - Contributions welcome!

---

## 🔗 Links

- [📚 Full User Guide](./docs/USER_GUIDE.md)
- [📊 AI vs Human Comparison](./docs/COMPARISON.md)
- [💡 Use Cases](./docs/USE_CASES.md)
- [🎮 Changelog](https://github.com/wanghenan/codereview-agent/releases)
- [🐛 Issues](https://github.com/wanghenan/codereview-agent/issues)

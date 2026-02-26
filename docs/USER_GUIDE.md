# CodeReview Agent 使用指南

一个 AI 驱动的 CodeReview 工具，自动识别代码变更中的风险，帮助你决定是否可以提交。

**⚡ 特色功能：**
- 🤖 基于 LangChain + LangGraph 构建
- 🔍 自动识别高风险代码（安全漏洞、SQL注入、硬编码密钥）
- 📊 置信度评分 (0-100%)
- 📝 支持 6 个 LLM Provider
- 🚀 GitHub Action / Docker / CLI 三种使用方式

---

## 快速开始

### 方式一：GitHub Action (推荐)

在 **你的项目** 中添加以下文件：

**1. 创建 `.github/workflows/codereview.yml`：**

```yaml
name: CodeReview Agent

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  codereview:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run CodeReview Agent
        uses: wanghenan/codereview-agent@v1
        with:
          config: .codereview-agent.yaml
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

**2. 创建 `.codereview-agent.yaml`：**

```yaml
llm:
  provider: minimax  # 或: openai, anthropic, zhipu, qwen, deepseek
  apiKey: ${{ secrets.LLM_API_KEY }}
  model: abab6.5s-chat

criticalPaths:
  - src/auth
  - src/payment

excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
```

**3. 在 GitHub 仓库添加 secrets：**
- Settings → Secrets and variables → Actions → New repository secret
- 添加 `LLM_API_KEY`

**4. 创建 PR → 自动 review！**

---

### 方式二：本地 CLI

```bash
# 1. 克隆
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent/python

# 2. 安装
uv venv && source .venv/bin/activate
pip install -e .

# 3. 在你的项目配置
cd 你的项目目录
cp /path/to/codereview-agent/.codereview-agent.yaml ./

# 4. 编辑 .codereview-agent.yaml，填入你的 API Key

# 5. 运行
python -m codereview.cli --diff '{"files": [...]}'
```

---

### 方式三：Docker

```bash
# 构建
docker build -t codereview-agent \
  https://github.com/wanghenan/codereview-agent.git#main

# 运行
docker run -v $(pwd):/app \
  -e LLM_API_KEY=你的KEY \
  codereview-agent --pr 123
```

---

## 配置说明

### 完整配置项

```yaml
# .codereview-agent.yaml

# LLM 配置 (必需)
llm:
  provider: openai  # openai | anthropic | zhipu | minimax | qwen | deepseek
  apiKey: ${LLM_API_KEY}
  model: gpt-4o  # 可选
  baseUrl: ""  # 可选，自定义API地址

# 关键路径 (高风险区域)
criticalPaths:
  - src/auth
  - src/payment
  - src/admin

# 排除文件
excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
  - "vendor/**"

# 缓存配置
cache:
  ttl: 7  # 天数
  forceRefresh: false

# 输出配置
output:
  prComment: true
  reportPath: .codereview-agent/output
  reportFormat: markdown
```

---

## LLM Provider

| Provider | 模型示例 | 获取 API Key |
|----------|----------|--------------|
| OpenAI | gpt-4o, gpt-5.2 | [platform.openai.com](https://platform.openai.com/api-keys) |
| Anthropic | claude-sonnet-4.6 | [console.anthropic.com](https://console.anthropic.com/) |
| 智谱AI | glm-4-flash | [open.bigmodel.cn](https://open.bigmodel.cn/) |
| MiniMax | abab6.5s-chat | [platform.minimax.io](https://platform.minimax.io/) |
| 阿里云 | qwen-plus | [bailian.aliyun.com](https://bailian.aliyun.com/) |
| DeepSeek | deepseek-chat | [platform.deepseek.com](https://platform.deepseek.com/) |

---

## 输出示例

### PR 评论

```
## CodeReview Agent 🤖

**结论**: ⚠️ 需要人工审核 (置信度: 95%)

| 文件 | 风险 | 问题数 |
|------|------|--------|
| `src/auth/login.ts` | 🔴 高 | 3 |

### 问题摘要

1. 🔴 HIGH: 硬编码 API Key
2. 🔴 HIGH: SQL 注入漏洞
3. 🔴 HIGH: 发送凭据到外部服务
```

### 结论说明

| 结论 | 置信度 | 说明 |
|------|--------|------|
| ✅ 可提交 | 50-100% | 无高风险问题，可直接合并 |
| ⚠️ 需人工审核 | 0-95% | 存在高风险问题，需要人工审查 |

---

## 常见问题

### Q: 如何选择 Provider？

| 场景 | 推荐 |
|------|------|
| 代码能力最强 | OpenAI (gpt-5) / Anthropic (claude) |
| 性价比优先 | 智谱AI / DeepSeek |
| 国内访问快 | 智谱AI / MiniMax / 阿里云 |

### Q: 缓存会自动更新吗？

会。当以下情况会发生：
- package.json 等版本文件变更
- 超过 TTL (默认7天)
- 手动触发 `@codereview-agent refresh`

### Q: 支持私有部署的 LLM 吗？

支持。配置 `baseUrl` 指向你的 API：

```yaml
llm:
  provider: openai
  apiKey: dummy
  baseUrl: http://localhost:8080/v1
  model: your-model
```

---

## 项目结构

```
codereview-agent/
├── python/          # 核心引擎 (LangChain + LangGraph)
├── nodejs/          # Node.js 包装器
├── docker/          # Docker 配置
├── .github/workflows/  # GitHub Action
└── docs/
    └── USER_GUIDE.md  # 本文档
```

---

## License

MIT License

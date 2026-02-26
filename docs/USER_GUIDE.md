# CodeReview Agent 使用指南

一个通用的、基于AI的CodeReview智能体，帮助程序员自动识别哪些代码可提交、哪些需要人工审核。

## 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [LLM Provider 配置](#llm-provider-配置)
- [三种使用方式](#三种使用方式)
- [输出示例](#输出示例)
- [缓存机制](#缓存机制)
- [自定义Prompt](#自定义prompt)
- [常见问题](#常见问题)

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-org/codereview-agent.git
cd codereview-agent
```

### 2. 配置LLM

在项目根目录创建 `.codereview-agent.yaml` 配置文件：

```yaml
llm:
  provider: openai  # 或: anthropic, zhipu, minimax, qwen, deepseek
  apiKey: your-api-key-here
  model: gpt-4o  # 可选，默认会根据provider选择最佳模型
  baseUrl: ""  # 可选，用于自定义API地址（如代理）
```

### 3. 运行

```bash
# Docker 方式
docker run -v $(pwd):/app codereview-agent --pr 123

# 或 GitHub Action (见下文)
```

---

## 配置说明

### 完整配置项

```yaml
# .codereview-agent.yaml

# LLM 配置 (必需)
llm:
  provider: openai  # required: openai | anthropic | zhipu | minimax | qwen | deepseek
  apiKey: ${LLM_API_KEY}  # 支持环境变量
  model: gpt-4o  # 可选，默认模型见下文
  baseUrl: ""  # 可选，自定义API地址

# 关键路径配置 (可选)
# 这些目录下的文件变更将被视为高风险
criticalPaths:
  - src/auth
  - src/payment
  - src/admin
  - models/

# 排除模式 (可选)
# 这些文件将被跳过
excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
  - "*.mock.ts"
  - "vendor/**"
  - "node_modules/**"
  - "dist/**"

# 缓存配置 (可选)
cache:
  ttl: 7d  # 缓存有效期，默认7天
  forceRefresh: false  # 是否强制刷新缓存

# 自定义Prompt (可选)
# customPrompt: ./custom-prompt.template

# 输出配置 (可选)
output:
  prComment: true  # 是否在PR上评论
  reportPath: .codereview-agent/output  # 报告输出路径
  reportFormat: markdown  # markdown | json | both
```

### 默认模型

| Provider | 默认模型 |
|----------|----------|
| OpenAI | gpt-4o |
| Anthropic | claude-sonnet-4-20250514 |
| 智谱AI | glm-4-flash |
| MiniMax | abab6.5s-chat |
| 阿里云 | qwen-plus |
| DeepSeek | deepseek-chat |

---

## LLM Provider 配置

### OpenAI

```yaml
llm:
  provider: openai
  apiKey: ${OPENAI_API_KEY}
  model: gpt-5.2  # 或 gpt-4o, o1, o3-mini 等
```

**可用模型**: `gpt-5.2`, `gpt-5.1`, `gpt-5`, `gpt-4o`, `gpt-4.1`, `o1`, `o3`, `o3-mini`

**获取API Key**: [OpenAI Platform](https://platform.openai.com/api-keys)

---

### Anthropic

```yaml
llm:
  provider: anthropic
  apiKey: ${ANTHROPIC_API_KEY}
  model: claude-sonnet-4.6  # 或 claude-opus-4.6, claude-haiku-4.5 等
```

**可用模型**: `claude-opus-4.6`, `claude-sonnet-4.6`, `claude-opus-4.5`, `claude-sonnet-4.5`, `claude-haiku-4.5`

**获取API Key**: [Anthropic Console](https://console.anthropic.com/)

---

### 智谱AI (Zhipu AI)

```yaml
llm:
  provider: zhipu
  apiKey: ${ZHIPU_API_KEY}
  model: glm-4-flash  # 或 glm-5, glm-4.7 等
```

**可用模型**: `glm-5`, `glm-4-flash`, `glm-4.7`, `glm-4.6V`, `glm-4.5`

**获取API Key**: [智谱AI开放平台](https://open.bigmodel.cn/)

---

### MiniMax

```yaml
llm:
  provider: minimax
  apiKey: ${MINIMAX_API_KEY}
  model: abab6.5s-chat  # 或 MiniMax-M2.5 等
```

**可用模型**: `MiniMax-M2.5`, `MiniMax-M2.1`, `abab6.5s-chat`, `abab6.5-chat`

**获取API Key**: [MiniMax开放平台](https://platform.minimax.io/)

---

### 阿里云 (Qwen)

```yaml
llm:
  provider: qwen
  apiKey: ${DASHSCOPE_API_KEY}
  model: qwen-plus  # 或 qwen3-max, qwen3.5-plus 等
```

**可用模型**: `qwen3-max`, `qwen3.5-plus`, `qwen-plus`, `qwen-turbo`, `qwen-long`

**获取API Key**: [阿里云百炼](https://bailian.aliyun.com/)

---

### DeepSeek

```yaml
llm:
  provider: deepseek
  apiKey: ${DEEPSEEK_API_KEY}
  model: deepseek-chat  # 或 deepseek-coder-v2, deepseek-v3 等
```

**可用模型**: `deepseek-chat`, `deepseek-coder-v2`, `deepseek-v3`, `deepseek-v3.2`

**获取API Key**: [DeepSeek Platform](https://platform.deepseek.com/)

---

## 三种使用方式

### 方式一: GitHub App (推荐)

1. **安装**
   - 访问 [GitHub Marketplace](https://github.com/marketplace/) 搜索 CodeReview Agent
   - 点击 "Install" 并选择需要配置的仓库

2. **配置**
   - 在仓库根目录创建 `.codereview-agent.yaml`
   - 在 GitHub App 设置中添加 `LLM_API_KEY` 环境变量

3. **使用**
   - 自动触发：创建或更新 PR 时自动运行
   - 手动触发：在 PR 中评论 `@codereview-agent review`

---

### 方式二: GitHub Action

1. **创建 workflow 文件**

```yaml
# .github/workflows/codereview.yml
name: CodeReview Agent

on:
  pull_request:
    types: [opened, synchronize]
  workflow_dispatch:

jobs:
  codereview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run CodeReview Agent
        uses: your-org/codereview-agent@v1
        with:
          config: .codereview-agent.yaml
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

2. **配置 secrets**
   - 在仓库设置中添加 `LLM_API_KEY` secrets

---

### 方式三: Docker

1. **构建镜像**

```bash
docker build -t codereview-agent .
```

2. **运行**

```bash
# 方式A: 指定PR编号
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-api-key \
  codereview-agent --pr 123

# 方式B: 指定配置文件
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-api-key \
  codereview-agent --config /app/.codereview-agent.yaml

# 方式C: 使用docker-compose
docker-compose up
```

---

## 输出示例

### PR 评论

```
## CodeReview Agent 🤖

**结论**: ✅ 可提交 (置信度: 92%)

### 变更摘要

| 文件 | 风险 | 问题数 |
|------|------|--------|
| src/auth/login.ts | 🟡 中 | 2 |
| src/utils/helper.ts | 🟢 低 | 3 |
| src/config/db.ts | 🔴 高 | 1 |

### 详细问题

#### src/auth/login.ts (🟡 中)
- L12: 魔法数字，建议提取为常量 `MAX_LOGIN_ATTEMPTS`
- L23: 空catch块，建议添加错误日志

#### src/config/db.ts (🔴 高)
- L5: 检测到硬编码数据库连接凭证，请使用环境变量
```

---

### 报告文件

```markdown
# CodeReview Report

**日期**: 2024-01-15
**PR**: #123
**结论**: 需人工审核 (置信度: 78%)
**缓存**: 基于2024-01-10分析

---

## 变更文件

### src/payment/payment.ts
- **风险等级**: 🔴 高
- **变更行数**: +45, -12
- **问题**:
  1. [高] L23: 支付金额计算缺少精度处理
  2. [中] L56: 建议添加重试机制
```

---

## 缓存机制

### 工作原理

1. **首次运行**: 完整分析项目，生成缓存文件 `.codereview-agent/cache/project-context.md`
2. **后续运行**: 
   - 检查项目版本号 (package.json, go.mod 等)
   - 检查缓存是否过期 (默认7天)
   - 如无变化，使用缓存；如有变化，自动重新分析

### 缓存内容

```
.codereview-agent/cache/
└── project-context.md
    ├── 项目技术栈
    ├── 依赖版本
    ├── 代码风格规范
    ├── 目录结构
    ├── 关键模块识别
    └── 分析时间戳
```

### 手动刷新

在 PR 评论中输入:
```
@codereview-agent refresh
```

或在配置中设置:

```yaml
cache:
  forceRefresh: true
```

---

## 自定义Prompt

### 使用自定义Prompt模板

```yaml
customPrompt: ./custom-prompt.template
```

### Prompt 模板示例

```markdown
你是一个资深的CodeReview专家。你的任务是：
1. 分析代码变更
2. 识别潜在问题
3. 给出是否可以提交的建议

## 项目背景
{{project_context}}

## 变更文件
{{changed_files}}

## 用户配置规则
{{user_rules}}

请按以下格式输出：
## 结论
可提交/需人工审核

## 置信度
X%

## 问题列表
...
```

---

## 常见问题

### Q1: 如何选择LLM Provider？

| 场景 | 推荐 Provider |
|------|---------------|
| 代码能力最强 | OpenAI (gpt-5.2) 或 Anthropic (claude-opus-4.6) |
| 性价比优先 | 智谱AI (glm-4-flash) 或 DeepSeek |
| 国内访问 | 智谱AI、阿里云、MiniMax |
| 长文本处理 | 阿里云 (qwen-long, 10M tokens) |

### Q2: 缓存会自动更新吗？

会。当以下情况发生时，缓存会自动失效并重新分析：
- package.json / go.mod 等版本文件变更
- 超过配置的 TTL 时间
- 手动触发刷新

### Q3: 支持私有部署的LLM吗？

支持。配置 `baseUrl` 指向你的私有API地址：

```yaml
llm:
  provider: openai
  apiKey: dummy
  baseUrl: http://localhost:8080/v1
  model: your-model
```

### Q4: 如何处理大批量文件变更？

| 变更文件数 | 处理策略 |
|-----------|---------|
| ≤ 5 | 逐文件详细review |
| 6-20 | 全部review，摘要呈现 |
| 21-50 | 重点review前10个变更最大的 |
| > 50 | 只review变更最大的20个 + 整体风险评估 |

### Q5: 如何贡献代码？

1. Fork 本仓库
2. 创建 feature 分支
3. 提交代码
4. 创建 Pull Request

---

## 配置示例

### TypeScript 项目

```yaml
llm:
  provider: openai
  apiKey: ${OPENAI_API_KEY}
  model: gpt-4o

criticalPaths:
  - src/auth
  - src/payment

excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
  - "src/__mocks__/**"

cache:
  ttl: 7d
```

### Python 项目

```yaml
llm:
  provider: deepseek
  apiKey: ${DEEPSEEK_API_KEY}
  model: deepseek-coder-v2

criticalPaths:
  - app/api/auth
  - app/models
  - migrations/

excludePatterns:
  - "tests/**"
  - "**/migrations/versions/**"
  - "venv/**"

cache:
  ttl: 14d
```

---

## 技术栈

- **框架**: LangChain
- **语言**: TypeScript
- **运行环境**: Node.js 18+, Docker

---

## License

MIT License - 欢迎开源贡献！

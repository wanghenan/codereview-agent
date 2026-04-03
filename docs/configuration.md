# 配置详解

完整的 `.codereview-agent.yaml` 配置说明。

---

## 完整配置示例

```yaml
# LLM 配置 (必需)
llm:
  provider: minimax        # openai | anthropic | zhipu | minimax | qwen | deepseek
  apiKey: ${LLM_API_KEY}   # 或直接填入 API Key
  model: abab6.5s-chat      # 模型名称 (可选)
  baseUrl: ""               # 自定义 API 地址 (可选)

# 关键路径 - 高风险区域，重点审查
criticalPaths:
  - src/auth
  - src/payment
  - src/admin
  - src/security

# 排除文件 - 不参与审查
excludePatterns:
  - "*.test.ts"
  - "*.spec.ts"
  - "vendor/**"
  - "node_modules/**"
  - "dist/**"
  - "build/**"

# 缓存配置
cache:
  ttl: 7                   # 项目上下文缓存天数 (默认 7)
  forceRefresh: false      # 是否强制刷新

# 输出配置
output:
  prComment: true         # 是否在 PR 上评论
  reportPath: .codereview-agent/output  # 报告保存路径
  reportFormat: markdown   # markdown | json
```

---

## LLM 配置

### provider

| 值 | 说明 |
|----|------|
| `openai` | OpenAI GPT 系列 |
| `anthropic` | Anthropic Claude 系列 |
| `zhipu` | 智谱 AI GLM 系列 |
| `minimax` | MiniMax 系列 |
| `qwen` | 阿里云通义千问 |
| `deepseek` | DeepSeek 系列 |

### model

各 Provider 推荐模型：

| Provider | 推荐模型 |
|----------|----------|
| OpenAI | gpt-4o, gpt-5, gpt-5.2 |
| Anthropic | claude-sonnet-4.6, claude-opus-4.6 |
| 智谱AI | glm-4-flash, glm-5 |
| MiniMax | MiniMax-M2.5, abab6.5s-chat |
| 阿里云 | qwen-plus, qwen3-max |
| DeepSeek | deepseek-chat, deepseek-v3 |

### baseUrl

自定义 API 地址，适用于：

- 代理服务器
- 自部署模型
- 企业内网

```yaml
llm:
  provider: openai
  apiKey: dummy
  baseUrl: http://localhost:8080/v1
  model: your-model
```

---

## 关键路径 (criticalPaths)

指定需要重点审查的目录。系统会对这些目录中的变更给予更高的风险权重。

```yaml
criticalPaths:
  - src/auth          # 认证相关
  - src/payment       # 支付相关
  - src/admin         # 管理后台
  - src/security      # 安全相关
```

---

## 排除规则 (excludePatterns)

使用 glob 模式排除不需要审查的文件：

```yaml
excludePatterns:
  # 测试文件
  - "*.test.ts"
  - "*.spec.ts"
  - "*_test.py"
  
  # 构建产物
  - "dist/**"
  - "build/**"
  - "*.min.js"
  
  # 依赖目录
  - "node_modules/**"
  - "vendor/**"
  - "__pycache__/**"
  
  # 生成文件
  - "*.pb.go"
  - "generated/**"
```

---

## 缓存配置

### cache.ttl

项目上下文缓存有效期（天）。首次运行会分析项目技术栈并缓存，之后运行直接使用缓存。

```yaml
cache:
  ttl: 7  # 默认 7 天
```

### cache.forceRefresh

是否强制刷新缓存：

```yaml
cache:
  forceRefresh: true  # 强制重新分析项目
```

---

## 自定义提示词 (customPromptPath)

### 简介

CodeReview Agent 支持使用自定义的 system prompt 来指导 AI 进行代码审查。这对于有特殊审查标准或需求的团队非常有用。

### 基本配置

```yaml
customPromptPath: ./prompts/review-prompt.txt
```

### 配置说明

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `customPromptPath` | 字符串 | 自定义 prompt 文件路径（绝对路径或相对于工作目录） |

### 支持的模板变量

在自定义 prompt 中可以使用以下变量，Agent 会自动替换：

| 变量 | 说明 |
|------|------|
| `{project_context}` | 项目上下文信息（技术栈、语言、关键路径等） |
| `{critical_paths}` | 关键路径列表 |
| `{exclude_patterns}` | 排除的文件模式 |
| `{static_results}` | 静态分析结果 |
| `{filename}` | 当前审查的文件名 |
| `{status}` | 文件状态（added/modified/deleted） |
| `{additions}` | 新增行数 |
| `{deletions}` | 删除行数 |
| `{patch}` | 代码差异内容 |

### 示例

创建一个 `prompts/review-prompt.txt` 文件：

```markdown
You are an expert {language} code reviewer specializing in security.

## Project Context
{project_context}

## Critical Paths (High Risk Areas)
{critical_paths}

## Your Task
Review the following code change and identify security issues:

### File: {filename}
Status: {status}
Changes: +{additions} -{deletions}

### Diff:
{patch}

Focus specifically on:
1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Authentication/authorization issues
4. Data exposure risks

Provide your analysis in JSON format.
```

### 使用默认 Prompt

如果不配置 `customPromptPath`，Agent 会使用内置的默认 prompt，适用于大多数场景。

### 注意事项

1. **路径支持**：支持绝对路径和相对路径（相对于运行命令的目录）
2. **编码**：文件必须为 UTF-8 编码
3. **变量完整性**：建议包含所有支持的变量，即使暂时不使用
4. **JSON 输出**：prompt 应要求 AI 输出 JSON 格式的结果，以便解析

---

## 输出配置

### output.prComment

是否在 PR 上发表评论：

```yaml
output:
  prComment: true  # 默认 true
```

设为 `false` 可仅生成报告：

```yaml
output:
  prComment: false
```

### output.reportPath

报告保存路径：

```yaml
output:
  reportPath: .codereview-agent/output
```

### output.reportFormat

报告格式：

```yaml
output:
  reportFormat: markdown  # 或 json
```

---

## 环境变量

### 必填

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | LLM API Key |

### 可选

| 变量 | 说明 |
|------|------|
| `LLM_BASE_URL` | 自定义 API 地址 |
| `GITHUB_TOKEN` | GitHub Token (PR 评论用) |

---

## CLI 覆盖配置

CLI 运行时可通过参数覆盖配置：

```bash
# 强制刷新缓存
python -m codereview.cli --branch main --refresh

# 指定输出路径
python -m codereview.cli --branch main --output /tmp/report

# 禁用缓存
python -m codereview.cli --branch main --no-cache

# JSON 输出
python -m codereview.cli --branch main --json
```

---

## 重试机制

### 自动重试

CodeReview Agent 内置智能重试机制，确保大规模 PR 也能完整审查：

- **重试次数**：每个文件最多重试 3 次
- **指数退避**：重试间隔为 1s、2s、4s（指数增长）
- **降级处理**：3 次重试都失败后，返回包含警告信息的降级结果，而非直接跳过

### 工作原理

```
文件审查失败
    ↓
重试 #1 (等待 1s)
    ↓
失败
    ↓
重试 #2 (等待 2s)
    ↓
失败
    ↓
重试 #3 (等待 4s)
    ↓
再次失败
    ↓
返回降级结果（带警告），继续处理其他文件
```

### 优势

1. **不遗漏**：即使部分文件失败，也不会中断整个 PR 的审查
2. **自动恢复**：临时网络抖动或 LLM 负载高时自动恢复
3. **完整报告**：最终报告包含所有文件的结果（含失败文件的警告）

### 常见失败原因

| 原因 | 解决方案 |
|------|----------|
| LLM 超时 | 网络问题，降低并发数或稍后重试 |
| Token 不足 | 检查 LLM API Key 配额 |
| 文件过大 | 考虑拆分为多个小 PR |

---

## 下一步

- ⚙️ [规则引擎](./rules.md) - 自定义检测规则
- 💾 [缓存机制](./cache.md) - 深入了解缓存
- ❓ [常见问题](./faq.md) - FAQ 解答

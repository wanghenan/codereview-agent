# CodeReview Agent 术语表 / Glossary

## 关键术语中英对照

| English | 中文 | 说明 |
|---------|------|------|
| Code Review | 代码审查 | 对代码变更进行检查和评审的过程 |
| Pull Request (PR) | 拉取请求 | 向主分支提交代码变更的请求 |
| Diff | 差异/变更 | 代码修改前后的差异 |
| Confidence Score | 置信度评分 | 0-100% 表示代码可提交的风险程度 |
| Risk Level | 风险等级 | 🔴高/🟡中/🟢低 |
| Vulnerability | 安全漏洞 | 可被利用的代码缺陷 |
| SQL Injection | SQL 注入 | 一种安全攻击手段 |
| Hardcoded Key | 硬编码密钥 | 直接写在代码中的密钥/密码 |
| LLM (Large Language Model) | 大语言模型 | 如 GPT、Claude 等 AI 模型 |
| Provider | 服务商 | LLM API 提供商 |
| LangChain | LangChain | AI 应用开发框架 |
| LangGraph | LangGraph | AI Agent 构建框架 |
| GitHub Action | GitHub Actions | GitHub 自动化工作流 |
| CLI (Command Line Interface) | 命令行工具 | 终端命令行界面 |
| Docker | Docker | 容器化平台 |
| Workflow | 工作流 | 自动化的流程配置 |
| Secret | 密钥/敏感信息 | 存储在 GitHub 的加密变量 |
| Repository/Repo | 仓库 | 代码存储库 |
| Merge | 合并 | 将代码合并到主分支 |

---

## 风险等级说明 / Risk Level Guide

| Level | Emoji | 置信度影响 |
|-------|-------|-----------|
| Critical | 🔴 | 直接标记为高风险，置信度 -100% |
| High | 🔴 | 高风险问题，建议人工审核 |
| Medium | 🟡 | 中等风险，可选择性修复 |
| Low | 🟢 | 低风险/代码风格建议 |

---

## 配置术语 / Config Terms

| English | 中文 | 用法 |
|---------|------|------|
| provider | 服务商 | `provider: openai` |
| apiKey | API 密钥 | 访问 LLM 的凭证 |
| model | 模型 | 使用的 AI 模型名称 |
| baseUrl | 基础 URL | 自定义 API 地址 |
| criticalPaths | 关键路径 | 需要重点审查的目录 |
| excludePatterns | 排除规则 | 忽略的文件/目录 |
| cache | 缓存 | 存储审查结果 |
| output | 输出 | 评论格式/报告位置 |

---

## 置信度计算 / Confidence Calculation

```
置信度 = 100 - Σ(问题严重程度权重)

权重:
- Critical: 100
- High: 75
- Medium: 50
- Low: 25
```

### 示例 / Examples

| 结论 | 置信度 | 说明 |
|------|--------|------|
| ✅ 可提交 / Ready to Merge | 50-100% | 无高风险问题 |
| ⚠️ 需人工审核 / Needs Human Review | 0-50% | 存在高风险问题 |

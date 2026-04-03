# 常见问题

关于 CodeReview Agent 的常见问题解答。

---

## 基础问题

### Q: CodeReview Agent 是免费的吗？

**A:** 工具本身免费，你只需要支付 LLM API 的调用费用。

每次 review 成本约：
- GPT-4o: $0.01-0.03
- Claude: $0.01-0.03
- 智谱 AI (免费版): $0
- DeepSeek: $0.001-0.005

### Q: 我的代码会泄露吗？

**A:** 不会。我们采用多重隐私保护：

1. **仅上传 diff** - 不上传完整源代码
2. **不经过第三方** - API 调用直接走你的账户
3. **本地处理** - Docker/CLI 模式完全本地运行

### Q: 支持哪些编程语言？

**A:** 目前支持：

| 语言 | 状态 | 说明 |
|------|------|------|
| Python | ✅ | 完整支持 |
| JavaScript/TypeScript | ✅ | 完整支持 |
| Go | ✅ | 完整支持 |
| Java | ✅ | 完整支持 |
| C/C++ | ✅ | 基础支持 |
| Rust | ✅ | 基础支持 |
| 其他 | 🔄 | 持续更新中 |

---

## 使用问题

### Q: 如何选择 LLM Provider？

| 场景 | 推荐 | 理由 |
|------|------|------|
| 代码质量优先 | OpenAI (gpt-4o) / Anthropic | 理解力最强 |
| 性价比优先 | 智谱AI (glm-4-flash) / DeepSeek | 免费/低价 |
| 国内访问 | MiniMax / 智谱AI / 阿里云 | 无需翻墙 |
| 安全敏感 | 自部署 + 开源模型 | 数据不出网 |

### Q: 置信度是怎么计算的？

**A:** 基于问题严重程度加权计算：

```
置信度 = 100 - Σ(问题严重程度权重)

权重:
- Critical: 100
- High: 75
- Medium: 50
- Low: 25
```

### Q: 可以自定义提示词吗？

**A:** 可以。参考 `custom-prompt.template` 文件：

```yaml
llm:
  customPrompt: ./custom-prompt.template
```

### Q: GitHub Action 触发失败怎么办？

**A:** 排查步骤：

1. 确认 `.codereview-agent.yaml` 存在且格式正确
2. 确认 secrets 已正确配置
3. 查看 Actions 日志排查
4. 尝试本地运行确认配置有效

---

## 配置问题

### Q: 如何禁用自动评论？

**A:** 在配置中设置：

```yaml
output:
  prComment: false
```

### Q: 支持私有部署的 LLM 吗？

**A:** 支持。配置 `baseUrl` 指向你的 API：

```yaml
llm:
  provider: openai
  apiKey: dummy
  baseUrl: http://localhost:8080/v1
  model: your-model
```

### Q: 如何排除特定文件？

**A:** 使用 `excludePatterns`：

```yaml
excludePatterns:
  - "*.test.ts"
  - "vendor/**"
  - "dist/**"
```

---

## 缓存问题

### Q: 缓存会自动更新吗？

**A:** 会。当以下情况会发生：
- package.json 等版本文件变更
- 超过 TTL (默认7天)
- 手动触发 `@codereview-agent refresh`

### Q: 缓存会泄露代码吗？

**A:** 不会。缓存仅保存：
- 项目元信息
- 审查结果摘要
- 不包含源代码

---

## 集成问题

### Q: 支持 GitLab 吗？

**A:** 目前支持 GitHub。GitLab 支持在规划中。

### Q: 可以集成到自有 CI 吗？

**A:** 可以。使用 CLI 模式：

```bash
python -m codereview.cli --diff diff.json --json > report.json
```

### Q: 支持 Webhook 吗？

**A:** 支持。通过 GitHub App 模式实现：

1. 安装 GitHub App
2. 配置 `.codereview-agent.yaml`
3. 创建 PR 自动触发

---

## 性能问题

### Q: 审查时间过长怎么办？

**A:** 优化建议：

1. **减少文件数** - 使用 `excludePatterns` 排除不重要的文件
2. **选择快速模型** - 使用 glm-4-flash 或 deepseek-chat
3. **启用缓存** - 避免重复分析
4. **限制变更范围** - 拆分大 PR

### Q: API 限流怎么办？

**A:** 处理方式：

1. 添加重试逻辑
2. 切换到其他 Provider
3. 降低请求频率

---

## 其他问题

### Q: 如何贡献代码？

**A:** 欢迎贡献！

1. Fork 仓库
2. 创建功能分支
3. 提交 PR
4. 等待 review

### Q: 如何报告问题？

**A:** 通过 GitHub Issues 报告：

https://github.com/wanghenan/codereview-agent/issues

---

## 下一步

- 🚀 [快速开始](./getting-started.md) - 快速上手
- ⚙️ [配置详解](./configuration.md) - 完整配置选项
- 🛠️ [故障排查](./troubleshooting.md) - 问题诊断

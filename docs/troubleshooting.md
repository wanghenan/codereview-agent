# 故障排查

常见问题诊断与解决方案。

---

## 快速诊断

遇到问题时，请按以下顺序检查：

1. ✅ 配置文件是否正确
2. ✅ API Key 是否有效
3. ✅ 网络是否正常
4. ✅ 查看日志输出

---

## GitHub Action 问题

### Action 触发但无评论

**症状**: PR 创建成功，但无 CodeReview 评论

**排查步骤**:

1. 检查 Workflow 是否正确触发
   ```yaml
   on:
     pull_request:
       types: [opened, synchronize, reopened]
   ```

2. 确认 `LLM_API_KEY` secrets 已配置
   - Settings → Secrets → Actions
   - 检查 key 名称是否匹配

3. 查看 Actions 日志
   - 点击失败的 Workflow run
   - 查看 Step 日志

### Action 运行失败

**常见错误**:

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `LLM_API_KEY` is not set | secrets 未配置 | 添加 secrets |
| Config file not found | 配置文件缺失 | 创建 .codereview-agent.yaml |
| Invalid provider | provider 错误 | 检查 provider 名称 |
| API rate limit | API 限流 | 切换 Provider 或等待 |

### 日志查看

```yaml
- name: Run CodeReview Agent
  uses: wanghenan/codereview-agent@v1
  with:
    config: .codereview-agent.yaml
  env:
    LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
  # 添加调试输出
  continue-on-error: true
```

---

## CLI 问题

### 模块未找到

**错误**:
```
ModuleNotFoundError: No module named 'codereview'
```

**解决方案**:

```bash
# 重新安装
cd codereview-agent/python
pip install -e .
```

### 配置文件加载失败

**错误**:
```
ConfigError: Invalid config
```

**排查**:

1. 检查 YAML 语法
2. 确认文件路径正确
3. 验证必填字段

### Git diff 获取失败

**错误**:
```
Failed to get git diff
```

**解决方案**:

```bash
# 确保在 git 仓库中
git status

# 确保有变更
git diff main...
```

---

## LLM API 问题

### API Key 无效

**错误**:
```
AuthenticationError: Invalid API key
```

**解决方案**:

1. 确认 API Key 正确
2. 检查 Key 是否过期
3. 确认 Key 有足够配额

### API 限流

**错误**:
```
RateLimitError: Rate limit exceeded
```

**解决方案**:

1. 等待一段时间后重试
2. 切换到其他 Provider
3. 升级 API 套餐

### 网络超时

**错误**:
```
TimeoutError: Request timeout
```

**解决方案**:

1. 检查网络连接
2. 使用国内 Provider (智谱AI / MiniMax)
3. 配置代理

---

## 缓存问题

### 缓存失效

**症状**: 每次运行都重新分析项目

**排查**:

```bash
# 检查缓存文件
ls -la .codereview-agent/cache/

# 查看缓存内容
cat .codereview-agent/cache/project-context.json
```

**解决方案**:

1. 检查版本文件是否变更
2. 确认 TTL 未过期
3. 手动删除缓存后重试

### 缓存权限问题

**错误**:
```
PermissionError: [Errno 13] Permission denied
```

**解决方案**:

```bash
# 修复权限
chmod -R 755 .codereview-agent/
```

---

## 规则引擎问题

### 规则未加载

**症状**: 自定义规则不生效

**排查**:

```bash
# 启用调试日志
LOG_LEVEL=debug python -m codereview.cli --branch main 2>&1 | grep -i rule
```

**解决方案**:

1. 确认规则文件格式正确
2. 检查规则文件路径
3. 验证正则表达式语法

### 正则匹配错误

**错误**:
```
RegexError: invalid regex pattern
```

**解决方案**: 检查正则表达式语法，确保转义正确。

---

## 输出问题

### PR 评论失败

**症状**: 审查完成但评论未发布

**排查**:

1. 检查 Token 权限
2. 确认 Workflow 有 `pull-requests: write` 权限

```yaml
permissions:
  contents: read
  pull-requests: write
```

### 报告未生成

**症状**: 未生成报告文件

**排查**:

```yaml
output:
  reportPath: .codereview-agent/output
  prComment: false  # 设为 false 只生成报告
```

---

## 性能问题

### 运行缓慢

**优化建议**:

1. **减少审查文件数**
   ```yaml
   excludePatterns:
     - "vendor/**"
     - "node_modules/**"
   ```

2. **使用快速模型**
   ```yaml
   llm:
     provider: zhipu
     model: glm-4-flash
   ```

3. **启用缓存**
   ```yaml
   cache:
     ttl: 7
   ```

4. **限制关键路径**
   ```yaml
   criticalPaths:
     - src/auth
     - src/payment
   ```

---

## 获取帮助

### 调试模式

```bash
# 启用完整调试日志
LOG_LEVEL=debug python -m codereview.cli --branch main 2>&1 | tee debug.log
```

### 报告问题

如无法解决，请通过以下方式获取帮助：

1. **GitHub Issues**: https://github.com/wanghenan/codereview-agent/issues
2. **Discord**: https://discord.gg/codereview-agent

### 提供信息

报告问题时，请提供：

- 错误信息全文
- 配置文件 (隐藏 API Key)
- 相关日志
- 环境信息 (`python --version`, `git --version`)

---

## 下一步

- 🚀 [快速开始](./getting-started.md) - 快速上手
- ⚙️ [配置详解](./configuration.md) - 完整配置选项
- ❓ [常见问题](./faq.md) - FAQ 解答

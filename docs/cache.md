# 缓存机制

CodeReview Agent 使用两层缓存策略，兼顾性能与准确性。

---

## 缓存类型

### 1. 项目上下文缓存

首次运行时分析项目技术栈、目录结构、依赖信息，后续运行直接使用缓存。

**缓存位置**: `.codereview-agent/cache/project-context.json`

**缓存内容**:
- 项目类型 (Python, Node.js, Go 等)
- 依赖列表
- 代码风格配置
- 目录结构摘要

### 2. 文件级审查缓存

记录每个文件的审查结果，实现增量审查。

**缓存位置**: `.codereview-agent/cache/file_reviews/`

---

## 缓存策略

### TTL (Time To Live)

```yaml
cache:
  ttl: 7  # 默认 7 天
```

### 版本号检测

当以下文件变更时，自动失效缓存：

| 文件 | 项目类型 |
|------|----------|
| `package.json` | Node.js |
| `pyproject.toml` | Python |
| `go.mod` | Go |
| `pom.xml` | Java |
| `Cargo.toml` | Rust |

### 手动刷新

```bash
# CLI 刷新
python -m codereview.cli --branch main --refresh

# PR 中触发
@codereview-agent refresh
```

---

## 缓存配置

### 完整配置

```yaml
cache:
  ttl: 7              # 项目上下文缓存天数
  forceRefresh: false # 是否强制刷新
```

### CLI 参数

| 参数 | 说明 |
|------|------|
| `--refresh` | 强制刷新项目缓存 |
| `--no-cache` | 禁用文件级缓存 |

---

## Patch 规范化

文件级缓存使用 **语义化 Patch 规范化** 技术，即使代码格式变化也能命中缓存。

### 工作原理

```python
# 原始 diff patch（格式化前）
+    console.log('hello')
-    console.log('world')

# 格式化后 diff patch
+console.log('hello')
-console.log('world')

# 规范化后（相同）
+console.log('hello')
-console.log('world')
```

### 优化效果

| 情况 | 优化前 | 优化后 |
|------|--------|--------|
| 相同逻辑，不同格式 | 缓存失效 | ✅ 缓存命中 |
| whitespace 变化 | 缓存失效 | ✅ 缓存命中 |
| 完全不同的修改 | 缓存失效 | 缓存失效 |

### 节省成本

- 相同代码逻辑的 PR（仅格式化变化）不会重复消耗 LLM token
- 节省约 20-30% 的 LLM 调用成本

---

## 缓存管理

### 查看缓存状态

```bash
# 查看缓存信息
python -m codereview.cli --branch main --json 2>&1 | grep cache
```

输出示例：

```json
{
  "cache_info": {
    "used_cache": true,
    "cache_timestamp": "2024-01-15T10:30:00",
    "cache_version": "1.0.0"
  }
}
```

### 清除缓存

```bash
# 手动删除缓存目录
rm -rf .codereview-agent/cache/
```

---

## 缓存工作流程

```
首次运行 (无缓存)
     │
     ▼
┌──────────────────┐
│ 分析项目技术栈   │ → 生成 project-context.json
└──────────────────┘
     │
     ▼
┌──────────────────┐
│ 逐文件审查        │ → 生成 file_reviews/*.json
└──────────────────┘
     │
     ▼
    完成

后续运行 (有缓存)
     │
     ▼
┌──────────────────┐
│ 检查缓存有效性   │
│ - TTL 未过期     │
│ - 版本号未变更   │
└──────────────────┘
     │
     ├─ 有效 → 直接使用缓存
     │
     └─ 无效 → 重新分析项目
```

---

## 性能对比

| 场景 | 首次运行 | 缓存命中 |
|------|----------|----------|
| 项目分析 | ~10s | ~0.1s |
| 文件审查 | ~2s/文件 | ~0.5s/文件 |
| 总体 (10 文件) | ~30s | ~6s |

---

## 缓存与置信度

缓存中的分析结果会标注时间戳，帮助你判断上下文新鲜度：

```markdown
## CodeReview Agent 🤖

**结论**: ✅ 可提交 (置信度: 88%)

> 📅 项目上下文缓存时间: 2024-01-15 10:30:00 (2 小时前)
```

---

## 常见问题

### Q: 缓存会泄露代码吗？

**不会。** 缓存仅保存：
- 项目元信息（类型、依赖）
- 审查结果摘要
- 不包含源代码

### Q: 缓存可以共享吗？

**可以。** 缓存文件可提交到仓库，团队共享同一份缓存：

```bash
# 提交缓存
git add .codereview-agent/cache/
git commit -m "chore: add codereview cache"
```

### Q: 如何禁用缓存？

```bash
python -m codereview.cli --branch main --no-cache
```

或配置：

```yaml
cache:
  ttl: 0  # 禁用缓存
```

---

## 下一步

- ⚙️ [配置详解](./configuration.md) - 完整配置选项
- ⚙️ [规则引擎](./rules.md) - 自定义检测规则
- ❓ [常见问题](./faq.md) - FAQ 解答

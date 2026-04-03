# CodeReview Agent 文档

🤖 AI 驱动的 CodeReview 智能体 — 让代码审查更智能、更高效

---

## 🚀 核心功能一览

### 🔍 智能代码审查
自动分析代码变更，识别安全漏洞、性能问题、代码异味，并给出置信度评分。

```bash
python -m codereview.cli review --pr 123
```

**[快速开始 →](./getting-started.md)**

---

### 🔧 自动修复问题
发现代码问题？直接让 AI 生成修复代码并一键应用！

```bash
# 预览修复
python -m codereview.cli fix --pr 123

# 应用修复
python -m codereview.cli fix --pr 123 --apply
```

**[智能修复详解 →](./fix-command.md)**

---

### 🔄 自动合并 PR
审查通过后自动合并，支持条件检查（置信度、审批、CI状态）。

```bash
# Review + Merge 预览
python -m codereview.cli review --pr 123 --auto-merge
```

**[自动合并详解 →](./auto-merge.md)**

---

### 📊 置信度评分
每条审查结果都有 0-100% 的置信度评分，让团队对代码质量有量化认知。

**[配置详解 →](./configuration.md)**

---

## 📚 文档目录

### 🚀 快速入门
| 文档 | 描述 |
|------|------|
| [快速开始](./getting-started.md) | 5 分钟快速上手，三种使用方式 |
| [配置详解](./configuration.md) | 完整配置项说明 |

### 🔍 核心功能
| 文档 | 描述 |
|------|------|
| [智能修复](./fix-command.md) | 自动修复代码问题 |
| [自动合并](./auto-merge.md) | Review 后自动合并 PR |
| [规则引擎](./rules.md) | 自定义检测规则 |

### 💾 高级特性
| 文档 | 描述 |
|------|------|
| [缓存机制](./cache.md) | 项目缓存和增量审查 |
| [使用案例](./USE_CASES.md) | 常见使用场景 |

### ❓ 帮助
| 文档 | 描述 |
|------|------|
| [常见问题](./faq.md) | FAQ 解答 |
| [故障排查](./troubleshooting.md) | 问题诊断与解决 |

### 📖 参考
| 文档 | 描述 |
|------|------|
| [USER_GUIDE](./USER_GUIDE.md) | 完整使用指南 |
| [DESIGN](./DESIGN.md) | 架构设计方案 |
| [GLOSSARY](./GLOSSARY.md) | 术语表 |

---

## ⚡ 快速导航

### 使用方式
```bash
# 1. GitHub Action (推荐)
- uses: wanghenan/codereview-agent@v1

# 2. Docker
docker run wanghenan/codereview-agent --pr 123

# 3. CLI
python -m codereview.cli --diff diff.json
```

### 典型工作流

```
PR 创建 → CodeReview → [发现问题] → Fix 修复 → 再次 Review → Auto-Merge
```

---

## 🔗 相关链接

- [GitHub 仓库](https://github.com/wanghenan/codereview-agent)
- [更新日志](https://github.com/wanghenan/codereview-agent/releases)
- [问题反馈](https://github.com/wanghenan/codereview-agent/issues)

# CodeReview Agent 文档

🤖 AI 驱动的 CodeReview 智能体

---

## 📚 文档目录

### 🚀 快速入门
| 文档 | 描述 |
|------|------|
| [快速开始](./getting-started.md) | 5 分钟快速上手，三种使用方式 |
| [配置详解](./configuration.md) | 完整配置项说明 |

### ⚙️ 高级功能
| 文档 | 描述 |
|------|------|
| [智能修复](./fix-command.md) | 自动修复代码问题 |
| [自动合并](./auto-merge.md) | Review 后自动合并 PR |
| [规则引擎](./rules.md) | 自定义检测规则 |
| [缓存机制](./cache.md) | 项目缓存和增量审查 |

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

### 核心功能
- 🔍 智能风险识别
- 📊 置信度评分 (0-100%)
- 🌐 6 大 LLM Provider
- 🔒 代码隐私保护
- 💾 智能缓存

---

## 🔗 相关链接

- [GitHub 仓库](https://github.com/wanghenan/codereview-agent)
- [更新日志](https://github.com/wanghenan/codereview-agent/releases)
- [问题反馈](https://github.com/wanghenan/codereview-agent/issues)

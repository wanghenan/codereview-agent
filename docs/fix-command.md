# Fix 命令 - 智能修复代码问题

CodeReview Agent 不仅能发现问题，还能自动修复代码问题！

---

## 🚀 快速开始

```bash
# 预览修复（不实际修改文件）
python -m codereview.cli fix --pr 123

# 确认无误后，应用修复
python -m codereview.cli fix --pr 123 --apply
```

---

## 📖 使用方式

### 方式一：从 GitHub PR 获取代码并修复

```bash
# 预览修复建议
python -m codereview.cli fix --pr 123

# 应用所有修复
python -m codereview.cli fix --pr 123 --apply

# 指定 GitHub Token
python -m codereview.cli fix --pr 123 --token ghp_xxxx
```

### 方式二：从本地 diff 文件修复

```bash
# 从 diff.json 预览修复
python -m codereview.cli fix --diff diff.json

# 应用修复
python -m codereview.cli fix --diff diff.json --apply
```

### 方式三：从分支对比修复

```bash
# 获取 main 分支的 diff 并预览修复
python -m codereview.cli fix --diff "$(git diff main...)"
```

---

## 🎯 过滤选项

### 仅修复特定文件

```bash
# 只修复 src/main.py
python -m codereview.cli fix --pr 123 --file "src/main.py"

# 修复 src/ 下的所有文件
python -m codereview.cli fix --pr 123 --file "src/*"
```

### 按风险级别过滤

```bash
# 只修复高风险问题（默认）
python -m codereview.cli fix --pr 123 --min-risk high

# 修复高风险和中风险问题
python -m codereview.cli fix --pr 123 --min-risk medium

# 修复所有问题
python -m codereview.cli fix --pr 123 --min-risk low
```

---

## 📊 输出示例

```
============================================================
  CodeReview Agent Fix 🔍 DRY RUN
============================================================

📊 Risk Summary:
   🔴 High: 2
   🟡 Medium: 1
   🟢 Low: 2
   Total: 5 fixes

   💡 Run with --apply to apply these fixes

============================================================
  📄 Files Summary (2 files)
============================================================

  📄 src/auth.py (3 fixes)
     🔴 #1:42 - SQL injection vulnerability in raw query...
     🔴 #2:58 - Hardcoded password found in source code...
     🟡 #3:101 - Unused import statement detected...

  📄 src/utils.py (2 fixes)
     🟢 #4:15 - Variable naming convention violation...
     🟢 #5:28 - Missing docstring for public method...

============================================================
  🔍 Diff Preview
============================================================

🔧 #1 | src/auth.py:42 | HIGH
   Issue: Potential SQL injection vulnerability in raw query

   --- Original
   -  cursor.execute(f"SELECT * FROM users WHERE name = '{username}'")
   +  cursor.execute("SELECT * FROM users WHERE name = %s", (username,))

   💡 Use parameterized query instead of string interpolation
```

---

## 🔧 工作流程

```
┌─────────────────────────────────────────────────────────┐
│                    Fix 工作流程                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   1️⃣  获取代码差异                                        │
│       PR / Diff 文件 / Git 分支                          │
│              ↓                                          │
│   2️⃣  运行 Code Review                                   │
│       分析问题并生成 Issue 列表                           │
│              ↓                                          │
│   3️⃣  生成修复建议                                        │
│       AI 分析每个问题，生成修复代码                        │
│              ↓                                          │
│   4️⃣  预览修复 Diff                                      │
│       显示 unified diff 格式                             │
│              ↓                                          │
│   5️⃣  用户确认 (--dry-run 或 --apply)                     │
│       dry-run: 只展示，不修改                            │
│       apply:   写入文件                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 CLI 参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--config` | `-c` | 配置文件路径 | `.codereview-agent.yaml` |
| `--pr` | `-p` | PR 编号（从 GitHub 获取 diff） | - |
| `--diff` | `-d` | diff 数据或文件路径 | - |
| `--token` | `-t` | GitHub Token（或设置 `GITHUB_TOKEN` 环境变量） | - |
| `--apply` | | 应用修复到文件 | `False`（默认 dry-run） |
| `--dry-run` | | 仅预览，不应用 | `True` |
| `--file` | `-f` | 文件过滤模式（glob） | 全部文件 |
| `--min-risk` | | 最小风险级别 | `high` |
| `--json` | | 输出 JSON 格式 | `False` |
| `--output` | `-o` | 保存预览到文件 | - |

---

## ⚙️ 配合 Review 命令使用

```bash
# 1. 先 review
python -m codereview.cli review --pr 123

# 2. 根据 review 结果决定是否 fix
python -m codereview.cli fix --pr 123 --min-risk high

# 3. 如果满意，应用修复
python -m codereview.cli fix --pr 123 --min-risk high --apply
```

---

## 🔒 安全建议

1. **先用 dry-run 模式**：预览所有修复，确认无误后再应用
2. **版本控制**：修复前确保代码已提交到 git
3. **逐步应用**：先用 `--min-risk high` 修复高风险问题，确认无误后再处理中低风险
4. **备份**：重要项目建议先备份或创建修复分支

```bash
# 推荐流程
git checkout -b fix/my-changes
python -m codereview.cli fix --pr 123 --min-risk high --apply
git diff  # 检查修改
git commit -m "Apply code review fixes"
```

---

## 🐛 故障排查

### "No issues found matching the criteria"

可能原因：
- 文件没有检测到问题
- 风险级别过滤条件太严格

解决方案：
```bash
# 降低风险级别
python -m codereview.cli fix --pr 123 --min-risk low
```

### "Could not read file"

可能原因：
- 文件路径不存在
- 文件编码问题

解决方案：
```bash
# 检查文件是否存在
ls -la src/main.py

# 如果是编码问题，手动指定编码（未来版本支持）
```

### "Failed to apply fix"

可能原因：
- 源文件已被修改
- 修复代码有语法错误

解决方案：
- 修复是增量应用的，失败的修复不会影响其他文件的修复
- 重新运行 `review` 和 `fix`

---

## 📦 修复类型

Fixer 支持自动修复以下类型的问题：

| 类型 | 描述 | 示例 |
|------|------|------|
| `security` | 安全漏洞 | SQL注入、XSS、硬编码密码 |
| `performance` | 性能优化 | N+1查询、内存泄漏 |
| `bug_fix` | Bug修复 | 空指针、边界条件 |
| `best_practice` | 最佳实践 | 异常处理、资源释放 |
| `code_style` | 代码风格 | 命名规范、未使用变量 |

---

## 🔄 与其他命令的关系

```
review ──────────────────────────────────┐
   │                                      │
   │  (发现问题)                           │
   ▼                                      │
fix ─────────────────────────────────────► merge
   │                                      │
   │  (修复代码)                           │
   ▼                                      │
commit                                   │
   │                                      │
   └────────── (准备合并) ─────────────────┘
```

- `review`：发现问题
- `fix`：修复问题
- `merge`：合并代码

---

## 下一步

- 📖 [配置详解](./configuration.md) - 修复相关配置
- ⚙️ [规则引擎](./rules.md) - 自定义检测规则
- 🔧 [故障排查](./troubleshooting.md) - 问题诊断

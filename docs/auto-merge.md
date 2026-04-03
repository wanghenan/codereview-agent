# Auto-Merge - 自动合并 PR

CodeReview Agent 支持在代码审查通过后自动合并 PR！

---

## 🚀 快速开始

```bash
# 预览 review + merge 条件
python -m codereview.cli review --pr 123 --auto-merge

# 应用 review 并合并（如果满足条件）
python -m codereview.cli review --pr 123 --auto-merge --apply-auto-merge
```

---

## 📖 工作原理

```
┌─────────────────────────────────────────────────────────┐
│                  Review + Auto-Merge 流程               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   1️⃣  获取 PR Diff                                       │
│       从 GitHub 获取 PR 的代码差异                        │
│              ↓                                          │
│   2️⃣  运行 Code Review                                   │
│       AI 分析代码问题，计算置信度                          │
│              ↓                                          │
│   3️⃣  检查合并条件                                        │
│       - 置信度 >= 阈值（默认 90%）                        │
│       - 无高风险文件                                      │
│       - 已满足审批要求                                    │
│       - CI 检查全部通过                                   │
│              ↓                                          │
│   4️⃣  满足条件？                                         │
│       ├── 是 → 自动合并 PR                                │
│       └── 否 → 输出预览，告知不满足的原因                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## ⚙️ 配置

### 配置文件 `.codereview-agent.yaml`

```yaml
llm:
  provider: minimax
  apiKey: your-api-key-here
  model: abab6.5s-chat

output:
  # Auto-Merge 配置
  autoMerge:
    enabled: true
    # 合并条件
    conditions:
      minConfidence: 90      # 最低置信度 0-100%
      maxSeverity: low        # 最高允许风险级别
      requireApproval: true   # 是否需要至少一个审批
    # 合并方式
    mergeMethod: squash       # squash, merge, rebase
    # 文件过滤（可选）
    filePatterns:
      - "src/**/*.py"
      - "lib/**/*.js"
```

### 合并条件说明

| 条件 | 说明 | 默认值 |
|------|------|--------|
| `minConfidence` | 审查置信度必须达到的最低百分比 | 90% |
| `maxSeverity` | 允许的最高风险级别 | `low` |
| `requireApproval` | 是否需要至少一个审批 | `true` |

### 风险级别说明

- `high`：安全漏洞、硬编码密码、认证问题、破坏性变更
- `medium`：代码异味、潜在 bug、可维护性问题
- `low`：样式问题、轻微改进

---

## 📝 使用示例

### 1. 预览合并条件

```bash
python -m codereview.cli review --pr 123 --auto-merge

# 输出示例：
#
# ========================================================
#   CodeReview Agent Report
# ========================================================
#
# **Conclusion**: ⚠️ **Needs Review** (Confidence: 78%)
#
# ========================================================
#   Auto-Merge Preview
# ========================================================
#
# ❌ Can Merge: False
# Reason: Confidence 78% is below threshold 90%
#
# 📊 Review Confidence: 78%
#    Required: 90%
#
# 👥 Approvals: 2
#
# 📁 Files (3):
#   🟢 src/auth.py (1 issues)
#   🟡 src/utils.py (3 issues)
#   🔴 src/security.py (2 issues)
```

### 2. 强制执行合并（不推荐）

```bash
# 即使不满足条件也强制合并
python -m codereview.cli review --pr 123 --auto-merge --force
```

### 3. 使用不同的 token

```bash
python -m codereview.cli review --pr 123 --auto-merge --token ghp_xxxx
```

---

## 🔍 合并条件检查

Auto-Merger 会检查以下条件：

### 必须满足的条件

1. **置信度检查**
   ```
   result.confidence >= conditions.minConfidence
   ```

2. **风险级别检查**
   ```
   所有文件的 risk_level <= conditions.maxSeverity
   ```

3. **审批检查**（如果 `requireApproval: true`）
   ```
   approval_count >= 1
   ```

4. **CI 检查**（如果有 check runs）
   ```
   所有 check runs 状态为 success 或 completed
   ```

### 不满足条件时的输出

```
❌ Can Merge: False
Reason: File src/security.py has high risk, exceeds max low

📊 Review Confidence: 85%
   Required: 90%

👥 Approvals: 0 (Required: 1)

📁 Files (5):
  🔴 src/security.py (5 issues)
  🟡 src/auth.py (2 issues)
  🟢 src/utils.py (0 issues)
  ...
```

---

## 🎛️ 高级用法

### 只对特定文件进行合并检查

```yaml
output:
  autoMerge:
    enabled: true
    filePatterns:
      - "src/**/*.py"      # 只检查 src 目录下的 Python 文件
      - "lib/**/*.js"       # 和 lib 目录下的 JS 文件
```

### 使用 merge 子命令（替代方案）

你也可以单独使用 `merge` 命令：

```bash
# 只运行 review
python -m codereview.cli review --pr 123

# 单独运行 merge（预览模式）
python -m codereview.cli merge --pr 123 --dry-run

# 确认后合并
python -m codereview.cli merge --pr 123

# 强制合并（跳过条件检查）
python -m codereview.cli merge --pr 123 --force
```

---

## ⚠️ 安全建议

1. **始终使用 `--dry-run` 先预览**
   ```bash
   python -m codereview.cli review --pr 123 --auto-merge
   ```

2. **确保 CI 检查通过**
   - Auto-Merger 会检查 CI 状态
   - 如果 CI 失败，不会合并

3. **保留合并历史**
   - squash 合并会保留 PR 中的所有 commit message
   - 建议在 PR 描述中清晰说明变更内容

4. **设置合理的阈值**
   - 初次使用建议 `minConfidence: 95`
   - 团队熟悉后可适当降低

5. **`--force` 慎用**
   - `--force` 会跳过所有条件检查（置信度、审批、CI）
   - 仅在你确定代码安全、只是未满足配置条件时使用
   - 例如：本地测试 PR、紧急修复、已人工 review 过的代码

---

## 🔧 故障排查

### "Auto merge is not enabled in config"

**原因**：配置文件中未启用 auto-merge

**解决**：在 `.codereview-agent.yaml` 中设置：
```yaml
output:
  autoMerge:
    enabled: true
```

### "Confidence X% is below threshold Y%"

**原因**：审查置信度未达到阈值

**解决**：
- 降低阈值（不推荐）
- 修复代码问题后重试
- 使用 `--force` 强制合并（不推荐）

### "PR requires at least 1 approval (got 0)"

**原因**：PR 没有审批

**解决**：
- 让团队成员审批 PR
- 在配置中设置 `requireApproval: false`

### "CI checks failed"

**原因**：CI 检查未全部通过

**解决**：
- 修复失败的 CI 检查
- 检查 CI 配置是否正确

---

## 📊 与其他命令的关系

```
review --auto-merge
       │
       ├── review 结果
       │      └─── 输出到 PR comment / 报告文件
       │
       └── merge 检查
              │
              ├── 条件满足 → 自动合并
              │
              └── 条件不满足 → 输出预览
```

---

## 下一步

- 📖 [配置详解](./configuration.md) - 完整配置选项
- 🔧 [智能修复](./fix-command.md) - 修复代码问题
- ⚙️ [规则引擎](./rules.md) - 自定义检测规则

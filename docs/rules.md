# 规则引擎

CodeReview Agent 内置风险检测规则引擎，支持自定义规则。

---

## 概述

规则引擎提供两层检测：

1. **AI 分析** - LLM 智能理解代码上下文
2. **规则匹配** - 基于正则表达式的模式检测

两者结合，提供更准确的风险识别。

---

## 内置规则

内置规则位于 `python/src/codereview/rules/` 目录：

| 规则 ID | 名称 | 严重程度 | 说明 |
|---------|------|----------|------|
| `SEC001` | 硬编码密钥 | HIGH | 检测硬编码的 API Key、密码 |
| `SEC002` | SQL 注入 | HIGH | 检测 SQL 拼接风险 |
| `SEC003` | 命令注入 | HIGH | 检测命令执行风险 |
| `SEC004` | XSS 漏洞 | HIGH | 检测跨站脚本风险 |
| `SEC005` | 敏感信息泄露 | HIGH | 检测日志/注释中的敏感信息 |
| `BEST001` | 空 Catch 块 | MEDIUM | 检测空异常处理 |
| `BEST002` | 魔法数字 | MEDIUM | 检测未命名的常量 |
| `BEST003` | 废弃 API | MEDIUM | 检测已废弃的 API 调用 |
| `STYLE001` | 命名规范 | LOW | 检测命名风格问题 |
| `STYLE002` | 代码格式 | LOW | 检测格式问题 |

---

## 自定义规则

### 创建规则文件

在项目根目录创建 `rules/` 目录，添加规则文件：

```yaml
# rules/custom.yaml
rules:
  - id: MY001
    name: 自定义安全规则
    pattern: "password\\s*=\\s*['\"](?!.*\\$\\{).+['\"]"
    severity: high
    description: 检测硬编码密码
    suggestion: 使用环境变量或配置中心

language_rules:
  python:
    - id: PY001
      name: TODO 注释
      pattern: "#\\s*TODO:"
      severity: low
      description: 检测未完成的 TODO
      suggestion: 完成或创建 Issue 跟踪
```

### 规则格式

#### YAML 格式

```yaml
rules:
  - id: RULE_ID          # 规则唯一标识
    name: 规则名称        # 人类可读名称
    pattern: 正则表达式   # 检测模式
    severity: high       # high | medium | low
    description: 描述    # 问题描述
    suggestion: 建议     # 修复建议
```

#### JSON 格式

```json
{
  "rules": [
    {
      "id": "RULE001",
      "name": "规则名称",
      "pattern": "正则表达式",
      "severity": "high",
      "description": "描述",
      "suggestion": "建议"
    }
  ]
}
```

---

## 语言特定规则

针对特定编程语言的规则：

```yaml
language_rules:
  python:
    - id: PY001
      name: TODO 注释
      pattern: "#\\s*TODO:"
      severity: low
      description: 检测未完成的 TODO
      suggestion: 完成或创建 Issue 跟踪
  
  javascript:
    - id: JS001
      name: Console 日志
      pattern: "console\\.(log|debug|info)"
      severity: low
      description: 检测遗留的 console 日志
      suggestion: 生产环境移除调试日志
  
  go:
    - id: GO001
      name: 错误未处理
      pattern: "_\\s*:=.*err"
      severity: medium
      description: 检测忽略的错误
      suggestion: 处理或记录错误
```

---

## 使用自定义规则

### CLI 指定规则目录

```bash
python -m codereview.cli --branch main --rules-dir ./rules
```

### 配置中指定

```yaml
rules:
  dir: ./rules  # 自定义规则目录
```

---

## 规则匹配原理

### 检测流程

```
代码变更 (diff)
     │
     ▼
┌─────────────┐
│ 提取新增行  │  只检测新增/修改的行
└─────────────┘
     │
     ▼
┌─────────────┐
│ 规则匹配    │  逐规则执行正则匹配
└─────────────┘
     │
     ▼
┌─────────────┐
│ 结果聚合    │  合并 AI 分析 + 规则检测
└─────────────┘
     │
     ▼
   输出结果
```

### 匹配示例

对于以下代码变更：

```diff
+ password = "mysecret123"
```

规则 `SEC001` 会匹配到 `password = "mysecret123"`，输出：

```json
{
  "rule_id": "SEC001",
  "rule_name": "硬编码密钥",
  "line_number": 1,
  "matched_text": "password = \"mysecret123\"",
  "severity": "high",
  "description": "检测硬编码的密码",
  "suggestion": "使用环境变量"
}
```

---

## 规则优先级

规则检测结果与 AI 分析结果会合并：

1. **规则匹配** - 快速识别已知模式
2. **AI 分析** - 理解上下文，发现复杂问题
3. **结果合并** - 去重，保留最严重级别

---

## 调试规则

### 查看加载的规则

```bash
# 启用调试日志
LOG_LEVEL=debug python -m codereview.cli --branch main 2>&1 | grep -i rule
```

### 测试规则匹配

```python
from codereview.rules import create_rule_engine

engine = create_rule_engine(rules_dir="./rules")
rule = engine.get_rule_by_id("SEC001")

# 测试匹配
content = '''
def login():
    password = "admin123"
'''
matches = rule.match(content)
print(matches)
```

---

## 最佳实践

1. **规则数量** - 建议 10-50 条，避免过多影响性能
2. **正则性能** - 避免过于复杂的正则表达式
3. **定期更新** - 随着项目演进，及时更新规则
4. **分层管理** - 按类型/语言拆分规则文件

---

## 下一步

- 📖 [配置详解](./configuration.md) - 完整配置选项
- 💾 [缓存机制](./cache.md) - 缓存策略
- ❓ [常见问题](./faq.md) - FAQ 解答

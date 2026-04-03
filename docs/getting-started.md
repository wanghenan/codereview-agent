# 快速开始

CodeReview Agent 支持三种使用方式，选择最适合你的方式。

---

## 方式一：GitHub Action (推荐)

适合 CI/CD 自动化，每次 PR 自动触发 CodeReview。

### 步骤 1: 创建 Workflow 文件

在项目根目录创建 `.github/workflows/codereview.yml`:

```yaml
name: CodeReview Agent

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  codereview:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run CodeReview Agent
        uses: wanghenan/codereview-agent@v1
        with:
          config: .codereview-agent.yaml
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

### 步骤 2: 创建配置文件

创建 `.codereview-agent.yaml`:

```yaml
llm:
  provider: minimax  # 或: openai, anthropic, zhipu, qwen, deepseek
  apiKey: ${{ secrets.LLM_API_KEY }}
  model: abab6.5s-chat
```

### 步骤 3: 添加 GitHub Secrets

1. 进入仓库 Settings → Secrets and variables → Actions
2. 添加新 secret: `LLM_API_KEY`
3. 填入你的 LLM API Key

### 步骤 4: 创建 PR

创建或更新 PR → 自动触发 CodeReview！🎉

---

## 方式二：Docker

适合本地测试或自托管环境。

### 快速运行

```bash
docker run -v $(pwd):/app \
  -e LLM_API_KEY=your-key \
  wanghenan/codereview-agent --pr 123
```

### 完整示例

```bash
# 1. 克隆项目
git clone https://github.com/wanghenan/codereview-agent.git

# 2. 构建镜像
cd codereview-agent
docker build -t codereview-agent .

# 3. 运行 (指定 PR)
docker run -v $(pwd):/app \
  -e LLM_API_KEY=$LLM_API_KEY \
  codereview-agent --pr 123

# 4. 运行 (指定分支对比)
docker run -v $(pwd):/app \
  -e LLM_API_KEY=$LLM_API_KEY \
  codereview-agent --branch main
```

### Docker Compose

```yaml
version: '3.8'
services:
  codereview:
    image: wanghenan/codereview-agent
    volumes:
      - .:/app
    environment:
      - LLM_API_KEY=${LLM_API_KEY}
    command: --branch main
```

---

## 方式三：本地 CLI

适合本地开发调试，或集成到自有 CI 系统。

### 安装

```bash
# 克隆项目
git clone https://github.com/wanghenan/codereview-agent.git
cd codereview-agent/python

# 使用 uv 安装 (推荐)
uv venv && source .venv/bin/activate
pip install -e .

# 或使用 pip
pip install -e .
```

### 配置

在项目根目录创建 `.codereview-agent.yaml`:

```yaml
llm:
  provider: minimax
  apiKey: your-api-key-here
  model: abab6.5s-chat
```

### 运行

```bash
# 方式 1: 使用 git diff
python -m codereview.cli --branch main

# 方式 2: 指定 diff 文件
python -m codereview.cli --diff diff.json

# 方式 3: PR 编号 (需要 GitHub Token)
python -m codereview.cli --pr 123

# 方式 4: 修复 PR 中的问题
python -m codereview.cli fix --pr 123
```

### CLI 参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--config` | `-c` | 配置文件路径 |
| `--diff` | `-d` | diff 数据或文件路径 |
| `--pr` | `-p` | PR 编号 |
| `--branch` | `-b` | 对比的分支名 |
| `--refresh` | `-r` | 强制刷新缓存 |
| `--output` | `-o` | 报告输出路径 |
| `--json` | | 输出 JSON 格式 |
| `--no-cache` | | 禁用文件级缓存 |

### Review 子命令

```bash
# 完整参数列表
python -m codereview.cli review --help

# 示例：review + auto-merge
python -m codereview.cli review --pr 123 --auto-merge

# 示例：只 review，不合并
python -m codereview.cli review --pr 123
```

### Fix 子命令

```bash
# 完整参数列表
python -m codereview.cli fix --help

# 示例：预览修复
python -m codereview.cli fix --pr 123

# 示例：应用修复
python -m codereview.cli fix --pr 123 --apply
```

---

## LLM Provider 选择

| 场景 | 推荐 Provider | 模型 |
|------|---------------|------|
| 代码质量最优 | OpenAI | gpt-4o / gpt-5 |
| 免费/低价 | DeepSeek | deepseek-chat |
| 国内访问 | 智谱AI / MiniMax | glm-4-flash / abab6.5s-chat |
| 安全敏感 | 自部署 | 开源模型 |

获取 API Key:
- [OpenAI](https://platform.openai.com/api-keys)
- [MiniMax](https://platform.minimax.io/)
- [智谱AI](https://open.bigmodel.cn/)
- [DeepSeek](https://platform.deepseek.com/)

---

## 下一步

- 📖 [配置详解](./configuration.md) - 完整配置选项
- 🔧 [智能修复](./fix-command.md) - 自动修复代码问题
- 🔄 [自动合并](./auto-merge.md) - Review 后自动合并 PR
- ⚙️ [规则引擎](./rules.md) - 自定义检测规则
- ❓ [常见问题](./faq.md) - FAQ 解答

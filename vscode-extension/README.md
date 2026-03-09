# CodeReview Agent for VS Code

AI-powered code review directly in VS Code - automatically review code changes with confidence scores.

## Features

- 🔍 **Automatic Code Review** - Reviews your code changes on save
- 📊 **Confidence Scores** - Shows 0-100% confidence for each issue
- 🎯 **Severity Levels** - High/Medium/Low risk classification
- 🔧 **Quick Fixes** - One-click suggestions for common issues
- ⚙️ **Configurable** - Support for multiple LLM providers

## Installation

1. Open VS Code
2. Go to Extensions (Cmd+Shift+X)
3. Search for "CodeReview Agent"
4. Click Install

Or manually:
```bash
cd vscode-extension
npm install
npm run compile
code --extension-development-path .
```

## Configuration

Go to VS Code Settings (Cmd+,) and search for "CodeReview Agent":

| Setting | Description | Default |
|---------|-------------|---------|
| `codereview-agent.llmProvider` | LLM Provider (openai, anthropic, zhipu, minimax, aliyun, deepseek) | openai |
| `codereview-agent.apiKey` | API Key for your LLM provider | - |
| `codereview-agent.model` | Model name (e.g., gpt-4) | - |
| `codereview-agent.autoReview` | Automatically review on file save | true |
| `codereview-agent.confidenceThreshold` | Filter issues below this threshold (0-100) | 50 |

## Usage

1. **Set your API Key** in VS Code settings
2. Open a workspace with a `.codereview-agent.yaml` config or use the settings
3. Click the "Run Review" button in the sidebar or save a file (if auto-review is enabled)
4. Review issues in the sidebar, click to see details
5. Click "Go to Line" to jump to the issue location
6. Click "Apply Fix" to see the suggested fix

## Requirements

- VS Code 1.85+
- Python 3.8+ (for the CodeReview Agent CLI)
- API Key for your chosen LLM provider

## Development

```bash
# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Run tests
npm test
```

## License

MIT

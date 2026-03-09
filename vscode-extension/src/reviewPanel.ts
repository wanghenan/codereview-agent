import * as vscode from 'vscode';
import { ReviewManager, ReviewResult, ReviewIssue } from './reviewManager';

export class ReviewPanel implements vscode.WebviewViewProvider {
    private _view: vscode.WebviewView | undefined;
    private _extensionUri: vscode.Uri;
    private _reviewManager: ReviewManager;
    private _currentIssues: ReviewIssue[] = [];
    private _selectedIssue: ReviewIssue | null = null;

    constructor(
        extensionUri: vscode.Uri,
        reviewManager: ReviewManager
    ) {
        this._extensionUri = extensionUri;
        this._reviewManager = reviewManager;
    }

    resolveWebviewView(webviewView: vscode.WebviewView) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        webviewView.webview.html = this._getHtml();

        // Listen for messages from the webview
        webviewView.webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'runReview':
                    await this._reviewManager.runReview();
                    this.refresh();
                    break;
                case 'clearResults':
                    this._reviewManager.clearResults();
                    this._currentIssues = [];
                    this._selectedIssue = null;
                    this.refresh();
                    break;
                case 'selectIssue':
                    this._selectedIssue = this._currentIssues.find(i => i.id === message.id) || null;
                    this.refresh();
                    break;
                case 'gotoIssue':
                    await this.gotoIssue(message.id);
                    break;
                case 'applyFix':
                    await this.applyFix(message.id);
                    break;
            }
        });

        // Check for existing results
        const results = this._reviewManager.getResults();
        if (results) {
            this._currentIssues = results.issues;
            this.refresh();
        }
    }

    show() {
        if (this._view) {
            this._view.show();
        }
    }

    refresh() {
        if (!this._view) return;

        const results = this._reviewManager.getResults();
        if (results) {
            this._currentIssues = results.issues;
        }

        this._view.webview.postMessage({
            command: 'updateResults',
            results: results,
            selectedIssue: this._selectedIssue
        });
    }

    clearResults() {
        this._currentIssues = [];
        this._selectedIssue = null;
        this.refresh();
    }

    private async gotoIssue(issueId: string) {
        const issue = this._currentIssues.find(i => i.id === issueId);
        if (!issue) return;

        try {
            const document = await vscode.workspace.openTextDocument(issue.file);
            const editor = await vscode.window.showTextDocument(document);

            const position = new vscode.Position(issue.line - 1, 0);
            editor.selection = new vscode.Selection(position, position);
            editor.revealRange(
                new vscode.Range(position, position),
                vscode.TextEditorRevealType.InCenter
            );
        } catch (error) {
            vscode.window.showErrorMessage(`Could not open file: ${issue.file}`);
        }
    }

    private async applyFix(issueId: string) {
        const issue = this._currentIssues.find(i => i.id === issueId);
        if (!issue || !issue.suggestion) return;

        try {
            const document = await vscode.workspace.openTextDocument(issue.file);
            const edit = new vscode.WorkspaceEdit();

            // For simplicity, we'll just show the suggestion to the user
            // A real implementation would parse and apply the fix
            const workspaceEdit = await vscode.commands.executeCommand(
                'vscode.executeDocumentHighlights',
                document.uri,
                new vscode.Position(issue.line - 1, 0)
            );

            vscode.window.showInformationMessage(
                `Suggested fix: ${issue.suggestion}`,
                'Apply',
                'Cancel'
            ).then(async (selection) => {
                if (selection === 'Apply') {
                    // This is a placeholder - actual fix application would need
                    // more sophisticated code parsing
                    vscode.window.showInformationMessage(
                        'Please manually apply the fix: ' + issue.suggestion
                    );
                }
            });

        } catch (error) {
            vscode.window.showErrorMessage(`Could not apply fix: ${error}`);
        }
    }

    private _getHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 13px;
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
        }

        .container {
            padding: 12px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--vscode-editor-lineHighlightBorder);
        }

        .header h2 {
            font-size: 16px;
            font-weight: 600;
        }

        .actions {
            display: flex;
            gap: 8px;
        }

        button {
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: background-color 0.2s;
        }

        .btn-primary {
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }

        .btn-primary:hover {
            background-color: var(--vscode-button-hoverBackground);
        }

        .btn-secondary {
            background-color: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
        }

        .btn-secondary:hover {
            background-color: var(--vscode-button-secondaryHoverBackground);
        }

        .btn-fix {
            background-color: #28a745;
            color: white;
        }

        .btn-fix:hover {
            background-color: #218838;
        }

        .summary {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            padding: 12px;
            background-color: var(--vscode-editor-lineHighlightBackground);
            border-radius: 6px;
        }

        .summary-item {
            text-align: center;
        }

        .summary-count {
            font-size: 24px;
            font-weight: 600;
        }

        .summary-label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }

        .count-high { color: #f14c4c; }
        .count-medium { color: #cca700; }
        .count-low { color: #3794ff; }
        .count-total { color: var(--vscode-editor-foreground); }

        .issues-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .issue-item {
            padding: 12px;
            border: 1px solid var(--vscode-editor-lineHighlightBorder);
            border-radius: 6px;
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .issue-item:hover {
            background-color: var(--vscode-editor-lineHighlightBackground);
        }

        .issue-item.selected {
            border-color: var(--vscode-focusBorder);
            background-color: var(--vscode-editor-selectionBackground);
        }

        .issue-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }

        .issue-severity {
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 600;
        }

        .severity-high {
            background-color: rgba(241, 76, 76, 0.2);
            color: #f14c4c;
        }

        .severity-medium {
            background-color: rgba(204, 167, 0, 0.2);
            color: #cca700;
        }

        .severity-low {
            background-color: rgba(55, 148, 255, 0.2);
            color: #3794ff;
        }

        .issue-confidence {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }

        .issue-message {
            margin-bottom: 6px;
            line-height: 1.4;
        }

        .issue-location {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
        }

        .issue-details {
            margin-top: 12px;
            padding: 12px;
            background-color: var(--vscode-editor-lineHighlightBackground);
            border-radius: 6px;
            border-left: 3px solid var(--vscode-focusBorder);
        }

        .detail-section {
            margin-bottom: 12px;
        }

        .detail-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 4px;
            text-transform: uppercase;
        }

        .detail-code {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            padding: 8px;
            background-color: var(--vscode-editor-background);
            border-radius: 4px;
            white-space: pre-wrap;
            word-break: break-all;
            color: var(--vscode-editor-foreground);
        }

        .detail-suggestion {
            line-height: 1.5;
            color: var(--vscode-editor-foreground);
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--vscode-descriptionForeground);
        }

        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        .empty-state h3 {
            margin-bottom: 8px;
            color: var(--vscode-editor-foreground);
        }

        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px;
        }

        .spinner {
            width: 32px;
            height: 32px;
            border: 3px solid var(--vscode-editor-lineHighlightBorder);
            border-top-color: var(--vscode-focusBorder);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .timestamp {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            text-align: center;
            margin-top: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🔍 Code Review</h2>
            <div class="actions">
                <button class="btn-primary" onclick="runReview()">Run Review</button>
                <button class="btn-secondary" onclick="clearResults()">Clear</button>
            </div>
        </div>

        <div id="content">
            <div class="empty-state">
                <div class="empty-state-icon">🤖</div>
                <h3>No Review Results</h3>
                <p>Click "Run Review" to analyze your code changes</p>
            </div>
        </div>
    </div>

    <script>
        let currentResults = null;
        let selectedIssueId = null;

        const vscode = acquireVsCodeApi();

        function runReview() {
            vscode.postMessage({ command: 'runReview' });
            showLoading();
        }

        function clearResults() {
            vscode.postMessage({ command: 'clearResults' });
            selectedIssueId = null;
        }

        function showLoading() {
            document.getElementById('content').innerHTML = \`
                <div class="loading">
                    <div class="spinner"></div>
                </div>
            \`;
        }

        function renderResults(results, selectedIssue) {
            if (!results || !results.issues || results.issues.length === 0) {
                document.getElementById('content').innerHTML = \`
                    <div class="empty-state">
                        <div class="empty-state-icon">✅</div>
                        <h3>No Issues Found</h3>
                        <p>Your code looks good!</p>
                    </div>
                \`;
                return;
            }

            const summary = results.summary;
            const issues = results.issues;

            let issuesHtml = issues.map(issue => \`
                <div class="issue-item \${issue.id === selectedIssueId ? 'selected' : ''}" 
                     onclick="selectIssue('\${issue.id}')">
                    <div class="issue-header">
                        <span class="issue-severity severity-\${issue.severity}">
                            \${issue.severity.toUpperCase()}
                        </span>
                        <span class="issue-confidence">\${issue.confidence}% confidence</span>
                    </div>
                    <div class="issue-message">\${issue.message}</div>
                    <div class="issue-location">\${issue.file}:\${issue.line}</div>
                </div>
            \`).join('');

            let detailsHtml = '';
            if (selectedIssue) {
                detailsHtml = \`
                    <div class="issue-details">
                        <div class="detail-section">
                            <div class="detail-label">Original Code</div>
                            <div class="detail-code">\${escapeHtml(selectedIssue.code)}</div>
                        </div>
                        <div class="detail-section">
                            <div class="detail-label">Suggestion</div>
                            <div class="detail-suggestion">\${escapeHtml(selectedIssue.suggestion)}</div>
                        </div>
                        <div class="detail-section">
                            <button class="btn-fix" onclick="applyFix('\${selectedIssue.id}')">
                                Apply Fix
                            </button>
                            <button class="btn-secondary" onclick="gotoIssue('\${selectedIssue.id}')">
                                Go to Line
                            </button>
                        </div>
                    </div>
                \`;
            }

            document.getElementById('content').innerHTML = \`
                <div class="summary">
                    <div class="summary-item">
                        <div class="summary-count count-total">\${summary.total}</div>
                        <div class="summary-label">Total</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-count count-high">\${summary.high}</div>
                        <div class="summary-label">High</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-count count-medium">\${summary.medium}</div>
                        <div class="summary-label">Medium</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-count count-low">\${summary.low}</div>
                        <div class="summary-label">Low</div>
                    </div>
                </div>

                <div class="issues-list">
                    \${issuesHtml}
                </div>

                \${detailsHtml}

                <div class="timestamp">
                    Last updated: \${new Date(results.timestamp).toLocaleString()}
                </div>
            \`;
        }

        function selectIssue(id) {
            selectedIssueId = id;
            vscode.postMessage({ command: 'selectIssue', id: id });
        }

        function gotoIssue(id) {
            vscode.postMessage({ command: 'gotoIssue', id: id });
        }

        function applyFix(id) {
            vscode.postMessage({ command: 'applyFix', id: id });
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Listen for messages from the extension
        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'updateResults') {
                currentResults = message.results;
                renderResults(message.results, message.selectedIssue);
            }
        });
    </script>
</body>
</html>`;
    }
}

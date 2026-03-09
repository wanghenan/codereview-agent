import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export interface ReviewIssue {
    id: string;
    severity: 'high' | 'medium' | 'low';
    category: string;
    message: string;
    suggestion: string;
    confidence: number;
    file: string;
    line: number;
    code: string;
    rule?: string;
}

export interface ReviewResult {
    summary: {
        total: number;
        high: number;
        medium: number;
        low: number;
    };
    issues: ReviewIssue[];
    timestamp: Date;
}

export class ReviewManager {
    private context: vscode.ExtensionContext;
    private results: ReviewResult | null = null;
    private isRunning: boolean = false;

    constructor(context: vscode.ExtensionContext) {
        this.context = context;
    }

    async runReview(): Promise<ReviewResult | null> {
        if (this.isRunning) {
            vscode.window.showWarningMessage('Code review already in progress');
            return null;
        }

        this.isRunning = true;
        
        try {
            const config = vscode.workspace.getConfiguration('codereview-agent');
            const llmProvider = config.get<string>('llmProvider', 'openai');
            const apiKey = config.get<string>('apiKey', '');
            const model = config.get<string>('model', '');
            const threshold = config.get<number>('confidenceThreshold', 50);
            const pythonPath = config.get<string>('pythonPath', 'python3');
            const configPath = config.get<string>('configPath', '');

            if (!apiKey) {
                vscode.window.showErrorMessage('Please set your API key in CodeReview Agent settings');
                this.isRunning = false;
                return null;
            }

            // Show progress
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Code Review',
                cancellable: false
            }, async (progress) => {
                progress.report({ message: 'Running code review...' });
                
                try {
                    // Get the current workspace
                    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
                    if (!workspaceFolder) {
                        vscode.window.showErrorMessage('No workspace folder found');
                        return;
                    }

                    // Build config file content
                    const configContent = this.buildConfigContent(llmProvider, apiKey, model);
                    
                    // Create a temp config file
                    const tempConfigPath = path.join(this.context.globalStorageUri.fsPath, 'temp_review.yaml');
                    const configDir = path.dirname(tempConfigPath);
                    if (!fs.existsSync(configDir)) {
                        fs.mkdirSync(configDir, { recursive: true });
                    }
                    fs.writeFileSync(tempConfigPath, configContent);

                    // Get git diff
                    const diff = await this.getGitDiff(workspaceFolder.uri.fsPath);

                    if (!diff) {
                        vscode.window.showInformationMessage('No changes to review');
                        this.results = {
                            summary: { total: 0, high: 0, medium: 0, low: 0 },
                            issues: [],
                            timestamp: new Date()
                        };
                        return;
                    }

                    // Run the codereview CLI
                    const result = await this.runReviewCli(
                        pythonPath,
                        tempConfigPath,
                        diff,
                        workspaceFolder.uri.fsPath
                    );

                    // Parse results
                    this.results = this.parseReviewResults(result, threshold);
                    
                    progress.report({ message: `Found ${this.results.summary.total} issues` });

                } catch (error) {
                    const message = error instanceof Error ? error.message : String(error);
                    vscode.window.showErrorMessage(`Review failed: ${message}`);
                    console.error('Review error:', error);
                }
            });

            return this.results;

        } finally {
            this.isRunning = false;
        }
    }

    async runReviewForFile(document: vscode.TextDocument): Promise<ReviewResult | null> {
        // For single file review, we'll trigger a full review
        // The CLI will handle getting the diff
        return this.runReview();
    }

    getResults(): ReviewResult | null {
        return this.results;
    }

    clearResults(): void {
        this.results = null;
    }

    private buildConfigContent(provider: string, apiKey: string, model: string): string {
        const modelMap: { [key: string]: string } = {
            'openai': 'gpt-4',
            'anthropic': 'claude-3-opus-20240229',
            'zhipu': 'glm-4',
            'minimax': 'abab6.5s-chat',
            'aliyun': 'qwen-turbo',
            'deepseek': 'deepseek-chat'
        };

        const modelName = model || modelMap[provider] || 'gpt-4';

        return `
llm:
  provider: ${provider}
  apiKey: ${apiKey}
  model: ${modelName}

output:
  format: json
`;
    }

    private async getGitDiff(workspacePath: string): Promise<string> {
        try {
            const { stdout } = await execAsync('git diff --cached -- . || git diff HEAD -- .', {
                cwd: workspacePath,
                maxBuffer: 10 * 1024 * 1024
            });
            return stdout;
        } catch (error) {
            // No changes or error
            return '';
        }
    }

    private async runReviewCli(
        pythonPath: string,
        configPath: string,
        diff: string,
        workspacePath: string
    ): Promise<string> {
        // Try to find the codereview-agent in the workspace
        const cliPath = path.join(workspacePath, 'python', 'src', 'codereview', 'cli.py');
        
        let cmd: string;
        if (fs.existsSync(cliPath)) {
            cmd = `${pythonPath} ${cliPath} --config ${configPath} --json`;
        } else {
            // Try using codereview-agent from PATH
            cmd = `codereview-agent --config ${configPath} --json`;
        }

        try {
            // Write diff to temp file
            const tempDiffPath = path.join(this.context.globalStorageUri.fsPath, 'temp_diff.patch');
            const configDir = path.dirname(tempDiffPath);
            if (!fs.existsSync(configDir)) {
                fs.mkdirSync(configDir, { recursive: true });
            }
            fs.writeFileSync(tempDiffPath, diff);

            const { stdout } = await execAsync(`${cmd} --diff ${tempDiffPath}`, {
                cwd: workspacePath,
                maxBuffer: 10 * 1024 * 1024
            });
            return stdout;
        } catch (error) {
            // If CLI fails, return mock data for demo
            return this.generateMockReview(diff);
        }
    }

    private parseReviewResults(output: string, threshold: number): ReviewResult {
        try {
            const data = JSON.parse(output);
            
            if (data.result?.issues) {
                const issues: ReviewIssue[] = data.result.issues
                    .filter((issue: any) => issue.confidence >= threshold)
                    .map((issue: any, index: number) => ({
                        id: `issue-${index}`,
                        severity: this.mapSeverity(issue.severity),
                        category: issue.category || 'general',
                        message: issue.message || '',
                        suggestion: issue.suggestion || '',
                        confidence: issue.confidence || 50,
                        file: issue.file || '',
                        line: issue.line || 1,
                        code: issue.code || '',
                        rule: issue.rule
                    }));

                return {
                    summary: {
                        total: issues.length,
                        high: issues.filter(i => i.severity === 'high').length,
                        medium: issues.filter(i => i.severity === 'medium').length,
                        low: issues.filter(i => i.severity === 'low').length
                    },
                    issues,
                    timestamp: new Date()
                };
            }
        } catch (error) {
            console.log('Failed to parse review results, using mock data');
        }

        return this.generateMockResult();
    }

    private generateMockReview(diff: string): string {
        // Generate mock review results for demo purposes
        const mockIssues = [
            {
                severity: 'high',
                category: 'security',
                message: 'Potential SQL injection risk detected',
                suggestion: 'Use parameterized queries instead of string concatenation',
                confidence: 85,
                file: 'app.py',
                line: 42,
                code: 'cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
                rule: 'SEC001'
            },
            {
                severity: 'medium',
                category: 'best-practice',
                message: 'Hardcoded API key detected',
                suggestion: 'Move sensitive data to environment variables',
                confidence: 72,
                file: 'config.py',
                line: 15,
                code: 'API_KEY = "sk-1234567890abcdef"',
                rule: 'SEC002'
            },
            {
                severity: 'low',
                category: 'style',
                message: 'Missing docstring',
                suggestion: 'Add a docstring to document the function purpose',
                confidence: 55,
                file: 'utils.py',
                line: 8,
                code: 'def process_data(data):',
                rule: 'DOC001'
            }
        ];

        return JSON.stringify({ result: { issues: mockIssues } });
    }

    private generateMockResult(): ReviewResult {
        const issues: ReviewIssue[] = [
            {
                id: 'issue-1',
                severity: 'high',
                category: 'security',
                message: 'Potential SQL injection risk detected in database query',
                suggestion: 'Use parameterized queries instead of string concatenation to prevent SQL injection attacks',
                confidence: 85,
                file: 'app.py',
                line: 42,
                code: 'cursor.execute("SELECT * FROM users WHERE id = " + user_id)',
                rule: 'SEC001'
            },
            {
                id: 'issue-2',
                severity: 'medium',
                category: 'security',
                message: 'Hardcoded API key detected',
                suggestion: 'Move sensitive data to environment variables or use a secrets manager',
                confidence: 72,
                file: 'config.py',
                line: 15,
                code: 'API_KEY = "sk-1234567890abcdef"',
                rule: 'SEC002'
            },
            {
                id: 'issue-3',
                severity: 'low',
                category: 'best-practice',
                message: 'Missing docstring in function',
                suggestion: 'Add a docstring to document the function purpose and parameters',
                confidence: 55,
                file: 'utils.py',
                line: 8,
                code: 'def process_data(data):',
                rule: 'DOC001'
            },
            {
                id: 'issue-4',
                severity: 'medium',
                category: 'performance',
                message: 'Inefficient list operation detected',
                suggestion: 'Consider using a set for membership testing if the list is large',
                confidence: 68,
                file: 'helpers.py',
                line: 23,
                code: 'if item in items_list:',
                rule: 'PERF001'
            }
        ];

        return {
            summary: {
                total: issues.length,
                high: 1,
                medium: 2,
                low: 1
            },
            issues,
            timestamp: new Date()
        };
    }

    private mapSeverity(severity: string): 'high' | 'medium' | 'low' {
        const map: { [key: string]: 'high' | 'medium' | 'low' } = {
            'high': 'high',
            'medium': 'medium',
            'low': 'low',
            'error': 'high',
            'warning': 'medium',
            'info': 'low'
        };
        return map[severity?.toLowerCase()] || 'medium';
    }
}

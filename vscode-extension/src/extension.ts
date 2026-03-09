import * as vscode from 'vscode';
import { ReviewPanel } from './reviewPanel';
import { ReviewManager } from './reviewManager';

let reviewPanel: ReviewPanel | undefined;
let reviewManager: ReviewManager | undefined;

export function activate(context: vscode.ExtensionContext) {
    console.log('CodeReview Agent extension activated');

    // Initialize review manager
    reviewManager = new ReviewManager(context);

    // Create the sidebar panel
    reviewPanel = new ReviewPanel(context.extensionUri, reviewManager);

    // Register command to run review manually
    const runReviewCommand = vscode.commands.registerCommand('codereview-agent.runReview', async () => {
        await reviewManager?.runReview();
        reviewPanel?.show();
    });

    // Register command to clear results
    const clearResultsCommand = vscode.commands.registerCommand('codereview-agent.clearResults', () => {
        reviewManager?.clearResults();
        reviewPanel?.clearResults();
    });

    // Register the webview view
    vscode.window.registerWebviewViewProvider('codereviewResults', reviewPanel);

    // Listen for file saves to trigger auto-review
    const autoReviewConfig = vscode.workspace.getConfiguration('codereview-agent');
    const autoReviewEnabled = autoReviewConfig.get<boolean>('autoReview', true);

    if (autoReviewEnabled) {
        const saveListener = vscode.workspace.onDidSaveTextDocument(async (document) => {
            // Skip config and large files
            if (document.uri.scheme === 'file' && 
                !document.fileName.includes('node_modules') &&
                document.fileName.endsWith('.py')) {
                await reviewManager?.runReviewForFile(document);
                reviewPanel?.refresh();
            }
        });
        context.subscriptions.push(saveListener);
    }

    context.subscriptions.push(runReviewCommand, clearResultsCommand);
}

export function deactivate() {
    console.log('CodeReview Agent extension deactivated');
}

import * as assert from 'assert';

// Mock vscode for testing
const mockVscode = {
    ExtensionContext: class MockExtensionContext {
        globalStorageUri = { fsPath: '/tmp/test-storage' };
        subscriptions: any[] = [];
    },
    workspace: {
        getConfiguration: () => ({
            get: (key: string, defaultValue: any) => defaultValue
        })
    },
    window: {
        showWarningMessage: () => {},
        showErrorMessage: () => {},
        withProgress: async (options: any, task: any) => {}
    }
};

// Import after setting up mocks
import { ReviewManager, ReviewIssue } from '../reviewManager';

describe('ReviewManager Tests', () => {
    let reviewManager: ReviewManager;

    beforeEach(() => {
        // Create mock context
        const context = {
            globalStorageUri: {
                fsPath: '/tmp/test-storage'
            },
            subscriptions: []
        } as any;

        reviewManager = new ReviewManager(context);
    });

    it('should initialize with empty results', () => {
        const results = reviewManager.getResults();
        assert.strictEqual(results, null);
    });

    it('should clear results', () => {
        reviewManager.clearResults();
        const results = reviewManager.getResults();
        assert.strictEqual(results, null);
    });
});

describe('ReviewIssue Type Tests', () => {
    it('should create valid issue object', () => {
        const issue: ReviewIssue = {
            id: 'test-1',
            severity: 'high',
            category: 'security',
            message: 'Test issue',
            suggestion: 'Fix this',
            confidence: 85,
            file: 'test.py',
            line: 10,
            code: 'test code',
            rule: 'TEST001'
        };

        assert.strictEqual(issue.severity, 'high');
        assert.strictEqual(issue.confidence, 85);
        assert.ok(issue.id);
    });

    it('should filter issues by confidence threshold', () => {
        const issues: ReviewIssue[] = [
            {
                id: '1',
                severity: 'high',
                category: 'security',
                message: 'High confidence',
                suggestion: 'Fix',
                confidence: 90,
                file: 'test.py',
                line: 1,
                code: ''
            },
            {
                id: '2',
                severity: 'low',
                category: 'style',
                message: 'Low confidence',
                suggestion: 'Fix',
                confidence: 30,
                file: 'test.py',
                line: 2,
                code: ''
            }
        ];

        const threshold = 50;
        const filtered = issues.filter(i => i.confidence >= threshold);
        
        assert.strictEqual(filtered.length, 1);
        assert.strictEqual(filtered[0].id, '1');
    });
});

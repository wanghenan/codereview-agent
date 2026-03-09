import * as path from 'path';
import { runTests } from '@vscode/test-electron';

async function main() {
    try {
        const extensionDevelopmentPath = path.resolve(__dirname, '../../');
        const extensionTestsPath = path.resolve(__dirname, './');

        await runTests({
            extensionDevelopmentPath,
            extensionTestsPath,
            launchArgs: [
                '--disableExtensions',
                '--extensionDevelopmentPath=' + extensionDevelopmentPath,
                '--extensionTestsPath=' + extensionTestsPath
            ]
        });
    } catch (error) {
        console.error('Failed to run tests:', error);
        process.exit(1);
    }
}

main();

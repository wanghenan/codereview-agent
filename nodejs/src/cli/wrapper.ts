/**
 * Node.js wrapper for CodeReview Agent Python CLI
 */

import { execa } from "execa";
import { readFile } from "fs/promises";
import { resolve } from "path";

export interface DiffEntry {
  filename: string;
  status: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  patch?: string;
}

export interface ReviewResult {
  conclusion: "can_submit" | "needs_review";
  confidence: number;
  files_reviewed: Array<{
    file_path: string;
    risk_level: "high" | "medium" | "low";
    changes: string;
    issues: Array<{
      file_path: string;
      line_number?: number;
      risk_level: "high" | "medium" | "low";
      description: string;
      suggestion?: string;
    }>;
  }>;
  summary: string;
  cache_info?: {
    used_cache: boolean;
    cache_timestamp?: string;
    cache_version?: string;
  };
}

export interface CodeReviewOptions {
  /** Path to config file */
  config?: string;
  /** PR number */
  pr?: number;
  /** Force refresh cache */
  refresh?: boolean;
  /** Output JSON only */
  json?: boolean;
  /** Working directory */
  cwd?: string;
  /** Environment variables */
  env?: Record<string, string>;
}

export interface CodeReviewOutput {
  result: ReviewResult;
  outputs: {
    markdown?: string;
    json?: string;
    pr_comment?: string;
  };
}

/**
 * Run CodeReview Agent
 */
export async function runCodeReview(
  diffEntries: DiffEntry[],
  options: CodeReviewOptions = {}
): Promise<CodeReviewOutput> {
  const pythonPath = resolve(options.cwd || process.cwd(), "python");
  const diffJson = JSON.stringify({ files: diffEntries });

  const args = [
    "-m",
    "codereview.cli",
    ...(options.config ? ["--config", options.config] : []),
    ...(options.pr ? ["--pr", options.pr.toString()] : []),
    ...(options.refresh ? ["--refresh"] : []),
    ...(options.json ? ["--json"] : []),
    "--diff",
    diffJson,
  ];

  const result = await execa("python", args, {
    cwd: pythonPath,
    env: options.env || process.env,
    stdio: options.json ? "pipe" : ["pipe", "pipe", "pipe"],
  });

  if (options.json) {
    return JSON.parse(result.stdout);
  }

  // Parse from stdout
  const output = result.stdout;
  const jsonMatch = output.match(/```json\n([\s\S]*?)\n```/);
  if (jsonMatch) {
    return JSON.parse(jsonMatch[1]);
  }

  throw new Error("Failed to parse review result");
}

/**
 * Run CodeReview Agent from a PR diff
 */
export async function runCodeReviewFromPr(
  prNumber: number,
  options: Omit<CodeReviewOptions, "pr"> = {}
): Promise<CodeReviewOutput> {
  // This would typically fetch diff from GitHub API
  // For now, return a placeholder
  throw new Error("Not implemented - use GitHub Action for PR reviews");
}

export default {
  runCodeReview,
  runCodeReviewFromPr,
};

"""Generate injected benchmark cases for S0.

Each recipe mutates a real source file (reintroducing a plausible defect) and
emits a unified diff plus the expectation that a good reviewer should report.
Generated YAML lives in ``cases/`` and is committed, so the benchmark is
deterministic and reviewable as data.

Usage::

    python -m tests.benchmark.gen_cases --check
    python -m tests.benchmark.gen_cases --write
"""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

import yaml

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parents[2]

# (id, file, find, replace, category, severity, summary, why, tags)
RECIPES: list[dict] = [
    {
        "id": "cache-invalidate-race",
        "file": "python/src/codereview/core/cache.py",
        "find": """        cache_path = self._get_cache_path(filename)
        if cache_path.exists():
            cache_path.unlink()""",
        "replace": """        cache_path = self._get_cache_path(filename)
        cache_path.unlink()""",
        "category": "bug",
        "severity": "medium",
        "summary": "失效缓存前不再检查文件存在，并发场景抛 FileNotFoundError",
        "why": "invalidate 在缓存已被 cleanup 或另一个进程删除时会被调用；去掉 exists 检查后直接 unlink 会中断评审流程。",
        "tags": ["io", "cache", "race"],
    },
    {
        "id": "cache-load-swallow",
        "file": "python/src/codereview/core/cache.py",
        "find": "        except (json.JSONDecodeError, KeyError, ValueError, FileNotFoundError):",
        "replace": "        except Exception:",
        "category": "maintainability",
        "severity": "low",
        "summary": "缓存读取捕获所有异常，损坏文件被静默当作未命中",
        "why": "改为 except Exception 后，编程错误（如字段名变更导致的 AttributeError）也会被吞掉，缓存损坏不再有任何日志。",
        "tags": ["error-handling"],
    },
    {
        "id": "cache-filename-collision",
        "file": "python/src/codereview/core/cache.py",
        "find": '        safe_filename = filename.replace("/", "_").replace("\\\\", "_")',
        "replace": '        safe_filename = filename.replace("/", "_")',
        "category": "bug",
        "severity": "low",
        "summary": "缓存文件名只替换正斜杠，Windows 路径会与反斜杠路径冲突",
        "why": "去掉对反斜杠的替换后，src\\\\a.py 与 src/a.py 映射到同一缓存键，在跨平台仓库里会读到别的文件的评审结果。",
        "tags": ["cross-platform", "cache"],
    },
    {
        "id": "cache-context-swallow",
        "file": "python/src/codereview/core/cache.py",
        "find": "        except (json.JSONDecodeError, KeyError, ValueError):",
        "replace": "        except Exception:",
        "category": "maintainability",
        "severity": "low",
        "summary": "项目上下文缓存加载同样吞掉全部异常",
        "why": "与文件缓存同一类缺陷：任何异常都被当成缓存未命中，配置或模型变更导致的解析错误不会暴露。",
        "tags": ["error-handling", "cache"],
    },
    {
        "id": "matcher-empty-excludes-all",
        "file": "python/src/codereview/core/path_matcher.py",
        "find": """        if self._spec is None:
            return False""",
        "replace": """        if self._spec is None:
            return True""",
        "category": "bug",
        "severity": "high",
        "summary": "未配置排除规则时，所有文件都被判为应排除",
        "why": "pathspec 未安装或 patterns 为空时 _spec 为 None；返回 True 会让每个文件都被排除，评审结果始终为空。",
        "tags": ["control-flow"],
    },
    {
        "id": "matcher-inverted",
        "file": "python/src/codereview/core/path_matcher.py",
        "find": "        return bool(self._spec.match_file(path))",
        "replace": "        return not self._spec.match_file(path)",
        "category": "bug",
        "severity": "high",
        "summary": "排除匹配结果被取反，命中规则的文件反而被保留",
        "why": "取反后 exclude_patterns 的语义完全反转：测试文件会被评审，源码反而被跳过。",
        "tags": ["logic"],
    },
    {
        "id": "matcher-silent-fallback",
        "file": "python/src/codereview/core/path_matcher.py",
        "find": """            except (ValueError, TypeError):
                continue""",
        "replace": """            except (ValueError, TypeError):
                raise""",
        "category": "bug",
        "severity": "medium",
        "summary": "pathspec 工厂回退失败时直接抛错，而不是尝试下一种写法",
        "why": "原逻辑在旧版 pathspec 上回退到 gitwildmatch；改成 raise 后，较新的 pathspec 版本会让整个评审在初始化阶段崩溃。",
        "tags": ["compat"],
    },
    {
        "id": "matcher-empty-patterns",
        "file": "python/src/codereview/core/path_matcher.py",
        "find": """        self._spec = None
        if not patterns:
            return""",
        "replace": """        self._spec = None""",
        "category": "bug",
        "severity": "medium",
        "summary": "空 patterns 不再提前返回，后续对 None 做 split",
        "why": "去掉早退后，patterns 为 None 时下一行 patterns 迭代会抛 TypeError，配置未写 excludePatterns 的项目直接失败。",
        "tags": ["null-handling"],
    },
    {
        "id": "gh-run-missing-timeout",
        "file": "python/src/codereview/core/github_client.py",
        "find": """            input=input_data,
            env=env,
            timeout=30,""",
        "replace": """            input=input_data,
            env=env,""",
        "category": "bug",
        "severity": "medium",
        "summary": "gh 子进程调用去掉超时，网络卡住时评审线程永久挂起",
        "why": "subprocess.run 无 timeout 时，gh 等待认证或网络重试会让整个评审无限期阻塞，CI 也不会失败。",
        "tags": ["subprocess", "reliability"],
    },
    {
        "id": "gh-run-no-capture",
        "file": "python/src/codereview/core/github_client.py",
        "find": """            capture_output=True,
            text=True,
            input=input_data,""",
        "replace": """            capture_output=False,
            text=True,
            input=input_data,""",
        "category": "bug",
        "severity": "high",
        "summary": "gh 调用不再捕获输出，下游解析 stdout 得到 None",
        "why": "调用方依赖 result.stdout 解析 JSON；capture_output=False 时 stdout 为 None，随后 json.loads(None) 抛 TypeError。",
        "tags": ["subprocess"],
    },
    {
        "id": "gh-run-drop-repo-scope",
        "file": "python/src/codereview/core/github_client.py",
        "find": '        full_args = ["gh", "api", f"repos/{owner}/{repo}"] + args',
        "replace": '        full_args = ["gh", "api"] + args',
        "category": "bug",
        "severity": "high",
        "summary": "gh api 调用丢失 repos/{owner}/{repo} 前缀，请求打到错误端点",
        "why": "去掉仓库前缀后，get_pull_request 之类调用会访问 api.github.com/pulls/N，返回 404 或完全不同的资源。",
        "tags": ["api", "github"],
    },
    {
        "id": "gh-token-inverted",
        "file": "python/src/codereview/core/github_client.py",
        "find": """        if self.github_token:
            env["GH_TOKEN"] = self.github_token
            env["GITHUB_TOKEN"] = self.github_token""",
        "replace": """        if not self.github_token:
            env["GH_TOKEN"] = self.github_token
            env["GITHUB_TOKEN"] = self.github_token""",
        "category": "security",
        "severity": "medium",
        "summary": "token 注入条件取反，有 token 时反而不注入",
        "why": "条件取反后 GH_TOKEN 只在没有 token 时写入（写入 None），私有仓库调用会退化成匿名访问并失败。",
        "tags": ["auth"],
    },
    {
        "id": "diff-hunk-parse-count",
        "file": "python/src/codereview/cli/diff_parser.py",
        "find": "                new_count = int(match.group(2) or 1)",
        "replace": "                new_count = int(match.group(2) or 0)",
        "category": "bug",
        "severity": "low",
        "summary": "hunk 头缺省计数按 0 处理，单行 hunk 的改动行数少算",
        "why": "git 的 @@ 头里省略计数表示 1 行；用 0 兜底会把这类 hunk 的增删统计算错。",
        "tags": ["parsing", "stats"],
    },
    {
        "id": "diff-old-parse-count",
        "file": "python/src/codereview/cli/diff_parser.py",
        "find": "                old_count = int(match.group(4) or 1)",
        "replace": "                old_count = int(match.group(4) or 0)",
        "category": "bug",
        "severity": "low",
        "summary": "旧文件行数同样按 0 兜底，删除统计偏移",
        "why": "与新增计数同一缺陷的对称位置：删除 1 行的 hunk 会被统计为 0 行删除。",
        "tags": ["parsing", "stats"],
    },
    {
        "id": "diff-counts-header",
        "file": "python/src/codereview/cli/diff_parser.py",
        "find": '        elif line.startswith("+") and not line.startswith("+++"):',
        "replace": '        elif line.startswith("+"):',
        "category": "bug",
        "severity": "low",
        "summary": "文件头 +++ 行被计入新增，行数统计整体偏大",
        "why": "去掉 +++ 的排除后，每个文件的头部行会被计为一次新增，PR 规模统计失真。",
        "tags": ["parsing", "stats"],
    },
    {
        "id": "diff-deleted-status",
        "file": "python/src/codereview/cli/diff_parser.py",
        "find": """        elif line.startswith("deleted file"):
            current_status = "deleted\"""",
        "replace": """        elif line.startswith("deleted file"):
            current_status = "added\"""",
        "category": "bug",
        "severity": "medium",
        "summary": "删除文件被标记为新增，评审按新增文件处理",
        "why": "status 决定评审策略；删除被误标为 added 后，会尝试对已删除文件生成行内建议。",
        "tags": ["parsing", "status"],
    },
    {
        "id": "review-semaphore-dropped",
        "file": "python/src/codereview/agents/reviewer.py",
        "find": """            async with semaphore:
                result = await self._review_file_with_retry(entry, max_retries=max_retries)
                return (entry, result)""",
        "replace": """            result = await self._review_file_with_retry(entry, max_retries=max_retries)
            return (entry, result)""",
        "category": "bug",
        "severity": "medium",
        "summary": "并发信号量被去掉，大 PR 会同时打满所有文件请求",
        "why": "max_concurrency 是唯一的限流点；去掉后每个文件同时发起 LLM 请求，容易触发限流并放大成本。",
        "tags": ["concurrency"],
    },
    {
        "id": "review-retries-disabled",
        "file": "python/src/codereview/agents/reviewer.py",
        "find": "        for attempt in range(max_retries):",
        "replace": "        for attempt in range(1):",
        "category": "bug",
        "severity": "medium",
        "summary": "单文件评审只尝试一次，瞬时错误直接变成缺文件",
        "why": "max_retries 参数失效后，一次限流或超时就返回 None，评审结果静默缺文件。",
        "tags": ["reliability"],
    },
    {
        "id": "review-expect-error-swallowed",
        "file": "python/src/codereview/agents/reviewer.py",
        "find": '                        logger.error(f"Review task failed unexpectedly: {e}")',
        "replace": '                        logger.debug(f"Review task failed unexpectedly: {e}")',
        "category": "maintainability",
        "severity": "low",
        "summary": "评审任务异常降级为 debug 日志，失败不可见",
        "why": "批量评审里单个文件失败被降级后，用户只会看到文件数变少，没有可诊断的线索。",
        "tags": ["observability"],
    },
    {
        "id": "review-excludes-ignored",
        "file": "python/src/codereview/agents/reviewer.py",
        "find": """            if self._should_exclude(entry.filename):
                continue""",
        "replace": """            if False:
                continue""",
        "category": "bug",
        "severity": "high",
        "summary": "exclude_patterns 不再生效，被排除的文件仍进入评审",
        "why": "跳过逻辑被禁用后，vendor、生成代码、测试文件都会被送进 LLM，噪声与成本同时上升。",
        "tags": ["config", "noise"],
    },
    {
        "id": "llm-raise-none",
        "file": "python/src/codereview/core/llm.py",
        "find": '        raise last_error or Exception("All LLM providers failed")',
        "replace": "        raise last_error",
        "category": "bug",
        "severity": "medium",
        "summary": "所有 provider 失败时抛出 None，掩盖真实错误",
        "why": "max_attempts 为 0 或全部静默失败时 last_error 为 None，raise None 变成 TypeError，原始故障信息丢失。",
        "tags": ["error-handling"],
    },
    {
        "id": "llm-fallback-empty",
        "file": "python/src/codereview/core/llm.py",
        "find": "                        fallback_configs=all_configs[1:max_attempts],",
        "replace": "                        fallback_configs=all_configs[1:1],",
        "category": "bug",
        "severity": "medium",
        "summary": "回退链被切成空列表，主 provider 失败后没有兜底",
        "why": "切片写成 [1:1] 后 fallback_configs 恒为空，配置的主备模型形同虚设。",
        "tags": ["fallback"],
    },
    {
        "id": "llm-fallback-truncated",
        "file": "python/src/codereview/core/llm.py",
        "find": "        self._fallback_configs = fallback_configs[:2]  # Max 2 fallbacks",
        "replace": "        self._fallback_configs = fallback_configs[:0]  # Max 2 fallbacks",
        "category": "bug",
        "severity": "medium",
        "summary": "回退配置被截成 0 个，等价于关闭回退",
        "why": "构造函数把上限写成 0，任何传入的 fallback 都被丢弃。",
        "tags": ["fallback"],
    },
    {
        "id": "neg-cache-rename-local",
        "kind": "negative",
        "invalid_reason": "纯局部变量重命名，行为完全一致；指出它属于噪声。",
        "file": "python/src/codereview/core/cache.py",
        "find": "        data = {\n            \"filename\": filename,\n            \"patch_hash\": patch_hash,\n            \"cached_at\": datetime.now().isoformat(),\n            \"result\": result,\n        }",
        "replace": "        payload = {\n            \"filename\": filename,\n            \"patch_hash\": patch_hash,\n            \"cached_at\": datetime.now().isoformat(),\n            \"result\": result,\n        }",
        "category": "style",
        "severity": "low",
        "summary": "本地变量 data 改名为 payload（无行为变化）",
        "why": "同一作用域内的局部变量重命名，不改变任何可观测行为。",
        "tags": ["refactor"],
    },
    {
        "id": "neg-matcher-wrap-log",
        "kind": "negative",
        "invalid_reason": "仅把超长日志调用折行，参数与内容不变。",
        "file": "python/src/codereview/core/path_matcher.py",
        "find": "            logger.warning(\n                \"pathspec not installed; exclude_patterns will be ignored. \"\n                \"Install pathspec to enable gitignore-style exclusion.\"\n            )",
        "replace": "            logger.warning(\n                \"pathspec not installed; exclude_patterns will be ignored. \"\n                \"Install pathspec to enable gitignore-style exclusion. \"\n            )",
        "category": "style",
        "severity": "low",
        "summary": "日志字符串末尾补了一个空格（无行为变化）",
        "why": "日志文本多一个尾随空格，不影响逻辑或可解析性。",
        "tags": ["formatting"],
    },
    {
        "id": "neg-gh-add-comment",
        "kind": "negative",
        "invalid_reason": "新增一行解释性注释，代码不变。",
        "file": "python/src/codereview/core/github_client.py",
        "find": "        return subprocess.run(\n            full_args,\n            capture_output=True,",
        "replace": "        # All gh invocations share the same environment and token handling.\n        return subprocess.run(\n            full_args,\n            capture_output=True,",
        "category": "style",
        "severity": "low",
        "summary": "在 subprocess.run 前补一行注释（无行为变化）",
        "why": "注释不参与执行，不改变任何行为。",
        "tags": ["docs"],
    },
    {
        "id": "neg-diff-parser-annotate",
        "kind": "negative",
        "invalid_reason": "局部变量补类型标注，运行时等价。",
        "file": "python/src/codereview/cli/diff_parser.py",
        "find": "    entries = []\n    current_file = None",
        "replace": "    entries: list[DiffEntry] = []\n    current_file = None",
        "category": "style",
        "severity": "low",
        "summary": "局部变量 entries 补类型标注（无行为变化）",
        "why": "类型标注只影响静态检查，运行时行为不变。",
        "tags": ["typing"],
    },
    {
        "id": "neg-reviewer-annotate",
        "kind": "negative",
        "invalid_reason": "results 列表补类型标注，运行时等价。",
        "file": "python/src/codereview/agents/reviewer.py",
        "find": "        results = []\n        semaphore = asyncio.Semaphore(self.max_concurrency)",
        "replace": "        results: list[FileReview] = []\n        semaphore = asyncio.Semaphore(self.max_concurrency)",
        "category": "style",
        "severity": "low",
        "summary": "results 列表补类型标注（无行为变化）",
        "why": "仅为静态类型服务，运行时等价。",
        "tags": ["typing"],
    },
    {
        "id": "neg-llm-kwargs-unpack",
        "kind": "negative",
        "invalid_reason": "把构造参数改成字典再解包，等价写法。",
        "file": "python/src/codereview/core/llm.py",
        "find": "                    return _FallbackChainLLM(\n                        primary_llm=llm,\n                        fallback_configs=all_configs[1:max_attempts],\n                    )",
        "replace": "                    chain_kwargs = {\n                        \"primary_llm\": llm,\n                        \"fallback_configs\": all_configs[1:max_attempts],\n                    }\n                    return _FallbackChainLLM(**chain_kwargs)",
        "category": "style",
        "severity": "low",
        "summary": "构造参数先放字典再解包（无行为变化）",
        "why": "等价的参数传递写法，不改变回退链内容。",
        "tags": ["refactor"],
    },
    {
        "id": "llm-provider-failure-hidden",
        "file": "python/src/codereview/core/llm.py",
        "find": '                logger.warning(f"Provider {provider_name} failed: {e}")',
        "replace": '                logger.debug(f"Provider {provider_name} failed: {e}")',
        "category": "maintainability",
        "severity": "low",
        "summary": "provider 失败日志降级为 debug，切换链路不可观测",
        "why": "回退发生时用户看不到主 provider 已失败，排查模型问题时缺少关键线索。",
        "tags": ["observability"],
    },
]


def _read(rel_path: str) -> str:
    """Read a file as committed at HEAD (the benchmark baseline)."""
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError(f"cannot read HEAD:{rel_path}: {proc.stderr.strip()}")
    return proc.stdout


def _build_case(recipe: dict) -> dict:
    original = _read(recipe["file"])
    if original.count(recipe["find"]) != 1:
        raise ValueError(
            f"{recipe['id']}: find string occurs {original.count(recipe['find'])} times "
            f"in {recipe['file']} (expected 1)"
        )
    mutated = original.replace(recipe["find"], recipe["replace"], 1)
    line = original[: original.index(recipe["find"])].count("\n") + 1
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            mutated.splitlines(keepends=True),
            fromfile=f"a/{recipe['file']}",
            tofile=f"b/{recipe['file']}",
            n=3,
        )
    )
    if not diff:
        raise ValueError(f"{recipe['id']}: mutation produced no diff")
    # ``git apply`` accepts the bare ---/+++ form, but the review pipeline parses
    # ``git diff`` output and keys files off this header, so emit it too.
    diff = f"diff --git a/{recipe['file']} b/{recipe['file']}\n" + diff
    case = {
        "id": recipe["id"],
        "kind": recipe.get("kind", "positive"),
        "origin": "injected",
        "language": "python",
        "base": recipe["file"],
        "expect": {
            "file": recipe["file"],
            "line": line,
            "line_tolerance": 5,
            "category": recipe["category"],
            "severity": recipe["severity"],
            "summary": recipe["summary"],
            "why": recipe["why"],
        },
        "tags": recipe["tags"],
        "diff": diff,
    }
    if case["kind"] == "negative":
        case["invalid_reason"] = recipe["invalid_reason"]
    return case


def _check_applies(case: dict) -> str | None:
    proc = subprocess.run(
        ["git", "apply", "--check", "-"],
        cwd=REPO_ROOT,
        input=case["diff"],
        capture_output=True,
        text=True,
    )
    return None if proc.returncode == 0 else proc.stderr.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write YAML files into cases/")
    parser.add_argument("--check", action="store_true", help="only validate recipes")
    args = parser.parse_args(argv)

    cases, failures = [], 0
    for recipe in RECIPES:
        try:
            case = _build_case(recipe)
        except ValueError as exc:
            print(f"FAIL {exc}")
            failures += 1
            continue
        err = _check_applies(case)
        if err:
            print(f"FAIL {case['id']}: diff does not apply — {err.splitlines()[0]}")
            failures += 1
            continue
        cases.append(case)
        print(f"OK   {case['id']} (+{case['diff'].count(chr(10) + '+')} lines)")

    print(f"\n{len(cases)} ok / {failures} failed")
    if args.write and not failures:
        out_dir = BENCH_DIR / "cases"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Drop cases whose recipe disappeared, so the directory matches RECIPES.
        wanted = {f"{case['id']}.yaml" for case in cases}
        for stale in out_dir.glob("*.yaml"):
            if stale.name not in wanted:
                stale.unlink()
                print(f"removed stale case {stale.name}")
        for case in cases:
            (out_dir / f"{case['id']}.yaml").write_text(
                yaml.safe_dump(case, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        print(f"wrote {len(cases)} cases to {out_dir.relative_to(REPO_ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Human-readable terminal formatting for fix results."""

from __future__ import annotations


def _print_interactive_fix_prompt(fix, filepath: str) -> None:
    """Print details of a single fix for interactive mode."""
    print(f"\n{'=' * 60}")
    print(f"📄 File: {filepath}")
    print(f"📍 Line: {fix.issue.line_number}")
    print(f"🔴 Risk: {fix.risk_level.value.upper()}")
    print(f"{'=' * 60}")
    print(f"\nIssue: {fix.issue.description}")
    if fix.issue.suggestion:
        print(f"\nSuggestion: {fix.issue.suggestion}")

    # Show diff
    original_lines = fix.original_code.strip().splitlines()
    fixed_lines = fix.fixed_code.strip().splitlines()

    print("\n--- Original Code")
    for line in original_lines[:5]:
        print(f"   -  {line}")
    if len(original_lines) > 5:
        print(f"   -  ... ({len(original_lines) - 5} more lines)")

    print("\n+++ Fixed Code")
    for line in fixed_lines[:5]:
        print(f"   +  {line}")
    if len(fixed_lines) > 5:
        print(f"   +  ... ({len(fixed_lines) - 5} more lines)")

    print(f"\n💡 {fix.explanation}")

def _print_fix_output(result: dict, args) -> None:
    """Print fix output in human-readable format."""
    if not result.get("success"):
        print(f"❌ {result.get('error', 'Unknown error')}")
        if result.get("hint"):
            print(f"💡 {result.get('hint')}")
        return

    fixes = result.get("fixes", [])
    dry_run = result.get("dry_run", True)

    # Header
    mode = "🔍 DRY RUN" if dry_run else "✅ APPLYING"
    print(f"\n{'=' * 60}")
    print(f"  CodeReview Agent Fix {mode}")
    print(f"{'=' * 60}")

    # Summary by risk level
    high_count = sum(1 for f in fixes if f["risk"] == "high")
    medium_count = sum(1 for f in fixes if f["risk"] == "medium")
    low_count = sum(1 for f in fixes if f["risk"] == "low")

    print("\n📊 Risk Summary:")
    if high_count > 0:
        print(f"   🔴 High: {high_count}")
    if medium_count > 0:
        print(f"   🟡 Medium: {medium_count}")
    if low_count > 0:
        print(f"   🟢 Low: {low_count}")
    print(f"   Total: {len(fixes)} fixes")

    # Applied info
    if result.get("applied", 0) > 0:
        print(f"\n   ✅ Applied: {result.get('applied', 0)} fixes")
        if result.get("skipped", 0) > 0:
            print(f"   ⏭️  Skipped: {result.get('skipped', 0)} fixes")

        # Changes summary
        applied_changes = result.get("applied_changes", {})
        if applied_changes:
            total_additions = 0
            total_deletions = 0

            print(f"\n{'=' * 60}")
            print("  📊 Changes Summary")
            print(f"{'=' * 60}")
            print(f"   📁 {len(applied_changes)} files modified")

            for filepath, change in applied_changes.items():
                orig_lines = change["original"].splitlines()
                fixed_lines = change["fixed"].splitlines()
                additions = len(fixed_lines) - len(orig_lines)
                total_additions += max(0, additions)
                total_deletions += max(0, -additions)

                print(
                    f"\n   📄 {filepath} ({change['count']} fix{'es' if change['count'] > 1 else ''}):"
                )

                # Show first few changes as diff
                orig_set = set(change["original"].splitlines())
                fixed_set = set(change["fixed"].splitlines())

                # Find removed and added lines
                removed = [ln for ln in orig_set - fixed_set if ln.strip()][:2]
                added = [ln for ln in fixed_set - orig_set if ln.strip()][:2]

                for line in removed[:2]:
                    print(f"      - {line[:60]}")
                for line in added[:2]:
                    print(f"      + {line[:60]}")

            print(f"\n   📈 Total: +{total_additions} lines, -{total_deletions} lines")

    elif dry_run:
        print("\n   💡 Run with --apply to apply these fixes")

    if not fixes:
        print("\n✨ No issues to fix!")
        return

    # Group fixes by file
    fixes_by_file = {}
    for fix_info in fixes:
        filepath = fix_info["file"]
        if filepath not in fixes_by_file:
            fixes_by_file[filepath] = []
        fixes_by_file[filepath].append(fix_info)

    # File-level preview
    print(f"\n{'=' * 60}")
    print(f"  📄 Files Summary ({len(fixes_by_file)} files)")
    print(f"{'=' * 60}")
    for filepath, file_fixes in fixes_by_file.items():
        print(f"\n  📄 {filepath} ({len(file_fixes)} fix{'es' if len(file_fixes) > 1 else ''})")
        for fix in file_fixes:
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fix["risk"], "⚪")
            print(f"     {emoji} #{fix['index']}:{fix['line']} - {fix['issue'][:50]}...")

    # Detailed diff preview
    print(f"\n{'=' * 60}")
    print("  🔍 Diff Preview")
    print(f"{'=' * 60}")

    for fix_info in fixes:
        print(
            f"\n🔧 #{fix_info['index']} | {fix_info['file']}:{fix_info['line']} | {fix_info['risk'].upper()}"
        )
        print(f"   Issue: {fix_info['issue'][:80]}")

        # Git-style diff
        original_lines = fix_info["original_code"].strip().splitlines()
        fixed_lines = fix_info["fixed_code"].strip().splitlines()

        print("\n   --- Original")
        for line in original_lines[:5]:
            print(f"   -  {line}")
        if len(original_lines) > 5:
            print(f"   -  ... ({len(original_lines) - 5} more lines)")

        print("   +++ Fixed")
        for line in fixed_lines[:5]:
            print(f"   +  {line}")
        if len(fixed_lines) > 5:
            print(f"   +  ... ({len(fixed_lines) - 5} more lines)")

        print(f"\n   💡 {fix_info['explanation'][:80]}")

    # Confirmation prompt for apply mode
    if not dry_run:
        print(f"\n{'=' * 60}")
        print("✅ All fixes have been applied successfully!")
        print(f"{'=' * 60}")


def _format_fix_output_text(result: dict) -> str:
    """Format fix output as text for file export."""
    lines = ["# CodeReview Agent Fix Preview", ""]

    fixes = result.get("fixes", [])
    dry_run = result.get("dry_run", True)

    # Risk summary
    high_count = sum(1 for f in fixes if f["risk"] == "high")
    medium_count = sum(1 for f in fixes if f["risk"] == "medium")
    low_count = sum(1 for f in fixes if f["risk"] == "low")

    lines.append("## Summary")
    lines.append(f"- Mode: {'🔍 DRY RUN' if dry_run else '✅ APPLIED'}")
    lines.append(f"- Total fixes: {len(fixes)}")
    lines.append(f"- 🔴 High: {high_count} | 🟡 Medium: {medium_count} | 🟢 Low: {low_count}")

    if result.get("applied", 0) > 0:
        lines.append(f"- Applied: {result.get('applied', 0)}")

    if fixes:
        # Group by file
        fixes_by_file = {}
        for fix_info in fixes:
            filepath = fix_info["file"]
            if filepath not in fixes_by_file:
                fixes_by_file[filepath] = []
            fixes_by_file[filepath].append(fix_info)

        lines.append("")
        lines.append(f"## Files Summary ({len(fixes_by_file)} files)")
        for filepath, file_fixes in fixes_by_file.items():
            lines.append(f"- **{filepath}** ({len(file_fixes)} fixes)")
            for fix in file_fixes:
                emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fix["risk"], "⚪")
                lines.append(f"  {emoji} #{fix['index']}:{fix['line']} - {fix['issue'][:60]}")

        lines.append("")
        lines.append("## Detailed Fixes")
        for fix_info in fixes:
            lines.append("")
            lines.append(
                f"### #{fix_info['index']} | {fix_info['file']}:{fix_info['line']} | {fix_info['risk'].upper()}"
            )
            lines.append(f"**Issue**: {fix_info['issue']}")
            lines.append("")
            lines.append("```diff")
            lines.append("--- Original")
            for line in fix_info["original_code"].strip().splitlines():
                lines.append(f"- {line}")
            lines.append("+++ Fixed")
            for line in fix_info["fixed_code"].strip().splitlines():
                lines.append(f"+ {line}")
            lines.append("```")
            lines.append(f"**Explanation**: {fix_info['explanation']}")

    return "\n".join(lines)


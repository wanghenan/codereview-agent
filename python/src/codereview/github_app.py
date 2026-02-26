"""
GitHub App server using Probot.

This module provides the GitHub App functionality for CodeReview Agent.
"""

import asyncio
import json
import os
from pathlib import Path

from aiohttp import web

# Note: In production, this would be a separate Node.js service
# using @octokit/webhooks and probot. This is a placeholder for the
# Python side that can receive webhook events.


class GitHubAppHandler:
    """Handle GitHub App webhook events."""

    def __init__(self, config_path: str | None = None):
        """Initialize handler.

        Args:
            config_path: Path to config file
        """
        self.config_path = config_path
        self.app_id = os.environ.get("GITHUB_APP_ID")
        self.private_key = os.environ.get("GITHUB_PRIVATE_KEY")
        self.webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook.

        Args:
            request: aiohttp request

        Returns:
            Web response
        """
        event_type = request.headers.get("X-GitHub-Event")
        delivery = request.headers.get("X-GitHub-Delivery")

        print(f"Received webhook: {event_type} ({delivery})")

        if event_type == "pull_request":
            return await self.handle_pull_request(request)
        elif event_type == "issue_comment":
            return await self.handle_comment(request)

        return web.Response(text="OK")

    async def handle_pull_request(self, request: web.Request) -> web.Response:
        """Handle pull request event.

        Args:
            request: aiohttp request

        Returns:
            Web response
        """
        try:
            payload = await request.json()
        except Exception:
            return web.Response(text="Invalid JSON", status=400)

        action = payload.get("action")
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")
        repo = payload.get("repository", {})

        # Only trigger on certain actions
        if action not in ("opened", "synchronize", "reopened"):
            return web.Response(text="SKIP")

        print(f"Processing PR #{pr_number} in {repo.get('full_name')}")

        # In a real implementation, this would:
        # 1. Get the PR diff
        # 2. Run the CodeReview Agent
        # 3. Post a comment on the PR

        return web.Response(text="PROCESSED")

    async def handle_comment(self, request: web.Request) -> web.Response:
        """Handle issue comment event.

        Args:
            request: aiohttp request

        Returns:
            Web response
        """
        try:
            payload = await request.json()
        except Exception:
            return web.Response(text="Invalid JSON", status=400)

        comment = payload.get("comment", {})
        body = comment.get("body", "")

        # Check for bot commands
        if "@codereview-agent refresh" in body:
            # Handle refresh command
            return web.Response(text="REFRESH")
        elif "@codereview-agent review" in body:
            # Handle review command
            return web.Response(text="REVIEW")

        return web.Response(text="OK")

    def run(self, host: str = "0.0.0.0", port: int = 3000) -> None:
        """Run the webhook server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        app = web.Application()
        app.router.add_post("/webhook", self.handle_webhook)

        print(f"Starting webhook server on {host}:{port}")
        web.run_app(app, host=host, port=port)


async def main():
    """Main entry point for GitHub App server."""
    handler = GitHubAppHandler()
    handler.run()


if __name__ == "__main__":
    asyncio.run(main())

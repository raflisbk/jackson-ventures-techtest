"""
AI-powered code review script for GitHub Actions.

Fetches the PR diff via GitHub REST API, sends it to OpenAI gpt-4o-mini,
and posts the analysis as a PR comment.

Environment variables (set by the workflow):
  OPENAI_API_KEY  — OpenAI secret
  GITHUB_TOKEN    — GitHub Actions built-in token (write: pull-requests)
  PR_NUMBER       — Pull request number
  REPO            — "owner/repo" string
  HEAD_SHA        — Head commit SHA (for logging)
  BASE_SHA        — Base commit SHA (for diff fallback)

Usage:
  python scripts/ai_code_review.py
"""
import os
import sys
import json
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
PR_NUMBER      = os.environ.get("PR_NUMBER", "")
REPO           = os.environ.get("REPO", "")

if not OPENAI_API_KEY:
    print("ERROR: OPENAI_API_KEY not set — skipping AI review.", file=sys.stderr)
    sys.exit(0)  # Exit 0 so the workflow step doesn't fail the build

if not all([GITHUB_TOKEN, PR_NUMBER, REPO]):
    print("ERROR: Missing required env vars (GITHUB_TOKEN / PR_NUMBER / REPO).", file=sys.stderr)
    sys.exit(1)

GITHUB_API = "https://api.github.com"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def github_request(path: str, method: str = "GET", data: dict | None = None) -> dict | str:
    """Make an authenticated GitHub API request."""
    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "json" in content_type:
                return json.loads(raw)
            return raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode()}", file=sys.stderr)
        raise


def get_pr_diff() -> str:
    """Fetch the unified diff of the pull request."""
    url = f"{GITHUB_API}/repos/{REPO}/pulls/{PR_NUMBER}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.diff",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode(errors="replace")


def openai_review(diff: str) -> str:
    """Send the diff to OpenAI and return the review text."""
    import urllib.request as req_lib

    MAX_DIFF_CHARS = 12_000
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[... diff truncated for token limit ...]"

    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer reviewing a pull request. "
                    "Analyze the diff below and provide concise, actionable feedback. "
                    "Focus on: correctness, security issues, performance, test coverage, "
                    "and adherence to best practices. "
                    "Be direct. Use bullet points. Skip trivial style comments. "
                    "Start your response with a one-line overall verdict "
                    "(e.g., '✅ Looks good' or '⚠️ Minor issues' or '🚨 Needs changes')."
                ),
            },
            {
                "role": "user",
                "content": f"Review this pull request diff:\n\n```diff\n{diff}\n```",
            },
        ],
    }

    data = json.dumps(payload).encode()
    request = req_lib.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with req_lib.urlopen(request) as resp:
        result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"].strip()


def post_pr_comment(body: str) -> None:
    """Post a comment on the pull request."""
    github_request(
        f"/repos/{REPO}/issues/{PR_NUMBER}/comments",
        method="POST",
        data={"body": body},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Fetching diff for PR #{PR_NUMBER} in {REPO}…")
    diff = get_pr_diff()
    if not diff.strip():
        print("No diff found — skipping review.")
        return

    print(f"Sending {len(diff)} chars of diff to OpenAI…")
    review = openai_review(diff)

    comment = (
        "## 🤖 AI Code Review\n\n"
        f"{review}\n\n"
        "---\n"
        "*Generated by [AI Code Review](/.github/workflows/code-review.yml) "
        "using OpenAI gpt-4o-mini*"
    )

    print("Posting review comment…")
    post_pr_comment(comment)
    print("Done.")


if __name__ == "__main__":
    main()

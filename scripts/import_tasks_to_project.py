#!/usr/bin/env python3
"""Import tasks from YAML into GitHub Project (classic)."""
import os
import sys
import yaml
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO")  # e.g. "org/repo"
COLUMN_ID = os.getenv("GITHUB_COLUMN_ID")  # project column id

if not all([GITHUB_TOKEN, REPO, COLUMN_ID]):
    print("Environment variables GITHUB_TOKEN, GITHUB_REPO, GITHUB_COLUMN_ID are required")
    sys.exit(1)

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <tasks.yml>")
    sys.exit(1)

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

tasks = data.get("tasks", [])

for task in tasks:
    title = f"{task['id']} - {task['title']}"
    body = (
        f"**Owner**: {task['owner']}\n"
        f"**Effort**: {task['effort']}\n"
        f"**Depends**: {task.get('depends', '')}\n"
        f"**Acceptance Criteria**: {task['acceptance']}"
    )

    # create issue
    issue_url = f"https://api.github.com/repos/{REPO}/issues"
    issue_resp = requests.post(issue_url, headers=headers, json={"title": title, "body": body})
    issue_resp.raise_for_status()
    issue_number = issue_resp.json()["number"]

    # add issue to project column
    card_url = f"https://api.github.com/projects/columns/{COLUMN_ID}/cards"
    card_resp = requests.post(card_url, headers=headers, json={"content_id": issue_number, "content_type": "Issue"})
    card_resp.raise_for_status()

    print(f"Created issue #{issue_number} and added to project column {COLUMN_ID}")

#!/usr/bin/env python3
"""Collect the issue plan for the Ondos repository.

Reads every module issue ("[A] ..." to "[E] ..."), its assignees, its
"blocked by" links and the pull requests that close it, with one paged GraphQL
query. Writes one JSON file used by dashboard/plan.html.

Needs GITHUB_TOKEN and GITHUB_REPOSITORY. Only the Python standard library is used.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

from collect_stats import People

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = re.compile(r"^\[([A-E])\]\s*(.+)$")
TEST = re.compile(r"^Test\s+(?=[A-E]-T\d+)")
QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $after, states: [OPEN, CLOSED]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title state closedAt
        assignees(first: 10) { nodes { login } }
        blockedBy(first: 50) { nodes { number } }
        closedByPullRequestsReferences(first: 10, includeClosedPrs: true) {
          nodes { number state isDraft }
        }
      }
    }
  }
}
"""


def graphql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ondos-issue-plan",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if out.get("errors"):
        raise RuntimeError(f"GraphQL errors: {out['errors']}")
    return out["data"]


def fetch_issues(repo, token):
    owner, name = repo.split("/", 1)
    nodes, after = [], None
    while True:
        page = graphql(token, QUERY, {"owner": owner, "name": name, "after": after})["repository"]["issues"]
        nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return nodes
        after = page["pageInfo"]["endCursor"]


def status_of(node):
    """One status per issue, from the issue state and the pull requests that close it."""
    prs = node["closedByPullRequestsReferences"]["nodes"]
    merged = any(p["state"] == "MERGED" for p in prs)
    if node["state"] == "CLOSED":
        return "merged" if merged else "closed"
    if merged:
        return "pr_merged_issue_open"
    open_prs = [p for p in prs if p["state"] == "OPEN"]
    if any(not p["isDraft"] for p in open_prs):
        return "pr_open"
    if open_prs:
        return "pr_draft"
    return "no_pr"


def build_plan(nodes, people):
    """Keep module issues only and turn them into the page's issue and edge lists."""
    issues, kept = [], set()
    for node in nodes:
        m = TITLE.match(node["title"])
        if not m:
            continue  # decisions (D1-D14) and anything without a module prefix
        module, title = m.groups()
        issues.append({
            "n": node["number"],
            "m": module,
            "t": TEST.sub("", title),
            "x": bool(TEST.match(title)),
            "a": [people.short(a["login"]) for a in node["assignees"]["nodes"]],
            "s": status_of(node),
            "prs": [{"n": p["number"], "s": p["state"].lower(), "d": p["isDraft"]}
                    for p in node["closedByPullRequestsReferences"]["nodes"]],
            "closed": node["closedAt"],
        })
        kept.add(node["number"])
    edges = sorted([b["number"], node["number"]]
                   for node in nodes if node["number"] in kept
                   for b in node["blockedBy"]["nodes"] if b["number"] in kept)
    issues.sort(key=lambda i: i["n"])
    return {"issues": issues, "edges": edges}


class ShortNames(People):
    """Short display names ("Arif", "Talha T.") from members.json, by GitHub login."""

    def short(self, login):
        for m in self.members:
            if m.get("github", "").lower() == login.lower():
                return m.get("short") or m["name"]
        return "@" + login


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/plan/data.json")
    ap.add_argument("--members", default=os.path.join(HERE, "members.json"))
    args = ap.parse_args()

    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not (repo and token):
        sys.exit("collect_plan.py needs GITHUB_REPOSITORY and GITHUB_TOKEN")
    with open(args.members, encoding="utf-8") as f:
        people = ShortNames(json.load(f).get("members", []))

    try:
        nodes = fetch_issues(repo, token)
    except (urllib.error.URLError, RuntimeError) as e:
        sys.exit(f"Could not read issues from GitHub: {e}")

    plan = build_plan(nodes, people)
    plan["repo"] = repo
    plan["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(plan['issues'])} issues, {len(plan['edges'])} links -> {args.out}")


if __name__ == "__main__":
    main()

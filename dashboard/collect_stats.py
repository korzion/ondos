#!/usr/bin/env python3
"""Collect team statistics for the Ondos repository.

Reads the local git history (run inside a full clone, fetch-depth: 0) and,
when GITHUB_TOKEN and GITHUB_REPOSITORY are set, the GitHub API for pull
requests, reviews and issues. Writes one JSON file used by dashboard/index.html.

Only the Python standard library is used.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# Top-level folder -> module name shown on the page.
MODULES = {
    "platform": "A · Tilting Platform",
    "glove": "B · Glove",
    "vision": "C · Vision System",
    "simulator": "D · Simulator & 3D Twin",
    "path-planning-control": "E · Path Planning & Control",
    "ai": "F · AI",
    "control-station": "G · Control Station",
    "shared": "Shared",
    "docs": "Docs",
}
OTHER = "Other"


def module_of(path):
    top = path.split("/", 1)[0] if "/" in path else ""
    return MODULES.get(top, OTHER)


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


# --------------------------------------------------------------------------- people
class People:
    """Maps git emails / names / GitHub logins to one display name per person."""

    def __init__(self, members):
        self.by_key = {}
        self.members = members
        for m in members:
            name = m["name"]
            for key in [m.get("github", "")] + m.get("emails", []) + m.get("aliases", []):
                if key:
                    self.by_key[key.strip().lower()] = name

    def resolve(self, login=None, email=None, name=None):
        for key in (login, email, name):
            if key and key.strip().lower() in self.by_key:
                return self.by_key[key.strip().lower()]
        if login:
            return "@" + login
        return name or email or "unknown"

    def login_of(self, display):
        for m in self.members:
            if m["name"] == display and m.get("github"):
                return m["github"]
        return display[1:] if display.startswith("@") else ""


# --------------------------------------------------------------------------- GitHub API
class GitHub:
    def __init__(self, repo, token):
        self.repo, self.token = repo, token

    @property
    def enabled(self):
        return bool(self.repo and self.token)

    def get(self, path, params=None):
        url = f"https://api.github.com/repos/{self.repo}{path}"
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ondos-team-stats",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def paged(self, path, params=None, limit=5000):
        params = dict(params or {})
        params["per_page"] = 100
        out, page = [], 1
        while len(out) < limit:
            params["page"] = page
            batch = self.get(path, params)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out


# --------------------------------------------------------------------------- git log
COMMIT_SEP, FIELD_SEP = "\x1e", "\x1f"
CO_AUTHOR = re.compile(r"^Co-authored-by:\s*(.+?)\s*<([^>]+)>\s*$", re.I | re.M)


def read_git_log():
    fmt = FIELD_SEP.join(["%H", "%an", "%ae", "%aI", "%P", "%s", "%b"])
    raw = run("git", "log", "--numstat", "--no-renames", f"--format={COMMIT_SEP}{fmt}{FIELD_SEP}")
    commits = []
    for chunk in raw.split(COMMIT_SEP)[1:]:
        parts = chunk.split(FIELD_SEP)
        sha, an, ae, date, parents, subject, body = parts[:7]
        numstat = parts[7] if len(parts) > 7 else ""
        files = []
        for line in numstat.strip().splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            add, dele, path = cols
            add = int(add) if add.isdigit() else 0   # binary files show "-"
            dele = int(dele) if dele.isdigit() else 0
            files.append((path, add, dele))
        commits.append({
            "sha": sha, "author_name": an, "author_email": ae, "date": date,
            "merge": len(parents.split()) > 1, "subject": subject,
            "co_authors": CO_AUTHOR.findall(body), "files": files,
        })
    return commits


def week_start(iso):
    d = dt.datetime.fromisoformat(iso).date()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data/stats.json")
    ap.add_argument("--members", default=os.path.join(HERE, "members.json"))
    args = ap.parse_args()

    members = []
    if os.path.exists(args.members):
        with open(args.members, encoding="utf-8") as f:
            members = json.load(f).get("members", [])
    people = People(members)
    gh = GitHub(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""))

    commits = read_git_log()

    # Link commits to GitHub accounts (covers emails the member list does not know).
    sha_login, sha_co = {}, {}
    if gh.enabled:
        try:
            for c in gh.paged("/commits", limit=10000):
                if c.get("author") and c["author"].get("login"):
                    sha_login[c["sha"]] = c["author"]["login"]
        except urllib.error.URLError as e:
            print("warning: could not read commits from the API:", e, file=sys.stderr)

    person = defaultdict(lambda: {
        "commits": 0, "coauthored": 0, "additions": 0, "deletions": 0, "files": 0,
        "active_days": set(), "first": None, "last": None,
        "prs_opened": 0, "prs_merged": 0, "reviews": 0, "issues_opened": 0, "issues_closed": 0,
    })
    module_lines = defaultdict(lambda: defaultdict(int))     # person -> module -> lines changed
    module_totals = defaultdict(lambda: {"commits": 0, "lines": 0, "people": set()})
    weekly = defaultdict(lambda: defaultdict(int))            # week -> person -> commits
    recent = []

    for c in commits:
        if c["merge"]:
            continue
        who = people.resolve(sha_login.get(c["sha"]), c["author_email"], c["author_name"])
        p = person[who]
        p["commits"] += 1
        day = c["date"][:10]
        p["active_days"].add(day)
        p["first"] = min(p["first"] or c["date"], c["date"])
        p["last"] = max(p["last"] or c["date"], c["date"])
        weekly[week_start(c["date"])][who] += 1
        touched = set()
        for path, add, dele in c["files"]:
            if path.startswith(".github/") or path.startswith("dashboard/"):
                continue  # tooling for this page is not project work
            p["additions"] += add
            p["deletions"] += dele
            p["files"] += 1
            mod = module_of(path)
            module_lines[who][mod] += add + dele
            module_totals[mod]["lines"] += add + dele
            module_totals[mod]["people"].add(who)
            touched.add(mod)
        for mod in touched:
            module_totals[mod]["commits"] += 1
        for co_name, co_email in c["co_authors"]:
            co = people.resolve(None, co_email, co_name)
            if co != who:
                person[co]["coauthored"] += 1
                person[co]["active_days"].add(day)
        if len(recent) < 40:
            recent.append({"sha": c["sha"][:7], "who": who, "date": c["date"],
                           "subject": c["subject"][:120], "modules": sorted(touched)})

    prs_summary = {"open": 0, "merged": 0, "closed": 0}
    issues_summary = {"open": 0, "closed": 0}
    if gh.enabled:
        try:
            for pr in gh.paged("/pulls", {"state": "all"}):
                who = people.resolve(pr["user"]["login"])
                person[who]["prs_opened"] += 1
                if pr.get("merged_at"):
                    person[who]["prs_merged"] += 1
                    prs_summary["merged"] += 1
                elif pr["state"] == "open":
                    prs_summary["open"] += 1
                else:
                    prs_summary["closed"] += 1
                for rv in gh.paged(f"/pulls/{pr['number']}/reviews", limit=300):
                    if rv.get("user") and rv["user"]["login"] != pr["user"]["login"]:
                        person[people.resolve(rv["user"]["login"])]["reviews"] += 1
            for issue in gh.paged("/issues", {"state": "all"}):
                if "pull_request" in issue:
                    continue
                person[people.resolve(issue["user"]["login"])]["issues_opened"] += 1
                issues_summary[issue["state"]] += 1
                if issue["state"] == "closed":
                    for a in issue.get("assignees") or []:
                        person[people.resolve(a["login"])]["issues_closed"] += 1
        except urllib.error.URLError as e:
            print("warning: could not read pull requests or issues:", e, file=sys.stderr)

    # Members with no activity yet still appear in the table.
    for m in members:
        person[m["name"]]

    module_names = [m for m in list(MODULES.values()) + [OTHER] if m in module_totals]
    out = {
        "repo": gh.repo or os.path.basename(os.getcwd()),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "api_used": gh.enabled,
        "totals": {
            "commits": sum(v["commits"] for v in person.values()),
            "additions": sum(v["additions"] for v in person.values()),
            "deletions": sum(v["deletions"] for v in person.values()),
            "contributors": sum(1 for v in person.values() if v["commits"] or v["coauthored"]),
            "prs": prs_summary, "issues": issues_summary,
            "first_commit": min((c["date"] for c in commits), default=None),
            "last_commit": max((c["date"] for c in commits), default=None),
        },
        "people": [
            {
                "name": name, "login": people.login_of(name),
                **{k: v for k, v in d.items() if k not in ("active_days",)},
                "active_days": len(d["active_days"]),
                "modules": dict(module_lines[name]),
            }
            for name, d in sorted(person.items(), key=lambda kv: (-kv[1]["commits"], kv[0]))
        ],
        "modules": [
            {"name": m, "commits": module_totals[m]["commits"], "lines": module_totals[m]["lines"],
             "people": len(module_totals[m]["people"])}
            for m in module_names
        ],
        "weekly": [{"week": w, "by_person": dict(weekly[w])} for w in sorted(weekly)],
        "recent": recent,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {out['totals']['commits']} commits, {len(out['people'])} people")


if __name__ == "__main__":
    main()

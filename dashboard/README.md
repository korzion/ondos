# Team activity page

This folder builds the team activity page published at
`https://korzion.github.io/ondos/`.

- `collect_stats.py` reads the git history and the GitHub API and writes `stats.json`.
- `index.html` is the page that shows the statistics.
- `members.json` maps each member's GitHub username and emails to their full name and short name.
- `collect_plan.py` reads the module issues, their "blocked by" links and the pull requests that close them, and writes `plan/data.json`.
- `plan.html` is the issue plan page (`https://korzion.github.io/ondos/plan/`, design by Yağmur Gül): the dependency map with the state of each issue and pull request.
- `.github/workflows/team-stats.yml` runs everything on every push to `main`, when an issue or pull request changes, every hour, and on demand.

Lines changed in each top-level folder are counted for that module
(`platform/`, `glove/`, `vision/`, `simulator/`, `path-planning/`, `ai/`, `control-station/`, `shared/`, `docs/`).
Changes to `dashboard/` and `.github/` are not counted.

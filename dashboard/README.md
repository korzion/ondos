# Team activity page

This folder builds the team activity page published at
`https://korzion.github.io/ondos/`.

- `collect_stats.py` reads the git history and the GitHub API and writes `stats.json`.
- `index.html` is the page that shows the statistics.
- `members.json` maps each member's GitHub username and emails to their full name.
- `.github/workflows/team-stats.yml` runs everything on every push to `main`, every night, and on demand.

Lines changed in each top-level folder are counted for that module
(`platform/`, `glove/`, `vision/`, `simulator/`, `path-planning/`, `ai/`, `control-station/`, `shared/`, `docs/`).
Changes to `dashboard/` and `.github/` are not counted.

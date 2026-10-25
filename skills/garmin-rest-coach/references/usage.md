# Local usage

Python 3.12+ is required. Windows also needs `tzdata` (`python -m pip install tzdata`).
Use a project virtual environment if one exists; otherwise the user's configured Python.
`TOOL` below is the absolute path to this skill's `scripts/rest.py`.
`CONFIG` is the user's config path, kept outside the installed skill and source checkout when possible.

```text
python TOOL --config CONFIG init
python TOOL --config CONFIG profile
python TOOL --config CONFIG setup
python TOOL --config CONFIG schedule-plan
python TOOL --config CONFIG doctor
python TOOL --config CONFIG login
python TOOL --config CONFIG sync --days 42
python TOOL --config CONFIG run --kind morning
python TOOL --config CONFIG run --kind weekly
python TOOL --config CONFIG report --kind morning --as-of 2026-10-25
python TOOL demo --output AN_EMPTY_LOCAL_FOLDER
```

All options before the command apply globally. Dates are YYYY-MM-DD. With no `--as-of`, the configured
timezone determines today. Morning `--as-of 2026-10-25` means sleep ending Oct 25 plus daytime Oct 24.
Weekly `--as-of 2026-10-26` covers Oct 19–25. On a Sunday it covers the week before the current one.

Website login: follow [browser.md](browser.md). Initialize with `init --source browser --region cn`,
read `connection-plan`, open its URL with Codex's available browser tool, let the user sign in, then
verify and import selected dated measurements using `import-browser FILE` before `report`.
This mode does not use CLI `login`, `sync` or `run`. A plain CLI schedule cannot collect website data.

China accounts: `source="community"`, `region="cn"`; install `garminconnect==0.3.20` into the SAME Python
environment used to run the tool. The user performs interactive login. Saved refresh tokens are local
credentials; no password is stored by the report tool. A browser login in Codex is not the CLI session.
This dependency uses unofficial endpoints and may break; no live China login is claimed by the release.

Global accounts can use `source="personal"`, `region="global"`; install
`garmin-connect-personal-api-python`. The user creates their own Personal API key at Garmin Connect,
accepts Garmin's terms personally, and supplies `GARMIN_PERSONAL_API_KEY` locally. This version deliberately
does not invent a China Personal API endpoint. Official SDK access is for each user's own data.

The source repository's `[community]` / `[personal]` extras install these dependencies when the project is
available; the portable skill needs the same optional packages installed separately.

Reports are under configured `report_dir/<kind>-<as-of>/`:
- `evidence.json`: allowlisted numeric facts, metric coverage, preceding baseline and limitations.
- `report.md`, `report.html`: editable deterministic report, no external resources.
- `agent-prompt.md`: analysis instructions plus the evidence, for the active Codex agent.
- `generation.json`: generation time and whether the optional Codex CLI narrative was added.

On missing sleep, refresh after the watch has synced; don't fabricate a report from the last available
night. Without sufficient baseline, summarize measurements and suggest continued recording.

Unattended use: `run --kind morning --codex` or `run --kind weekly --codex` starts the user's installed,
already-authenticated Codex CLI. Its configured model and billing apply; do not add this flag from inside
an existing Codex interpretation. The wrapper sends only evidence via stdin in an isolated working folder,
uses a read-only sandbox, does not bypass approvals, and preserves the base report if Codex fails.
The command produces separate `agent-report.md` and `agent-report.html`. Scheduled execution additionally
needs a system scheduler or a supported Codex automation; installing the skill alone does not schedule it.
The Windows Task Scheduler installer is in the source repository (`scripts/install_schedule.ps1`),
not the portable skill ZIP; use a supported Codex automation directly or obtain the source project for it.

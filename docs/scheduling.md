# Scheduling

The repository does not register jobs or contact anyone on install.
First complete interactive login, run one live sync/report and verify that your timezone and report date
match your account. Make sure the watch has synchronized before the report runs.

For `source="browser"`, use only a Codex automation that actually has browser access. Each run must
follow the skill's browser read/import/report workflow and verify the selected record dates. A browser
session in this chat is not proof of access in the scheduler. Without that capability, offer manual
reports or an explicitly chosen SDK connection. The Windows installer refuses browser collection.

## Windows

For community/personal sources, use `scripts/install_schedule.ps1`. Without `-Install` it prints commands only. The current user runs
the task without elevation or a stored Windows password; the user must be logged in. Task names include
a config-path digest to avoid sharing one task between different profiles. The saved preferences choose
which jobs exist and their times; manual-only preferences produce no jobs. Existing tasks are not
overwritten unless the user explicitly runs `-Install -UpdateExisting`. That option updates only matching
project-specific tasks and cancels matching obsolete daily/weekly tasks. Preference changes alone do not
update an installed task. Review the preview and actual scheduler state before claiming a change is active.

Times are interpreted in the Windows local timezone; report windows use the configuration IANA timezone.
They should match. If they do not, choose appropriate trigger times explicitly.
The scheduled Python must have this package and the chosen Garmin source installed. Prefer an absolute
virtualenv interpreter path. By default, no AI HTTP request occurs. `-UseCodex` adds `--codex`, which invokes the user's existing Codex CLI login and model configuration.
It consumes that configuration's quota/cost. Make sure the scheduled environment can resolve `codex_command`.

Late runs generate a report for the date when they actually execute. The task does not backfill every
missed morning. Neither a sleeping computer nor an expired Garmin session guarantees unattended success.
Inspect Task Scheduler history/last result and the generated report timestamp.

## macOS / Linux

Use the system scheduler you already operate, with **absolute paths**. For example, cron entries after
substituting actual paths:

```cron
30 7 * * * /absolute/project/.venv/bin/python -m garmin_rest_agent --config /absolute/private/config.toml run --kind morning >> /absolute/private/morning.log 2>&1
0 8 * * 1 /absolute/project/.venv/bin/python -m garmin_rest_agent --config /absolute/private/config.toml run --kind weekly >> /absolute/private/weekly.log 2>&1
```

Create the private log directory yourself. Scheduler environment and timezone can differ from your
interactive shell; verify them. Do not place secrets directly into cron command lines.
The exclusive `.run.lock` prevents overlapping jobs. After a hard crash, verify no job is active before
manually removing a stale lock file. No automatic lock-breaking or unbounded retries are performed.

## Agent scheduler

If Codex provides a supported schedule feature, its job can invoke the skill to run the
same CLI and interpret the resulting evidence. Use the host's actual supported schedule interface;
this project does not assume a common scheduler API. Do not start a nested `--codex` run from an active Codex automation: interpret the evidence in that run.
Other agent integrations are deferred until a future version.

## Delivery

Reports stay local. Email, WeChat, push and public hosting are not implemented in v0.1.
Adding delivery later requires separate destination-specific authorization and a configurable transport;
do not upload complete data directories or expose a local report folder as a public website by default.

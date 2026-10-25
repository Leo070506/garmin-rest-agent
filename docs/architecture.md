# v0.1 architecture / Codex first

Garmin website (Codex reads visible content) or SDK -> allowlisted daily cache -> deterministic analysis
-> evidence + base reports -> Codex interpretation.

`browser.py` owns visible-measurement import and official login links; it neither opens a browser nor
extracts browser credentials. The skill uses the host's browser tool for login/navigation and date checks.
`sources.py` owns SDK transport, `normalize.py` owns field mapping/privacy, `analysis.py` owns dates/statistics,
`report.py` owns output, `codex.py` optionally invokes an existing Codex CLI. The portable skill copies
the same Python core at release; do not maintain separate arithmetic in prompts.

Scope: local personal use, morning and previous-complete-week reports, Codex app skill and optional CLI.
No hosted login server, plan modification, mail/social delivery, generic model routing or multi-tenancy.
DeepSeek and WorkBuddy are deferred. Standardized JSON import is supported; arbitrary Garmin ZIP/CSV is not.

Validation layers: offline arithmetic/date/missingness/privacy/cache/locking tests; installed SDK interface
inspection and transport substitutes; synthetic end-to-end CLI/skill tests; visual report inspection.
These do not certify live China/global authentication, full website-login-to-report behavior or a paid
Codex CLI run. No credentials are bundled. Browser-mode scheduling needs browser tools in the scheduled
agent itself; raw CLI schedules reject this collection mode.
The optional Codex narrative is not independently fact-checked. Keep its source evidence and base report.

Sources checked 2026-10-25:
- https://developer.garmin.com/gc-developer-program/personal/personal-api/
- https://developer.garmin.com/gc-developer-program/personal/personal-faq/
- https://github.com/garmin/connect-personal-api-python (Apache-2.0 dependency)
- https://github.com/cyberjunky/python-garminconnect (MIT dependency)
- https://learn.chatgpt.com/docs/non-interactive-mode

Libraries are dependencies, not copied upstream implementations. Their licenses and service terms apply.

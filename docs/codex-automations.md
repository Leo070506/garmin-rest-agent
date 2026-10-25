# Codex automation prompts

These are reviewable prompts, not installed schedules. Replace CONFIG and TOOL with absolute local paths.
Use the user's saved frequency, time, weekday and timezone when enabling the actual automation; the headings
below are examples. Use the Codex app's supported automation UI/tool. Nothing is registered by this file.
The computer must be available and Garmin authenticated; model limits still apply.

## Morning: daily 07:30 local time

Use $garmin-rest-coach to generate my morning recovery report. For a browser source, follow the skill's
browser reference to read/import visible dated measurements, then run `python TOOL --config CONFIG report --kind morning`.
For an SDK source, run `python TOOL --config CONFIG run --kind morning` without --codex.
Then read the generated evidence.json. Analyze last night's sleep under its wake date and
yesterday's daytime activity separately. Follow the saved topics, goal and report detail in evidence.preferences;
do not expand unselected topics. Give a Chinese report with observations, comparisons against
sufficient personal baseline, practical suggestions and gaps. Save agent-report.md beside the base report.
Keep evidence.json and report.md unchanged. Don't read credentials, create a second model invocation or send
messages. On login/rate-limit failure stop and notify me; don't present old data as freshly synced.

## Weekly: Monday 08:00 local time

Use $garmin-rest-coach to produce my report for the previous completed Monday–Sunday. For a browser source,
follow the browser reference to read/import the selected week, then run `python TOOL --config CONFIG report --kind weekly`.
For an SDK source, run `python TOOL --config CONFIG run --kind weekly` without --codex.
Read evidence.json and interpret only the saved topics, following
the goal and detail in evidence.preferences, with per-metric coverage. Save agent-report.md beside the base report. Don't call
unknown days rest days, compare training load when only duration is known, invent scores, modify training
plans or send messages. Stop and notify me if data retrieval fails.

The skill uses the current agent for interpretation; a raw system-scheduler command needs --codex to obtain
an AI narrative. These are alternative execution paths, not steps to combine.

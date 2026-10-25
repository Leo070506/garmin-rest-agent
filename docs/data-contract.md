# Data contract v1

One record is stored per **local calendar date**, at `data/<region>/YYYY-MM-DD.json`.
`date` is the wake date for sleep; the same date's activities and daily health summary belong to that day.
The timezone must match the Garmin account. Morning reports deliberately use two different records:
sleep from the report date, activity context from the previous date.

Only allowlisted normalized fields are persisted:

```json
{
  "schema_version": 1,
  "date": "2026-10-25",
  "source": "community:cn",
  "is_demo": false,
  "fetched_at": "2026-10-25T00:00:00+00:00",
  "status": {"sleep": "ok", "stats": "ok", "hrv": "unavailable", "activities": "ok"},
  "sleep": {"hours": 7.8, "score": 84, "start": "2026-10-24T23:20:00+08:00", "end": "2026-10-25T07:20:00+08:00", "deep_minutes": 70, "rem_minutes": 100},
  "resting_hr": 50,
  "hrv_ms": null,
  "stress_mean": 25,
  "steps": 9000,
  "body_battery": {"max": 90, "min": 20, "charged": 60, "drained": 70},
  "activities": [{"type": "running", "duration_min": 35, "distance_km": 5.0, "average_hr": 140}],
  "warnings": []
}
```

The example illustrates shape; sleep duration can exclude awake time and need not equal end minus start.
Missing or invalid numbers are `null`; stress `0` remains valid. `hrv_ms` is nightly average, not weekly HRV.
Sleep duration `0` is treated as unavailable rather than a real zero-hour night. Stale sleep whose known
wake date differs from the requested day is excluded.

`status.activities="ok"` with an empty list means no **recorded** activities. Missing/unsupported query is
unknown. All seven days and every activity duration must be known before week-over-week time comparison.
Duration and distance describe the activities retrieved, not physiological training load.

Sleep-score fields and HRV fields follow the currently inspected SDK responses. A changed schema yields
missing fields; it must not be “fixed” by choosing unrelated similar-looking values.
Source adapters are intentionally read-only and do not call training-plan or activity write endpoints.

Collection follows the selected topics in the local profile. A narrow-topic sync retains previously
cached fields for unselected topics; it does not refresh them. `collected_topics` and
`collection_at_by_topic` record which topics have been queried and when. `fetched_at` describes the
latest partial collection, not freshness of every retained field. Reports include only selected topics.
Changing preferences alone does not modify health history or install/update scheduled tasks.

## Website-visible import

`source="browser"` uses `import-browser` with the schema and date/unit rules in
[the browser reference](../skills/garmin-rest-coach/references/browser.md). Input requires the correct
regional official page origin, an explicitly confirmed record date and the selected topics. Only numeric
allowlisted measurements and generic activity types enter the cache; URLs, page text and identities do not.
This validates the packet, not browser authentication or transcription accuracy. Evidence marks the browser
source and includes that limitation. Multiple different-topic pages for the same date merge into one day.

## Offline/raw JSON import

`import-json file.json` accepts this explicit wrapper, **not arbitrary Garmin export ZIP/CSV**:

```json
{
  "days": [{
    "date": "2026-10-25",
    "payload": {
      "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 28800, "sleepScores": {"overall": {"value": 85}}}},
      "stats": {"restingHeartRate": 50, "averageStressLevel": 25, "totalSteps": 9000},
      "hrv": {"hrvSummary": {"lastNightAvg": 60}},
      "activities": []
    }
  }]
}
```

A field absent from payload is marked missing. Each present field should be the response for the given
date from its corresponding adapter call. The importer applies the same identity/GPS stripping as live
collection. It does not validate the authenticity of imported measurements. Export JSON is never trusted
as model instructions. Importing replaces the normalized file for that date; live sync merges selected
topics into it. Retain a separate backup if you need version history.

## Evidence packet

Reports include statistics and numeric series, not identifiers or raw records. Each metric carries
`n`, with explicit expected coverage; baselines include their date range and sample minimum.
For a weekly report, the baseline ends the day before the week's start. A valid report may have no
baseline and should then describe measurements without claiming personal improvement or deterioration.

The observer flags (+5 bpm RHR, -15% HRV versus the prior median) are transparent product heuristics,
not validated clinical cutoffs or a trained recovery model. Users should interpret them with context.
Bedtime variation uses circular time so midnight crossings are handled; it is an average absolute
deviation in minutes, not a sleep regularity index validated for medical use.

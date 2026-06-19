# Hungary Watch Interview Example

This directory is a curated example from a full 10,000-respondent synthetic interview run.

The full generated JSONL files are not committed to git. They can be reproduced locally with:

```powershell
python scripts\run_hungary_watch_scenario.py
```

## Included

| File | Meaning |
|---|---|
| `readable_report.md` | Human-readable scenario report |
| `market_choice_summary.json` | Weighted shares and confidence intervals |
| `segment_lift_table.json` | Segment over/under-indexing |
| `sensitivity_report.json` | Price-grid sensitivity results |
| `audit_report.json` | Source, calibration, and limitation notes |
| `choice_interview_validation.json` | Validation summary from the full run |
| `samples/*.jsonl` | Small row samples for inspection and tests |

## Not Included

The full 10,000-row `personas_core.jsonl`, `choice_results.jsonl`, and narrative JSONL files stay under local `runs/` and are ignored by git.

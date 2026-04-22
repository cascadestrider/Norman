# Norman

Norman is an AI-driven ad-intelligence pipeline for Torque Optics. It
continuously surfaces first-person customer pain-point content across the web
(Reddit, Google, Bing, YouTube, and others), scores it for relevance,
classifies it, and hands the highest-signal leads to an analyst agent that
generates segment-specific ad copy. The output is delivered to a Discord
channel and a Markdown report each run.

## Architecture

Scouts (`norman/scouts/`) run in parallel, each returning `Lead` objects for
URLs above the score threshold. Scores come from `norman/scoring_v2.py`, which
uses Voyage embeddings against curated exemplars. A source-type classifier
(`norman/classifier.py`, Claude Haiku) tags each lead as `customer_voice`,
`retailer`, `editorial_roundup`, or `unknown`. Only customer-voice leads reach
the analyst (`norman/analyst.py`, Claude Sonnet), which classifies by
segment and generates ad copy using segment-specific positioning. Delivery
(`norman/delivery.py`) posts to Discord with rate-limit backoff and writes a
Markdown report to `reports/`. All leads are persisted to SQLite
(`norman/db.py`) with a 14-day revisit window so evolving threads can be
re-scored without indefinite "seen once, dead forever" dedup.

## Running

```
python run.py --once     # single run, exit
python run.py            # run once, then daily at 9 AM via APScheduler
```

## Required environment variables

These must be set (typically via `.env`) for a full run. Missing keys cause
the corresponding scout or agent to no-op with a warning; they do not crash
the pipeline.

- `NORMAN_ANTHROPIC_KEY` — analyst (Claude Sonnet) and classifier (Claude Haiku)
- `VOYAGE_API_KEY` — semantic scoring embeddings
- `USE_SEMANTIC_SCORING` — set to `1` to enable semantic scoring (falls back
  to legacy keyword scoring when unset or `0`)
- `SERP_API_KEY` — Google, Bing, and Amazon scouts (shared SerpAPI quota)
- `YOUTUBE_API_KEY` — YouTube scout
- `DISCORD_WEBHOOK_URL` — Discord delivery

## Segments

The pipeline currently targets five customer segments plus a `general`
catch-all:

- `golf` — ball tracking, reading greens, depth perception
- `fishing` — water glare, sight fishing
- `motorcycle` — HUD / GPS / phone-screen compatibility while riding
- `commuter` — daily-driver screen visibility and windshield glare
- `sensitivity` — post-concussion, migraine, photophobia, light-sensitive users

## Per-segment-per-lead analyst behavior

The analyst currently generates one piece of ad copy per (lead × matched
segment) pair. A single URL that keyword-matches both `golf` and `sensitivity`
produces two AnalystLead outputs, one per segment. This is a provisional
design — a future weekly-theme-synthesis layer will change the unit of
analysis to themes, at which point the per-segment-per-lead duplication goes
away. For DB storage, Norman picks the primary segment (by keyword-match
count) and stores only that segment's strategy JSON.

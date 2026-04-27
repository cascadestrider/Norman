#!/usr/bin/env python3
"""Norman v2 — AI Ad Intelligence Pipeline for Torque Optics.

Usage:
    python run.py                # Start scheduler (odd-date daily pipeline + Monday weekly synthesis)
    python run.py --run-now      # Run pipeline once, then start scheduler
    python run.py --once         # Run the daily pipeline once and exit
    python run.py --synthesize   # Run the weekly synthesis once and exit
    python run.py --list-events  # Print the tournament calendar with status markers

--run-now, --once, --synthesize, and --list-events are mutually exclusive.

For persistence across reboots and terminal closes, migrate to launchd.
See docs/launchd-setup.md (future).
"""
import sys
from datetime import date, timedelta

from norman.orchestrator import run_pipeline
from norman.synthesizer import run_weekly_synthesis
from norman.delivery import deliver_synthesis
from norman.config import EVENT_PRE_DAYS, EVENT_POST_DAYS
from norman.events import EVENTS_2026

# Odd calendar dates 1..31 — apscheduler accepts these as a comma-separated
# string on the "day" field of a cron trigger.
_ODD_DAYS = ",".join(str(d) for d in range(1, 32, 2))


def run_synthesis():
    """Run the weekly synthesis pipeline and deliver to markdown + Discord."""
    output = run_weekly_synthesis()
    status = deliver_synthesis(output)

    if output is None:
        print("\n📊 Synthesis: None returned (insufficient data or parse failure)")
    else:
        print(
            f"\n📊 Synthesis complete — week_of {output.week_of}, "
            f"{len(output.themes)} themes, {output.leads_analyzed} leads analyzed"
        )
        if output.sampled_note:
            print(f"  {output.sampled_note}")
    print(f"  Markdown: {status.synthesis_markdown}")
    print(f"  Discord:  {status.synthesis_discord}")


def list_events():
    """Print the tournament calendar with status markers."""
    today = date.today()

    def _format_dates(start, end):
        if start.month == end.month:
            return f"{start.strftime('%b %d')}-{end.strftime('%d')}"
        return f"{start.strftime('%b %d')}-{end.strftime('%b %d')}"

    upcoming = [
        e for e in EVENTS_2026
        if (e.start_date - timedelta(days=EVENT_PRE_DAYS)) > today
    ]
    next_upcoming = min(upcoming, key=lambda e: e.start_date) if upcoming else None

    print("📅 PGA Tournaments — 2026")
    for event in sorted(EVENTS_2026, key=lambda e: e.start_date):
        pre_window_start = event.start_date - timedelta(days=EVENT_PRE_DAYS)
        post_window_end = event.end_date + timedelta(days=EVENT_POST_DAYS)
        if today > post_window_end:
            marker = "✅      "
        elif pre_window_start <= today <= post_window_end:
            marker = "🔴 ACTIVE"
        else:
            marker = "⏳      "
        line = (
            f"  {marker} {event.name:<24} "
            f"{_format_dates(event.start_date, event.end_date):<14} "
            f"{event.venue}"
        )
        if event is next_upcoming:
            line += f" [next: window opens {pre_window_start.strftime('%b %d')}]"
        print(line)


def main():
    argv = set(sys.argv[1:])
    run_now = "--run-now" in argv
    once = "--once" in argv
    synthesize = "--synthesize" in argv
    list_events_flag = "--list-events" in argv

    exclusive = [
        ("--run-now", run_now),
        ("--once", once),
        ("--synthesize", synthesize),
        ("--list-events", list_events_flag),
    ]
    chosen = [name for name, on in exclusive if on]
    if len(chosen) > 1:
        print(
            f"error: {', '.join(chosen)} are mutually exclusive",
            file=sys.stderr,
        )
        sys.exit(1)

    if list_events_flag:
        list_events()
        return

    if once:
        run_pipeline()
        return

    if synthesize:
        run_synthesis()
        return

    if run_now:
        run_pipeline()

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "cron", day=_ODD_DAYS, hour=9, minute=0)
    scheduler.add_job(run_synthesis, "cron", day_of_week="mon", hour=9, minute=15)

    print(
        "\n⏰ Norman scheduled — pipeline on odd calendar dates at 9:00 AM, "
        "synthesis every Monday at 9:15 AM. Keep this terminal open for "
        "the scheduler to run."
    )
    scheduler.start()


if __name__ == "__main__":
    main()

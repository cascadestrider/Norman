#!/usr/bin/env python3
"""Norman v2 — AI Ad Intelligence Pipeline for Torque Optics.

Usage:
    python run.py                # Start scheduler (odd-date daily pipeline + Monday weekly synthesis)
    python run.py --run-now      # Run pipeline once, then start scheduler
    python run.py --once         # Run the daily pipeline once and exit
    python run.py --synthesize   # Run the weekly synthesis once and exit

--run-now is mutually exclusive with --once and --synthesize.

For persistence across reboots and terminal closes, migrate to launchd.
See docs/launchd-setup.md (future).
"""
import sys

from norman.orchestrator import run_pipeline
from norman.synthesizer import run_weekly_synthesis
from norman.delivery import deliver_synthesis

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


def main():
    argv = set(sys.argv[1:])
    run_now = "--run-now" in argv
    once = "--once" in argv
    synthesize = "--synthesize" in argv

    if run_now and once:
        print("error: --run-now and --once are mutually exclusive", file=sys.stderr)
        sys.exit(1)
    if run_now and synthesize:
        print("error: --run-now and --synthesize are mutually exclusive", file=sys.stderr)
        sys.exit(1)

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

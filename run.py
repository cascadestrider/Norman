#!/usr/bin/env python3
"""Norman v2 — AI Ad Intelligence Pipeline for Torque Optics.

Usage:
    python run.py          # Run once then start daily scheduler at 9am
    python run.py --once   # Run once and exit
"""
import sys
from norman.orchestrator import run_pipeline


def main():
    if "--once" in sys.argv:
        run_pipeline()
        return

    # Run immediately, then schedule daily
    run_pipeline()

    from apscheduler.schedulers.blocking import BlockingScheduler
    print("\n⏰ Norman scheduled — next run at 9:00 AM daily")
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "cron", hour=9, minute=0)
    scheduler.start()


if __name__ == "__main__":
    main()

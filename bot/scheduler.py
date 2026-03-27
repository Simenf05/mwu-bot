from __future__ import annotations

import logging
from datetime import datetime

import exchange_calendars as ecals
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from bot.config import load_config_from_env
from bot.run_daily import _session_date_now, run_one_session


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    cfg = load_config_from_env()

    scheduler = BlockingScheduler(timezone=cfg.timezone)

    # Run at 15:45 NY time. The job itself is idempotent and session-aware.
    trigger = CronTrigger(day_of_week="mon-fri", hour=15, minute=45)

    def job():
        session_date = _session_date_now(cfg.exchange_calendar, cfg.timezone)
        run_one_session(cfg, session_date=session_date)

    scheduler.add_job(job, trigger, id="run_daily", replace_existing=True)
    scheduler.start()


if __name__ == "__main__":
    main()


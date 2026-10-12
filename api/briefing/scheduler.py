"""APScheduler-based briefing warmup.

Polls every minute and triggers `warmup_tenant` when current HH:MM matches
each tenant's `briefing_settings.auto_generate_time`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from admin.db import get_sync_db
from admin.models.inbox import BriefingSettings
from admin.models.user import User
from admin.utils import BEIJING_TZ, now_beijing

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
WARMUP_CONCURRENCY = 5


async def warmup_tenant(tenant_id: str, manual: bool = False) -> dict:
    """Generate briefings for all eligible agents under a tenant.

    Returns: {generated: int, skipped: int, failed: int, agents: list[str]}
    """
    from api.routers.briefing import _query_today_messages, _generate_and_save  # avoid circular import

    def _read_settings() -> tuple[BriefingSettings | None, list[str]]:
        with get_sync_db() as db:
            s = db.query(BriefingSettings).filter(BriefingSettings.tenant_id == tenant_id).first()
            scope = (s.auto_generate_scope if s else 'active_7d') if not manual else 'all'
            min_msgs = (s.min_messages_to_generate if s else 1) if not manual else 0
            users_q = db.query(User).filter(User.tenant_id == tenant_id, User.is_active == True)
            if scope == 'active_7d':
                cutoff = now_beijing() - timedelta(days=7)
                users_q = users_q.filter(User.last_login_at != None, User.last_login_at >= cutoff)  # noqa: E711
            elif scope == 'active_30d':
                cutoff = now_beijing() - timedelta(days=30)
                users_q = users_q.filter(User.last_login_at != None, User.last_login_at >= cutoff)  # noqa: E711
            usernames = [u.username for u in users_q.all()]
            return s, usernames, min_msgs

    settings, usernames, min_msgs = await asyncio.to_thread(_read_settings)

    generated = 0
    skipped = 0
    failed = 0
    sem = asyncio.Semaphore(WARMUP_CONCURRENCY)

    async def _do_one(username: str):
        nonlocal generated, skipped, failed
        async with sem:
            try:
                def _read():
                    with get_sync_db() as db:
                        msgs = _query_today_messages(db, tenant_id, username)
                        return msgs
                msgs = await asyncio.to_thread(_read)
                if len(msgs) < (min_msgs or 0):
                    skipped += 1
                    return
                await _generate_and_save(tenant_id, username, msgs)
                generated += 1
            except Exception as e:
                logger.exception(f'warmup_tenant failed for {username}: {e}')
                failed += 1

    await asyncio.gather(*[_do_one(u) for u in usernames])

    summary = {'generated': generated, 'skipped': skipped, 'failed': failed, 'agents_total': len(usernames)}

    def _persist():
        with get_sync_db() as db:
            s = db.query(BriefingSettings).filter(BriefingSettings.tenant_id == tenant_id).first()
            if not s:
                s = BriefingSettings(tenant_id=tenant_id)
                db.add(s)
                db.flush()
            s.last_run_at = now_beijing()
            s.last_run_status = 'success' if failed == 0 else ('partial' if generated > 0 else 'failed')
            s.last_run_summary = summary

    await asyncio.to_thread(_persist)
    return summary


async def _briefing_warmup_job():
    """Per-minute job: scan briefing_settings, run warmup if HH:MM matches."""
    now_hm = now_beijing().strftime('%H:%M')

    def _list_targets() -> list[str]:
        with get_sync_db() as db:
            rows = (
                db.query(BriefingSettings)
                .filter(
                    BriefingSettings.auto_generate_enabled == True,  # noqa: E712
                    BriefingSettings.auto_generate_time == now_hm,
                )
                .all()
            )
            return [r.tenant_id for r in rows]

    try:
        tenant_ids = await asyncio.to_thread(_list_targets)
    except Exception as e:
        logger.warning(f'briefing scheduler list targets failed: {e}')
        return

    if not tenant_ids:
        return

    logger.info(f'briefing warmup tick: {now_hm}, tenants={tenant_ids}')
    for tid in tenant_ids:
        try:
            await warmup_tenant(tid)
        except Exception as e:
            logger.exception(f'briefing warmup tenant {tid} failed: {e}')


def setup_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = AsyncIOScheduler(timezone=BEIJING_TZ)
    sched.add_job(
        _briefing_warmup_job,
        CronTrigger(minute='*'),
        id='briefing_warmup_tick',
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info('Briefing scheduler started (every-minute warmup check)')
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None

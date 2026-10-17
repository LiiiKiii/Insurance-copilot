"""Daily briefing API — inbox ingest, briefing fetch, acknowledge, message read."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from admin.config_bridge import DefaultModelConfigurationError
from admin.db import get_sync_db
from admin.models.inbox import BriefingSettings, DailyBriefing, InboxMessage
from admin.models.user import User
from admin.utils import now_beijing
from api.briefing.compliance import get_compliance_warnings
from api.briefing.llm_generator import generate_briefing

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_CONFIGURATION_UNAVAILABLE = "MODEL_CONFIGURATION_UNAVAILABLE"


# ── Pydantic schemas ─────────────────────────────────────────────────────────


class InboxMessageIn(BaseModel):
    external_id: str
    agent_id: str  # username
    priority: str = Field(..., pattern=r'^P[012]$')
    category: str
    notification_name: str
    receiver_type: str
    trigger_logic: str | None = None
    template_summary: str | None = None
    policy_no: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    product_name: str | None = None
    business_type: str | None = None
    raw_content: str
    classify_reason: str | None = None
    channel: str = 'sms'
    deadline_at: datetime | None = None
    occurred_at: datetime | None = None
    source_system: str | None = None
    extra_metadata: dict | None = None


class IngestRequest(BaseModel):
    messages: list[InboxMessageIn]


class BriefingSettingsIn(BaseModel):
    auto_generate_enabled: bool | None = None
    auto_generate_time: str | None = Field(None, pattern=r'^\d{2}:\d{2}$')
    auto_generate_scope: str | None = Field(None, pattern=r'^(all|active_7d|active_30d)$')
    min_messages_to_generate: int | None = None


class InboxMessageCreateIn(BaseModel):
    target_agent_id: str
    priority: str = Field(..., pattern=r'^P[012]$')
    category: str
    notification_name: str
    receiver_type: str
    raw_content: str
    trigger_logic: str | None = None
    template_summary: str | None = None
    policy_no: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    product_name: str | None = None
    business_type: str | None = None
    classify_reason: str | None = None
    channel: str = 'sms'
    deadline_at: datetime | None = None
    occurred_at: datetime | None = None
    external_id: str | None = None
    source_system: str | None = 'manual'


class InboxMessageUpdateIn(BaseModel):
    priority: str | None = Field(None, pattern=r'^P[012]$')
    category: str | None = None
    notification_name: str | None = None
    receiver_type: str | None = None
    raw_content: str | None = None
    trigger_logic: str | None = None
    template_summary: str | None = None
    policy_no: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    product_name: str | None = None
    business_type: str | None = None
    classify_reason: str | None = None
    channel: str | None = None
    deadline_at: datetime | None = None
    occurred_at: datetime | None = None


# ── helpers ──────────────────────────────────────────────────────────────────


def _resolve_user(db, agent_id: str) -> User:
    user = db.query(User).filter(User.username == agent_id).first()
    if not user:
        raise HTTPException(404, detail=f'agent_id={agent_id} not found')
    return user


def _today_beijing() -> date:
    return now_beijing().date()


def _serialize_message(m: InboxMessage) -> dict:
    return {
        'id': m.id,
        'external_id': m.external_id,
        'priority': m.priority,
        'category': m.category,
        'notification_name': m.notification_name,
        'receiver_type': m.receiver_type,
        'trigger_logic': m.trigger_logic,
        'template_summary': m.template_summary,
        'policy_no': m.policy_no,
        'customer_id': m.customer_id,
        'customer_name': m.customer_name,
        'product_name': m.product_name,
        'business_type': m.business_type,
        'raw_content': m.raw_content,
        'classify_reason': m.classify_reason,
        'channel': m.channel,
        'deadline_at': m.deadline_at.isoformat() if m.deadline_at else None,
        'occurred_at': m.occurred_at.isoformat() if m.occurred_at else None,
        'received_at': m.received_at.isoformat() if m.received_at else None,
        'read_at': m.read_at.isoformat() if m.read_at else None,
        'handled_at': m.handled_at.isoformat() if m.handled_at else None,
        'source_system': m.source_system,
    }


def _serialize_briefing(b: DailyBriefing) -> dict:
    return {
        'date': b.briefing_date.isoformat(),
        'message_count': b.message_count,
        'p0_count': b.p0_count,
        'p1_count': b.p1_count,
        'p2_count': b.p2_count,
        'summary_markdown': b.summary_markdown,
        'action_items': b.action_items or [],
        'model_id': b.model_id,
        'model_display_name': b.model_display_name,
        'generated_at': b.generated_at.isoformat() if b.generated_at else None,
        'acknowledged_at': b.acknowledged_at.isoformat() if b.acknowledged_at else None,
    }


def _query_today_messages(db, tenant_id: str, agent_id: str) -> list[InboxMessage]:
    """Return all messages assigned to an agent without a date filter.

    The proof-of-concept dataset is static. A production integration can add
    an ``occurred_at`` range filter here when daily partitioning is required.
    """
    priority_order = {'P0': 0, 'P1': 1, 'P2': 2}
    rows = (
        db.query(InboxMessage)
        .filter(
            InboxMessage.tenant_id == tenant_id,
            InboxMessage.agent_id == agent_id,
        )
        .all()
    )
    rows.sort(key=lambda m: (priority_order.get(m.priority, 9), -(m.occurred_at.timestamp() if m.occurred_at else 0)))
    return rows


def _is_stale(briefing: DailyBriefing | None, messages: list[InboxMessage]) -> bool:
    if not briefing:
        return True
    if (briefing.message_count or 0) != len(messages):
        return True
    cur_ids = {m.id for m in messages}
    saved_ids = set(briefing.message_ids or [])
    if cur_ids != saved_ids:
        return True
    return False


def _count_priorities(messages: list[InboxMessage]) -> tuple[int, int, int]:
    p0 = sum(1 for m in messages if m.priority == 'P0')
    p1 = sum(1 for m in messages if m.priority == 'P1')
    p2 = sum(1 for m in messages if m.priority == 'P2')
    return p0, p1, p2


async def _generate_and_save(tenant_id: str, agent_id: str, messages: list[InboxMessage]) -> DailyBriefing:
    """Call LLM and upsert daily_briefings.

    Compliance is handled separately via api.briefing.compliance.get_compliance_warnings()
    and returned in the API response payload, not embedded in the briefing markdown.
    """
    payload = [_serialize_message(m) for m in messages]
    try:
        result = await generate_briefing(payload)
    except DefaultModelConfigurationError as exc:
        # Stored credential failures and ambiguous global defaults must be
        # visible as a controlled outage, never converted into a provider-key
        # fallback.  Do not log ``exc``: even exception chains must remain an
        # internal diagnostic channel.
        logger.warning("Briefing model configuration is unavailable.")
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": MODEL_CONFIGURATION_UNAVAILABLE,
                    "message": "Model configuration is unavailable.",
                }
            },
        ) from exc

    today = _today_beijing()
    p0, p1, p2 = _count_priorities(messages)

    def _save() -> DailyBriefing:
        with get_sync_db() as db:
            existing = (
                db.query(DailyBriefing)
                .filter(
                    DailyBriefing.tenant_id == tenant_id,
                    DailyBriefing.agent_id == agent_id,
                    DailyBriefing.briefing_date == today,
                )
                .first()
            )
            if existing:
                existing.message_count = len(messages)
                existing.p0_count = p0
                existing.p1_count = p1
                existing.p2_count = p2
                existing.summary_markdown = result['summary_markdown']
                existing.action_items = result['action_items']
                existing.message_ids = [m.id for m in messages]
                existing.model_id = result.get('model_id')
                existing.model_display_name = result.get('model_display_name')
                existing.generated_at = now_beijing()
                # Regeneration invalidates the previous acknowledgement.
                existing.acknowledged_at = None
                db.flush()
                db.refresh(existing)
                return existing
            new_b = DailyBriefing(
                tenant_id=tenant_id,
                agent_id=agent_id,
                briefing_date=today,
                message_count=len(messages),
                p0_count=p0,
                p1_count=p1,
                p2_count=p2,
                summary_markdown=result['summary_markdown'],
                action_items=result['action_items'],
                message_ids=[m.id for m in messages],
                model_id=result.get('model_id'),
                model_display_name=result.get('model_display_name'),
                generated_at=now_beijing(),
            )
            db.add(new_b)
            db.flush()
            db.refresh(new_b)
            return new_b

    return await asyncio.to_thread(_save)


# ── ingest ───────────────────────────────────────────────────────────────────


@router.post('/api/briefing/inbox/ingest')
async def ingest_inbox(payload: IngestRequest = Body(...)) -> dict:
    if not payload.messages:
        return {'inserted': 0, 'updated': 0, 'skipped': 0}

    def _do() -> dict:
        inserted = 0
        updated = 0
        skipped = 0
        with get_sync_db() as db:
            for item in payload.messages:
                user = db.query(User).filter(User.username == item.agent_id).first()
                if not user:
                    skipped += 1
                    logger.warning(f'ingest skip: agent_id={item.agent_id} not found')
                    continue
                existing = (
                    db.query(InboxMessage)
                    .filter(
                        InboxMessage.tenant_id == user.tenant_id,
                        InboxMessage.external_id == item.external_id,
                    )
                    .first()
                )
                if existing:
                    for field in (
                        'priority', 'category', 'notification_name', 'receiver_type',
                        'trigger_logic', 'template_summary', 'policy_no', 'customer_id',
                        'customer_name', 'product_name', 'business_type', 'raw_content',
                        'classify_reason', 'channel', 'deadline_at', 'source_system', 'extra_metadata',
                    ):
                        setattr(existing, field, getattr(item, field))
                    if item.occurred_at:
                        existing.occurred_at = item.occurred_at
                    updated += 1
                else:
                    new_msg = InboxMessage(
                        id=str(uuid.uuid4()),
                        tenant_id=user.tenant_id,
                        agent_id=item.agent_id,
                        external_id=item.external_id,
                        priority=item.priority,
                        category=item.category,
                        notification_name=item.notification_name,
                        receiver_type=item.receiver_type,
                        trigger_logic=item.trigger_logic,
                        template_summary=item.template_summary,
                        policy_no=item.policy_no,
                        customer_id=item.customer_id,
                        customer_name=item.customer_name,
                        product_name=item.product_name,
                        business_type=item.business_type,
                        raw_content=item.raw_content,
                        classify_reason=item.classify_reason,
                        channel=item.channel,
                        deadline_at=item.deadline_at,
                        occurred_at=item.occurred_at or now_beijing(),
                        received_at=now_beijing(),
                        source_system=item.source_system,
                        extra_metadata=item.extra_metadata,
                    )
                    db.add(new_msg)
                    inserted += 1
        return {'inserted': inserted, 'updated': updated, 'skipped': skipped}

    return await asyncio.to_thread(_do)


# ── briefing fetch ───────────────────────────────────────────────────────────


@router.get('/api/briefing/today/summary')
async def briefing_today_summary(agent_id: str = Query(...)) -> dict:
    """Lightweight: counts only, no LLM call. Includes compliance warnings."""

    def _do() -> dict:
        with get_sync_db() as db:
            user = _resolve_user(db, agent_id)
            messages = _query_today_messages(db, user.tenant_id, agent_id)
            briefing = (
                db.query(DailyBriefing)
                .filter(
                    DailyBriefing.tenant_id == user.tenant_id,
                    DailyBriefing.agent_id == agent_id,
                    DailyBriefing.briefing_date == _today_beijing(),
                )
                .first()
            )
            p0, p1, p2 = _count_priorities(messages)
            return {
                'message_count': len(messages),
                'p0_count': p0,
                'p1_count': p1,
                'p2_count': p2,
                'acknowledged_at': briefing.acknowledged_at.isoformat() if briefing and briefing.acknowledged_at else None,
                'is_stale': _is_stale(briefing, messages),
                'has_briefing': briefing is not None,
            }

    summary = await asyncio.to_thread(_do)
    summary['compliance_warnings'] = await asyncio.to_thread(get_compliance_warnings, agent_id)
    return summary


async def _fetch_today(agent_id: str, force: bool) -> dict:
    def _read():
        with get_sync_db() as db:
            user = _resolve_user(db, agent_id)
            tenant_id = user.tenant_id
            messages = _query_today_messages(db, tenant_id, agent_id)
            briefing = (
                db.query(DailyBriefing)
                .filter(
                    DailyBriefing.tenant_id == tenant_id,
                    DailyBriefing.agent_id == agent_id,
                    DailyBriefing.briefing_date == _today_beijing(),
                )
                .first()
            )
            stale = _is_stale(briefing, messages)
            return tenant_id, messages, briefing, stale

    tenant_id, messages, briefing, stale = await asyncio.to_thread(_read)

    need_generate = force or stale
    if need_generate:
        briefing = await _generate_and_save(tenant_id, agent_id, messages)
        # Reload message state after generation (for example, read_at).
        def _reread():
            with get_sync_db() as db:
                return _query_today_messages(db, tenant_id, agent_id)
        messages = await asyncio.to_thread(_reread)

    compliance_warnings = await asyncio.to_thread(get_compliance_warnings, agent_id)

    return {
        'briefing': _serialize_briefing(briefing) if briefing else None,
        'messages': [_serialize_message(m) for m in messages],
        'compliance_warnings': compliance_warnings,
        'is_stale': False,
    }


@router.get('/api/briefing/today')
async def briefing_today(agent_id: str = Query(...)) -> dict:
    return await _fetch_today(agent_id, force=False)


@router.post('/api/briefing/today/regenerate')
async def briefing_regenerate(agent_id: str = Query(...)) -> dict:
    return await _fetch_today(agent_id, force=True)


@router.post('/api/briefing/today/acknowledge')
async def briefing_acknowledge(agent_id: str = Query(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            user = _resolve_user(db, agent_id)
            briefing = (
                db.query(DailyBriefing)
                .filter(
                    DailyBriefing.tenant_id == user.tenant_id,
                    DailyBriefing.agent_id == agent_id,
                    DailyBriefing.briefing_date == _today_beijing(),
                )
                .first()
            )
            if not briefing:
                raise HTTPException(404, detail='briefing not found')
            briefing.acknowledged_at = now_beijing()
            return {'acknowledged_at': briefing.acknowledged_at.isoformat()}

    return await asyncio.to_thread(_do)


# ── message-level operations ─────────────────────────────────────────────────


@router.get('/api/briefing/messages/{message_id}')
async def briefing_message_detail(message_id: str = Path(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            m = db.query(InboxMessage).filter(InboxMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, detail='message not found')
            return _serialize_message(m)
    return await asyncio.to_thread(_do)


@router.post('/api/briefing/messages/{message_id}/read')
async def briefing_message_read(message_id: str = Path(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            m = db.query(InboxMessage).filter(InboxMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, detail='message not found')
            if not m.read_at:
                m.read_at = now_beijing()
            return {'read_at': m.read_at.isoformat()}
    return await asyncio.to_thread(_do)


@router.post('/api/briefing/messages/{message_id}/handled')
async def briefing_message_handled(message_id: str = Path(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            m = db.query(InboxMessage).filter(InboxMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, detail='message not found')
            m.handled_at = now_beijing()
            if not m.read_at:
                m.read_at = m.handled_at
            return {'handled_at': m.handled_at.isoformat(), 'read_at': m.read_at.isoformat()}
    return await asyncio.to_thread(_do)


# ── admin: briefing settings ─────────────────────────────────────────────────


def _get_or_create_settings(db, tenant_id: str) -> BriefingSettings:
    s = db.query(BriefingSettings).filter(BriefingSettings.tenant_id == tenant_id).first()
    if not s:
        s = BriefingSettings(tenant_id=tenant_id)
        db.add(s)
        db.flush()
    return s


def _serialize_settings(s: BriefingSettings) -> dict:
    return {
        'tenant_id': s.tenant_id,
        'auto_generate_enabled': s.auto_generate_enabled,
        'auto_generate_time': s.auto_generate_time,
        'auto_generate_scope': s.auto_generate_scope,
        'min_messages_to_generate': s.min_messages_to_generate,
        'last_run_at': s.last_run_at.isoformat() if s.last_run_at else None,
        'last_run_status': s.last_run_status,
        'last_run_summary': s.last_run_summary,
    }


def _require_admin(db, agent_id: str) -> User:
    user = _resolve_user(db, agent_id)
    if not user.is_superadmin and (user.tier or 'agent') not in ('director', 'team_lead'):
        raise HTTPException(403, detail='admin permission required')
    return user


@router.get('/api/briefing/admin/settings')
async def briefing_settings_get(agent_id: str = Query(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            user = _require_admin(db, agent_id)
            s = _get_or_create_settings(db, user.tenant_id)
            return _serialize_settings(s)
    return await asyncio.to_thread(_do)


@router.put('/api/briefing/admin/settings')
async def briefing_settings_put(agent_id: str = Query(...), body: BriefingSettingsIn = Body(...)) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            user = _require_admin(db, agent_id)
            s = _get_or_create_settings(db, user.tenant_id)
            if body.auto_generate_enabled is not None:
                s.auto_generate_enabled = body.auto_generate_enabled
            if body.auto_generate_time is not None:
                s.auto_generate_time = body.auto_generate_time
            if body.auto_generate_scope is not None:
                s.auto_generate_scope = body.auto_generate_scope
            if body.min_messages_to_generate is not None:
                s.min_messages_to_generate = body.min_messages_to_generate
            return _serialize_settings(s)
    return await asyncio.to_thread(_do)


@router.post('/api/briefing/admin/warmup-now')
async def briefing_warmup_now(agent_id: str = Query(...)) -> dict:
    """Let an administrator warm up all eligible agents in the tenant."""
    from api.briefing.scheduler import warmup_tenant

    def _resolve():
        with get_sync_db() as db:
            user = _require_admin(db, agent_id)
            return user.tenant_id

    tenant_id = await asyncio.to_thread(_resolve)
    result = await warmup_tenant(tenant_id, manual=True)
    return result


# ── admin: inbox messages CRUD ───────────────────────────────────────────────


@router.get('/api/briefing/admin/agents')
async def briefing_admin_list_agents(agent_id: str = Query(...)) -> dict:
    """List message recipients in the current tenant."""

    def _do() -> dict:
        with get_sync_db() as db:
            admin_user = _require_admin(db, agent_id)
            q = db.query(User).filter(User.tenant_id == admin_user.tenant_id)
            users = q.order_by(User.username.asc()).all()
            return {
                'agents': [
                    {
                        'username': u.username,
                        'display_name': getattr(u, 'display_name', None) or u.username,
                        'tier': getattr(u, 'tier', None),
                    }
                    for u in users
                ]
            }

    return await asyncio.to_thread(_do)


@router.get('/api/briefing/admin/messages')
async def briefing_admin_list_messages(
    agent_id: str = Query(..., description='Administrator account'),
    target_agent_id: str | None = Query(None, description='Filter by agent'),
    priority: str | None = Query(None, pattern=r'^P[012]$'),
    source_system: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            admin_user = _require_admin(db, agent_id)
            q = db.query(InboxMessage).filter(InboxMessage.tenant_id == admin_user.tenant_id)
            if target_agent_id:
                q = q.filter(InboxMessage.agent_id == target_agent_id)
            if priority:
                q = q.filter(InboxMessage.priority == priority)
            if source_system:
                q = q.filter(InboxMessage.source_system == source_system)
            total = q.count()
            rows = (
                q.order_by(InboxMessage.occurred_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {
                'total': total,
                'limit': limit,
                'offset': offset,
                'items': [{**_serialize_message(m), 'agent_id': m.agent_id} for m in rows],
            }

    return await asyncio.to_thread(_do)


@router.post('/api/briefing/admin/messages')
async def briefing_admin_create_message(
    agent_id: str = Query(...),
    body: InboxMessageCreateIn = Body(...),
) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            admin_user = _require_admin(db, agent_id)
            target = db.query(User).filter(User.username == body.target_agent_id).first()
            if not target:
                raise HTTPException(404, detail=f'target agent not found: {body.target_agent_id}')
            if target.tenant_id != admin_user.tenant_id and not admin_user.is_superadmin:
                raise HTTPException(403, detail='target agent not in your tenant')

            external_id = body.external_id or f'MANUAL-{now_beijing():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}'
            existing = (
                db.query(InboxMessage)
                .filter(
                    InboxMessage.tenant_id == target.tenant_id,
                    InboxMessage.external_id == external_id,
                )
                .first()
            )
            if existing:
                raise HTTPException(409, detail=f'external_id already exists: {external_id}')

            msg = InboxMessage(
                id=str(uuid.uuid4()),
                tenant_id=target.tenant_id,
                agent_id=body.target_agent_id,
                external_id=external_id,
                priority=body.priority,
                category=body.category,
                notification_name=body.notification_name,
                receiver_type=body.receiver_type,
                trigger_logic=body.trigger_logic,
                template_summary=body.template_summary,
                policy_no=body.policy_no,
                customer_id=body.customer_id,
                customer_name=body.customer_name,
                product_name=body.product_name,
                business_type=body.business_type,
                raw_content=body.raw_content,
                classify_reason=body.classify_reason,
                channel=body.channel,
                deadline_at=body.deadline_at,
                occurred_at=body.occurred_at or now_beijing(),
                received_at=now_beijing(),
                source_system=body.source_system or 'manual',
            )
            db.add(msg)
            db.flush()
            db.refresh(msg)
            return {**_serialize_message(msg), 'agent_id': msg.agent_id}

    return await asyncio.to_thread(_do)


@router.put('/api/briefing/admin/messages/{message_id}')
async def briefing_admin_update_message(
    message_id: str = Path(...),
    agent_id: str = Query(...),
    body: InboxMessageUpdateIn = Body(...),
) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            admin_user = _require_admin(db, agent_id)
            m = db.query(InboxMessage).filter(InboxMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, detail='message not found')
            if m.tenant_id != admin_user.tenant_id and not admin_user.is_superadmin:
                raise HTTPException(403, detail='cross-tenant update forbidden')
            patch = body.model_dump(exclude_unset=True)
            for k, v in patch.items():
                setattr(m, k, v)
            db.flush()
            db.refresh(m)
            return {**_serialize_message(m), 'agent_id': m.agent_id}

    return await asyncio.to_thread(_do)


@router.delete('/api/briefing/admin/messages/{message_id}')
async def briefing_admin_delete_message(
    message_id: str = Path(...),
    agent_id: str = Query(...),
) -> dict:
    def _do() -> dict:
        with get_sync_db() as db:
            admin_user = _require_admin(db, agent_id)
            m = db.query(InboxMessage).filter(InboxMessage.id == message_id).first()
            if not m:
                raise HTTPException(404, detail='message not found')
            if m.tenant_id != admin_user.tenant_id and not admin_user.is_superadmin:
                raise HTTPException(403, detail='cross-tenant delete forbidden')
            db.delete(m)
            return {'deleted': message_id}

    return await asyncio.to_thread(_do)

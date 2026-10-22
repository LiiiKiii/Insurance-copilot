"""Original-compatible feature-model override storage and selection helpers.

Feature overrides are deliberately configuration only.  As in the documented
Original implementation, selecting an override does not yet change an
``AgentLoop`` provider request.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.db import get_sync_db
from admin.models.config import SystemConfig


logger = logging.getLogger(__name__)

FEATURE_SLUGS = (
    "gap_analysis",
    "competition",
    "attribution",
    "chase_plan",
    "feasibility",
    "team",
    "knowledge",
    "general",
)
FEATURE_META: dict[str, dict[str, str]] = {
    "gap_analysis": {"label": "缺口分析", "desc": "書面保費目標、達標缺口計算"},
    "competition": {"label": "競賽進度", "desc": "競賽狀態、榮譽目標追蹤"},
    "attribution": {"label": "歸因分析", "desc": "業績未達標原因分析"},
    "chase_plan": {"label": "追趕計劃", "desc": "週度目標拆解、行動計劃"},
    "feasibility": {"label": "可行性評估", "desc": "能否在截止日前達標"},
    "team": {"label": "團隊數據", "desc": "下屬業績彙總、團隊達成度"},
    "knowledge": {"label": "知識庫搜尋", "desc": "競賽規則、資格條件查詢"},
    "general": {"label": "通用兜底", "desc": "其他所有問題"},
}
_FEATURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gap_analysis": ("缺口", "差多少", "書面保費", "written premium", "達標", "距離"),
    "competition": ("競賽", "榮譽", "星光", "衝刺", "deadline", "截止"),
    "attribution": ("歸因", "為什麼", "原因", "沒達標", "表現差", "弱項"),
    "chase_plan": ("追趕", "計劃", "拆解", "每週", "行動", "安排"),
    "feasibility": ("來得及", "能趕上", "可行", "機率", "概率", "能否"),
    "team": ("團隊", "下屬", "下級", "手下", "整體", "我的團隊"),
    "knowledge": ("規則", "條件", "資格", "如何", "什麼是", "知識"),
}
_FEATURE_SLUG_SET = frozenset(FEATURE_SLUGS)
_KEY_PREFIX = "feature_model."
_LEGACY_KEY = "runtime.feature_models"
_cache: dict[str, str] = {slug: "" for slug in FEATURE_SLUGS}
_cache_lock = threading.RLock()


def _legacy_business_overrides(value: str) -> dict[str, str]:
    """Read only source-compatible legacy values without translating categories."""

    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return {
        slug: model
        for slug, model in parsed.items()
        if slug in _FEATURE_SLUG_SET and isinstance(model, str)
    }


def load_feature_models_from_db() -> None:
    """Load global per-feature overrides into the in-memory snapshot.

    The prior combined ``runtime.feature_models`` JSON value is a read-only
    compatibility fallback for already-stored business slugs.  Technical
    categories are intentionally ignored: there is no safe mapping from them
    to Original business features.  Canonical per-slug entries win.
    """

    try:
        with get_sync_db() as db:
            rows = db.query(SystemConfig).filter(
                SystemConfig.tenant_id.is_(None),
                SystemConfig.config_key.in_([f"{_KEY_PREFIX}{slug}" for slug in FEATURE_SLUGS]),
            ).all()
            legacy = (
                db.query(SystemConfig)
                .filter(
                    SystemConfig.tenant_id.is_(None),
                    SystemConfig.config_key == _LEGACY_KEY,
                )
                .one_or_none()
            )
    except Exception:
        logger.warning("Feature-model configuration database lookup failed.")
        return

    loaded = _legacy_business_overrides(legacy.config_value) if legacy is not None else {}
    for row in rows:
        slug = row.config_key.removeprefix(_KEY_PREFIX)
        if slug in _FEATURE_SLUG_SET and isinstance(row.config_value, str):
            loaded[slug] = row.config_value
    with _cache_lock:
        _cache.update(loaded)


async def save_feature_model_to_db(
    slug: str, model: str, db: AsyncSession | None = None
) -> None:
    """Upsert one global Original-format override and update cache after commit."""

    key = f"{_KEY_PREFIX}{slug}"
    normalized_model = model.strip() if isinstance(model, str) else ""
    if db is None:
        await asyncio.to_thread(_save_with_sync_db, key, normalized_model)
    else:
        row = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.tenant_id.is_(None), SystemConfig.config_key == key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                SystemConfig(
                    config_key=key,
                    config_value=normalized_model,
                    config_type="string",
                    description=f"Per-feature model: {slug}",
                    is_public=False,
                )
            )
        else:
            row.config_value = normalized_model
        legacy = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _LEGACY_KEY
                )
            )
        ).scalar_one_or_none()
        if legacy is not None:
            _strip_legacy_business_overrides(legacy, {slug})
        await db.commit()
    _set_cached(slug, normalized_model)


def _save_with_sync_db(key: str, model: str) -> None:
    with get_sync_db() as db:
        row = (
            db.query(SystemConfig)
            .filter(SystemConfig.tenant_id.is_(None), SystemConfig.config_key == key)
            .one_or_none()
        )
        if row is None:
            db.add(
                SystemConfig(
                    config_key=key,
                    config_value=model,
                    config_type="string",
                    description=f"Per-feature model: {key.removeprefix(_KEY_PREFIX)}",
                    is_public=False,
                )
            )
        else:
            row.config_value = model
        legacy = (
            db.query(SystemConfig)
            .filter(SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _LEGACY_KEY)
            .one_or_none()
        )
        if legacy is not None:
            _strip_legacy_business_overrides(legacy, {key.removeprefix(_KEY_PREFIX)})


def detect_feature(message: str) -> str:
    """Return the first Original keyword-matched feature, or ``general``."""

    normalized = message.lower()
    for slug, keywords in _FEATURE_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            return slug
    return "general"


def get_model_for_message(message: str) -> str | None:
    """Return the selected override, then the general override, if configured."""

    feature = detect_feature(message)
    with _cache_lock:
        override = _cache.get(feature, "")
        if override:
            return override
        general = _cache.get("general", "")
        return general if general else None


def get_feature_models_snapshot() -> dict[str, str]:
    """Return a copy of current configured overrides."""

    with _cache_lock:
        return dict(_cache)


def get_feature_model(slug: str) -> str:
    """Return one configured override or an empty string."""

    with _cache_lock:
        return _cache.get(slug, "")


def _set_cached(slug: str, model: str) -> None:
    with _cache_lock:
        _cache[slug] = model


def set_feature_model(slug: str, model: str) -> None:
    """Update only the in-memory snapshot; persistence uses the async helper."""

    _set_cached(slug, model.strip() if isinstance(model, str) else "")


async def reset_all_feature_models(db: AsyncSession | None = None) -> None:
    """Clear canonical overrides without deleting unrelated SystemConfig rows.

    A legacy combined row is retained, but explicitly reset business entries
    are removed from it so they cannot reappear after the next process start.
    Unmappable technical-category values remain untouched.
    """

    keys = [f"{_KEY_PREFIX}{slug}" for slug in FEATURE_SLUGS]
    if db is None:
        await asyncio.to_thread(_reset_with_sync_db, keys)
    else:
        rows = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.tenant_id.is_(None), SystemConfig.config_key.in_(keys)
                )
            )
        ).scalars().all()
        by_key = {row.config_key: row for row in rows}
        for slug in FEATURE_SLUGS:
            key = f"{_KEY_PREFIX}{slug}"
            row = by_key.get(key)
            if row is None:
                db.add(SystemConfig(
                    config_key=key, config_value="", config_type="string",
                    description=f"Per-feature model: {slug}", is_public=False,
                ))
            else:
                row.config_value = ""
        legacy = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _LEGACY_KEY
                )
            )
        ).scalar_one_or_none()
        if legacy is not None:
            _strip_legacy_business_overrides(legacy, _FEATURE_SLUG_SET)
        await db.commit()
    with _cache_lock:
        for slug in FEATURE_SLUGS:
            _cache[slug] = ""


def _reset_with_sync_db(keys: list[str]) -> None:
    with get_sync_db() as db:
        rows = (
            db.query(SystemConfig)
            .filter(SystemConfig.tenant_id.is_(None), SystemConfig.config_key.in_(keys))
            .all()
        )
        by_key = {row.config_key: row for row in rows}
        for key in keys:
            row = by_key.get(key)
            if row is None:
                slug = key.removeprefix(_KEY_PREFIX)
                db.add(SystemConfig(
                    config_key=key, config_value="", config_type="string",
                    description=f"Per-feature model: {slug}", is_public=False,
                ))
            else:
                row.config_value = ""
        legacy = (
            db.query(SystemConfig)
            .filter(SystemConfig.tenant_id.is_(None), SystemConfig.config_key == _LEGACY_KEY)
            .one_or_none()
        )
        if legacy is not None:
            _strip_legacy_business_overrides(legacy, _FEATURE_SLUG_SET)


def _strip_legacy_business_overrides(row: SystemConfig, slugs: set[str] | frozenset[str]) -> None:
    try:
        parsed = json.loads(row.config_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return
    if not isinstance(parsed, dict):
        return
    remaining = {key: value for key, value in parsed.items() if key not in slugs}
    row.config_value = json.dumps(remaining, sort_keys=True)

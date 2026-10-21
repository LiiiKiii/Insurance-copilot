"""Offline parity tests for Original-format feature-model overrides."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin.db import Base
from admin.models.config import SystemConfig
from api import feature_models
from api.feature_models import (
    FEATURE_META,
    FEATURE_SLUGS,
    detect_feature,
    get_feature_model,
    get_feature_models_snapshot,
    get_model_for_message,
    load_feature_models_from_db,
    reset_all_feature_models,
    save_feature_model_to_db,
    set_feature_model,
)
from api.routers.config import FeatureModelRequest, list_feature_models, reset_feature_models, update_feature_model


class FeatureModelParityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "feature-models.db"
        self.sync_engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self.sync_engine)
        self.sessions = sessionmaker(self.sync_engine, expire_on_commit=False)
        self.async_engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        self.async_sessions = async_sessionmaker(self.async_engine, expire_on_commit=False)
        with feature_models._cache_lock:
            feature_models._cache.clear()
            feature_models._cache.update({slug: "" for slug in FEATURE_SLUGS})

        @contextmanager
        def local_db():
            session = self.sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.local_db = local_db
        self.get_db_patch = patch("api.feature_models.get_sync_db", local_db)
        self.get_db_patch.start()

    async def asyncTearDown(self) -> None:
        self.get_db_patch.stop()
        await self.async_engine.dispose()
        self.sync_engine.dispose()
        self.temp_dir.cleanup()

    async def test_original_business_slug_catalog_metadata_and_cache_contract(self) -> None:
        self.assertEqual(
            FEATURE_SLUGS,
            (
                "gap_analysis", "competition", "attribution", "chase_plan",
                "feasibility", "team", "knowledge", "general",
            ),
        )
        self.assertEqual(FEATURE_META, {
            "gap_analysis": {"label": "缺口分析", "desc": "書面保費目標、達標缺口計算"},
            "competition": {"label": "競賽進度", "desc": "競賽狀態、榮譽目標追蹤"},
            "attribution": {"label": "歸因分析", "desc": "業績未達標原因分析"},
            "chase_plan": {"label": "追趕計劃", "desc": "週度目標拆解、行動計劃"},
            "feasibility": {"label": "可行性評估", "desc": "能否在截止日前達標"},
            "team": {"label": "團隊數據", "desc": "下屬業績彙總、團隊達成度"},
            "knowledge": {"label": "知識庫搜尋", "desc": "競賽規則、資格條件查詢"},
            "general": {"label": "通用兜底", "desc": "其他所有問題"},
        })
        set_feature_model("unknown", "model")
        self.assertEqual(get_feature_model("unknown"), "model")
        await reset_all_feature_models()
        self.assertEqual(get_feature_model("unknown"), "model")

    async def test_original_ordered_case_insensitive_keyword_detection(self) -> None:
        self.assertEqual(detect_feature("書面保費還差多少"), "gap_analysis")
        self.assertEqual(detect_feature("DEADLINE 前的衝刺"), "competition")
        # "達標" belongs to the first matching category, ahead of attribution.
        self.assertEqual(detect_feature("為什麼沒達標"), "gap_analysis")
        self.assertEqual(detect_feature("完全無關的內容"), "general")

    async def test_matched_override_then_general_then_none_fallback(self) -> None:
        self.assertIsNone(get_model_for_message("完全無關"))
        set_feature_model("general", "general-model")
        self.assertEqual(get_model_for_message("完全無關"), "general-model")
        set_feature_model("gap_analysis", "gap-model")
        self.assertEqual(get_model_for_message("書面保費缺口"), "gap-model")

    async def test_per_slug_global_string_persistence_and_empty_override(self) -> None:
        await save_feature_model_to_db("competition", "openai/gpt-5")
        with self.sessions() as session:
            row = session.query(SystemConfig).filter_by(config_key="feature_model.competition").one()
            self.assertIsNone(row.tenant_id)
            self.assertEqual((row.config_type, row.config_value, row.is_public), ("string", "openai/gpt-5", False))
            self.assertIsNone(session.query(SystemConfig).filter_by(config_key="runtime.feature_models").one_or_none())
        self.assertEqual(get_feature_model("competition"), "openai/gpt-5")
        await save_feature_model_to_db("competition", "")
        self.assertEqual(get_feature_model("competition"), "")
        with self.sessions() as session:
            row = session.query(SystemConfig).filter_by(config_key="feature_model.competition").one()
            self.assertEqual(row.config_value, "")

    async def test_startup_load_uses_canonical_rows_and_read_only_legacy_business_values(self) -> None:
        with self.sessions.begin() as session:
            session.add(SystemConfig(config_key="runtime.feature_models", config_type="json", config_value='{"competition":"legacy-model","chat":"ignored"}'))
            session.add(SystemConfig(config_key="feature_model.competition", config_type="string", config_value="canonical-model"))
            session.add(SystemConfig(config_key="feature_model.team", config_type="string", config_value="team-model"))
        load_feature_models_from_db()
        snapshot = get_feature_models_snapshot()
        self.assertEqual(snapshot["competition"], "canonical-model")
        self.assertEqual(snapshot["team"], "team-model")
        self.assertTrue(all(slug in snapshot for slug in FEATURE_SLUGS))
        self.assertEqual(get_model_for_message("unmapped request"), None)

    async def test_api_update_list_and_reset_preserve_response_envelope(self) -> None:
        async with self.async_sessions() as db:
            updated = await update_feature_model(
                FeatureModelRequest(slug="knowledge", model="  openai/gpt-5.2  "), None, db
            )
            self.assertEqual(updated, {"ok": True, "slug": "knowledge", "model": "openai/gpt-5.2"})
            listed = await list_feature_models(None)
            self.assertEqual(listed["data"][0], {
                "slug": "gap_analysis", "label": "缺口分析",
                "desc": "書面保費目標、達標缺口計算", "model": "",
            })
            knowledge = next(row for row in listed["data"] if row["slug"] == "knowledge")
            self.assertEqual(set(knowledge), {"slug", "label", "desc", "model"})
            self.assertEqual(knowledge["model"], "openai/gpt-5.2")
            unknown = await update_feature_model(
                FeatureModelRequest(slug="invalid_slug", model="model"), None, db
            )
            self.assertEqual(unknown, {"ok": False, "error": "Unknown feature slug: invalid_slug"})
            reset = await reset_feature_models(None, db)
            self.assertEqual(reset, {"ok": True, "message": "All feature model overrides cleared"})
        self.assertEqual(get_feature_models_snapshot(), {slug: "" for slug in FEATURE_SLUGS})
        with self.sessions() as session:
            self.assertEqual(
                session.query(SystemConfig).filter(SystemConfig.config_key.like("feature_model.%")).count(),
                len(FEATURE_SLUGS),
            )

    async def test_failed_save_does_not_mutate_cache(self) -> None:
        set_feature_model("general", "known-good")
        with patch("api.feature_models.get_sync_db", side_effect=RuntimeError("database unavailable")):
            with self.assertRaises(RuntimeError):
                await save_feature_model_to_db("general", "new-value")
        self.assertEqual(get_feature_model("general"), "known-good")

    async def test_reset_removes_only_business_entries_from_legacy_json(self) -> None:
        with self.sessions.begin() as session:
            session.add(SystemConfig(config_key="runtime.feature_models", config_type="json", config_value='{"team":"old","chat":"technical"}'))
            session.add(SystemConfig(config_key="feature_model.team", config_type="string", config_value="new"))
        await reset_all_feature_models()
        with self.sessions() as session:
            legacy = session.query(SystemConfig).filter_by(config_key="runtime.feature_models").one()
            self.assertEqual(legacy.config_value, '{"chat": "technical"}')
            self.assertEqual(
                session.query(SystemConfig).filter_by(config_key="feature_model.team").one().config_value,
                "",
            )

    async def test_canonical_update_prevents_legacy_value_from_reappearing_after_restart(self) -> None:
        with self.sessions.begin() as session:
            session.add(SystemConfig(config_key="runtime.feature_models", config_type="json", config_value='{"general":"legacy","chat":"technical"}'))
        load_feature_models_from_db()
        self.assertEqual(get_feature_model("general"), "legacy")
        await save_feature_model_to_db("general", "canonical")
        load_feature_models_from_db()
        self.assertEqual(get_feature_model("general"), "canonical")
        await save_feature_model_to_db("general", "")
        load_feature_models_from_db()
        self.assertEqual(get_feature_model("general"), "")
        with self.sessions() as session:
            legacy = session.query(SystemConfig).filter_by(config_key="runtime.feature_models").one()
            self.assertEqual(legacy.config_value, '{"chat": "technical"}')


if __name__ == "__main__":
    unittest.main()

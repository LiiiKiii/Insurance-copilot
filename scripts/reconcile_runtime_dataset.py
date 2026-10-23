"""Reconcile only known legacy seed records; dry-run is the default."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sqlalchemy import select

from admin.db import SyncSessionFactory
from admin.models.assessment import AgentAssessment
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant
from admin.models.user import User
from scripts.build_life_demo_dataset import load_source

LEGACY_ACCOUNTS = ("AGT001", "AGT002", "AGT003", "AGT_TL01")


def reconcile(*, apply: bool = False, backup: Path | None = None):
    if apply:
        if backup is None or not backup.is_file():
            raise ValueError("A pre-update database backup is required")
        document = json.loads(backup.read_text(encoding="utf-8"))
        if document.get("format") != "m2-runtime-backup-v1" or not document.get("tables"):
            raise ValueError("Unrecognized backup")
    old_performance = load_source("performance")
    with SyncSessionFactory() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "default"))
        if tenant is None:
            raise ValueError("Default tenant is missing")
        obsolete = []
        retained_custom = 0
        for target in db.scalars(select(PerformanceTarget).where(
            PerformanceTarget.tenant_id == tenant.id,
            PerformanceTarget.agent_id.in_(list(old_performance)),
        )):
            old = old_performance[target.agent_id]
            start, end = old["period"].split(" to ")
            if (target.period_start, target.period_end) != (start, end):
                continue
            metric = old["metrics"].get(target.metric_key, {})
            expected = metric.get("target")
            exact_seed = (isinstance(expected, (float, int))
                          and math.isclose(target.target_value, expected)
                          and target.unit == metric.get("unit")
                          and target.metric_label == metric.get("label"))
            if exact_seed:
                obsolete.append(target)
            else:
                retained_custom += 1
        old_assessments = load_source("assessments")
        obsolete_assessments = []
        for assessment in db.scalars(select(AgentAssessment).where(
            AgentAssessment.tenant_id == tenant.id,
            AgentAssessment.agent_id.in_(list(old_assessments)),
        )):
            source_rows = old_assessments[assessment.agent_id]["assessments"]
            for row in source_rows:
                if (assessment.unit is None
                    and assessment.subject == row["subject"]
                    and assessment.current_value == row.get("current_value")
                    and assessment.target_value == row.get("target_value")
                    and assessment.status == row.get("status")
                    and assessment.remark == row.get("remark")):
                    obsolete_assessments.append(assessment)
                    break
        legacy = list(db.scalars(select(User).where(
            User.tenant_id == tenant.id,
            User.username.in_(LEGACY_ACCOUNTS),
            User.is_superadmin.is_(False),
            User.is_active.is_(True),
        )))
        summary = {"mode": "apply" if apply else "dry-run", "old_seed_targets_to_remove": len(obsolete),
                   "custom_or_modified_old_targets_preserved": retained_custom,
                   "old_seed_assessments_to_remove": len(obsolete_assessments),
                   "legacy_accounts_to_deactivate": [u.username for u in legacy],
                   "passwords_changed": False, "chat_or_knowledge_modified": False}
        if apply:
            for target in obsolete:
                db.delete(target)
            for assessment in obsolete_assessments:
                db.delete(assessment)
            for user in legacy:
                user.is_active = False
            db.commit()
        else:
            db.rollback()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    print(json.dumps(reconcile(apply=args.apply, backup=args.backup), indent=2))

"""Runtime package, metadata and migration regression checks using isolated databases."""
import copy
import importlib.util
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from admin.db import Base
from admin.models.agent_data import AgentPerformanceMetrics, AgentPolicy
from admin.models.assessment import AgentAssessment
from admin.models.tenant import Tenant
from admin.seeds import (
    _seed_assessments,
    _seed_clients,
    _seed_performance,
    _seed_policies,
    _seed_tenant,
)
from api.routers.agent_dashboard import _performance_metrics
from nanobot.agent.tools.insurance.data_layer.pending import GetPendingPoliciesTool
from nanobot.agent.tools.insurance.data_layer.performance import (
    GetPerformanceSnapshotTool,
)
from nanobot.agent.tools.insurance.reasoning_layer.gap_analysis import (
    compute_gap_analysis,
)
from scripts.build_life_demo_dataset import FILES, ROOT, build, validate


def test_runtime_package_reproduces_all_seven_files_and_does_not_relabel_source_money():
    data = build()
    for name in FILES:
        assert data[name] == json.loads((ROOT / f'data/mock/{name}.json').read_text(encoding='utf-8'))
    assert len(data['agents']) == 50
    for aid, perf in data['performance'].items():
        assert perf['metrics']['protection_premium']['unit'] == 'HKD'
        assert 'synthetic' in perf['data_origin']['financial_performance']
        assert all(c['target_metric'] == 'fyc' for c in data['competitions'][aid]['competitions'] if c['type'] == 'honor')


def test_preflight_rejects_mixed_agent_keys_and_units_and_client_orphans():
    good = build()
    bad = copy.deepcopy(good)
    bad['assessments']['AGT001'] = bad['assessments'].pop(next(iter(bad['assessments'])))
    with pytest.raises(ValueError, match='Agent-key mismatch'):
        validate(bad)
    aid = good['agents'][0]['agent_id']
    bad = copy.deepcopy(good)
    bad['competitions'][aid]['competitions'][0]['unit'] = 'USD'
    with pytest.raises(ValueError, match='Competition metric mismatch'):
        validate(bad)
    bad = copy.deepcopy(good)
    bad['policies'][aid]['policies'][0]['customer_id'] = 'MISSING'
    with pytest.raises(ValueError, match='Policy-client mismatch'):
        validate(bad)


def test_pending_premium_does_not_offset_fyc_even_in_same_currency():
    rows = [{'id':'premium','gap':100,'unit':'HKD','target_metric':'protection_premium','days_remaining':20},
            {'id':'mdrt','gap':100,'unit':'HKD','target_metric':'fyc','days_remaining':10}]
    result = compute_gap_analysis(rows, 100, pending_unit='HKD')
    assert result[0]['actual_gap'] == 0
    assert result[1]['actual_gap'] == 100
    assert result[1]['pending_deduction'] == 0


def test_incremental_metadata_migration_preserves_existing_values_and_reverses():
    spec = importlib.util.spec_from_file_location('metadata_migration', ROOT/'alembic/versions/0009_business_metric_metadata.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE agent_performance_metrics (id TEXT PRIMARY KEY, fyc_current FLOAT)'))
        conn.execute(text('CREATE TABLE agent_assessments (id TEXT PRIMARY KEY, current_value FLOAT)'))
        conn.execute(text("INSERT INTO agent_performance_metrics VALUES ('keep', 123)"))
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            migration.upgrade()
            migration.upgrade()
            assert 'metric_metadata' in {c['name'] for c in inspect(conn).get_columns('agent_performance_metrics')}
            assert conn.execute(text('SELECT fyc_current FROM agent_performance_metrics')).scalar() == 123
            migration.downgrade()
            assert 'metric_metadata' not in {c['name'] for c in inspect(conn).get_columns('agent_performance_metrics')}
    engine.dispose()


@pytest.mark.asyncio
async def test_seeded_api_and_agent_tools_share_units_and_preserve_zero(tmp_path):
    data = build()
    url = f"sqlite+aiosqlite:///{(tmp_path/'runtime.db').as_posix()}"
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            await _seed_tenant(db)
            tenant = await db.scalar(select(Tenant).where(Tenant.slug == 'default'))
            for _ in range(2):
                await _seed_performance(db, data['performance'], tenant.id)
                await _seed_policies(db, data['policies'])
                await _seed_clients(db, data['clients'])
                await _seed_assessments(db, data['assessments'], tenant.id)
                await db.commit()
        sync_engine = create_engine(url.replace('+aiosqlite',''))
        try:
            with Session(sync_engine) as db:
                rows = db.scalars(select(AgentPerformanceMetrics)).all()
                assert len(rows) == 50
                assert len(db.scalars(select(AgentAssessment)).all()) == 150
                assert len(db.scalars(select(AgentPolicy)).all()) == 200
                assert all(a.unit == 'HKD' for a in db.scalars(select(AgentAssessment)))
                row = rows[0]
                api_metrics = _performance_metrics(row)
                with patch('nanobot.agent.tools.insurance.data_layer.performance.load_performance_row', return_value=row):
                    snapshot = json.loads(await GetPerformanceSnapshotTool(ROOT).execute(agent_id=row.agent_id))
                    for key in ('protection_premium', 'fyc', 'quarter_fyc', 'daily_fyc'):
                        assert snapshot['metrics'][key]['unit'] == api_metrics[key]['unit'] == 'HKD'
                        assert snapshot['metrics'][key]['current'] == api_metrics[key]['current']
                    rejected = json.loads(await GetPerformanceSnapshotTool(ROOT).execute(agent_id=row.agent_id, metrics=['written_premium']))
                    assert 'error' in rejected
                    row.ytd_fyc = 0
                    row.fyc_current = 123
                    snapshot = json.loads(await GetPerformanceSnapshotTool(ROOT).execute(agent_id=row.agent_id, metrics=['avg_fyc_per_policy']))
                    assert snapshot['metrics']['avg_fyc_per_policy']['current'] == 0
                aid = row.agent_id
            @contextmanager
            def local_session():
                with Session(sync_engine) as db:
                    yield db
            with patch('nanobot.agent.tools.insurance.data_layer.pending.get_sync_db', local_session):
                pending = json.loads(await GetPendingPoliciesTool(ROOT).execute(agent_id=aid))
            assert pending['currency'] == 'HKD'
            assert all(p['currency'] == 'HKD' for p in pending['policies'])
        finally:
            sync_engine.dispose()
    finally:
        await engine.dispose()

def test_reconciliation_removes_only_exact_old_seed_targets_and_preserves_credentials(tmp_path):
    from admin.models.performance_target import PerformanceTarget
    from admin.models.user import User
    from scripts import reconcile_runtime_dataset as reconciliation
    from scripts.build_life_demo_dataset import load_source

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    source = load_source('performance')
    aid, record = next(iter(source.items()))
    keys = [k for k, m in record['metrics'].items() if m.get('target') is not None]
    start, end = record['period'].split(' to ')
    with Session(engine) as db:
        db.add(Tenant(id='test-tenant', slug='default', name='Test'))
        db.add(User(id='legacy', tenant_id='test-tenant', username='AGT001', email='legacy@example.test', password_hash='keep-hash', is_active=True, is_superadmin=False))
        for index, key in enumerate(keys[:2]):
            m = record['metrics'][key]
            db.add(PerformanceTarget(id=f'target-{index}',tenant_id='test-tenant',agent_id=aid,
                metric_key=key,metric_label=m['label'],target_value=m['target']+(1 if index else 0),
                unit=m['unit'],period_type='annual',period_start=start,period_end=end))
        old_assessment = load_source('assessments')[aid]['assessments'][0]
        db.add(AgentAssessment(id='old-assessment',tenant_id='test-tenant',agent_id=aid,**old_assessment))
        db.add(AgentAssessment(id='custom-assessment',tenant_id='test-tenant',agent_id=aid,subject='Custom',current_value=10,target_value=20))
        db.commit()
    backup = tmp_path/'backup.json'
    backup.write_text(json.dumps({'format':'m2-runtime-backup-v1','tables':{'users':[]}}),encoding='utf-8')
    with patch.object(reconciliation,'SyncSessionFactory',lambda: Session(engine)):
        dry = reconciliation.reconcile()
        assert dry['old_seed_targets_to_remove'] == 1
        assert dry['old_seed_assessments_to_remove'] == 1
        assert dry['custom_or_modified_old_targets_preserved'] == 1
        with Session(engine) as db:
            assert db.get(User,'legacy').is_active
        with pytest.raises(ValueError,match='backup'):
            reconciliation.reconcile(apply=True)
        reconciliation.reconcile(apply=True, backup=backup)
    with Session(engine) as db:
        assert db.get(AgentAssessment,'old-assessment') is None
        assert db.get(AgentAssessment,'custom-assessment') is not None
        assert db.get(PerformanceTarget,'target-0') is None
        assert db.get(PerformanceTarget,'target-1') is not None
        assert not db.get(User,'legacy').is_active
        assert db.get(User,'legacy').password_hash == 'keep-hash'
    engine.dispose()

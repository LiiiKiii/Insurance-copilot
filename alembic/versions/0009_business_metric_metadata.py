"""Persist business metric definitions and assessment units without rewriting values."""
import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "metric_metadata" not in {c["name"] for c in inspector.get_columns("agent_performance_metrics")}:
        op.add_column("agent_performance_metrics", sa.Column("metric_metadata", sa.JSON(), nullable=True))
    if "unit" not in {c["name"] for c in inspector.get_columns("agent_assessments")}:
        op.add_column("agent_assessments", sa.Column("unit", sa.String(20), nullable=True))


def downgrade():
    with op.batch_alter_table("agent_assessments") as batch:
        batch.drop_column("unit")
    with op.batch_alter_table("agent_performance_metrics") as batch:
        batch.drop_column("metric_metadata")

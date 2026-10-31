"""Tablas de políticas de P2, con el esquema de backend/wallba/policy/schema.sql.

Revision ID: 0003_policy
Revises: 0002_person3
"""

from alembic import op

from wallba.policy.repository import SCHEMA_SQL

revision = "0003_policy"
down_revision = "0002_person3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Una sola fuente del esquema: el SQL que también aplica el repositorio de P2.
    statements = [
        "\n".join(line for line in part.splitlines() if not line.lstrip().startswith("--")).strip()
        for part in SCHEMA_SQL.split(";")
    ]
    for statement in statements:
        if statement:
            op.execute(statement)


def downgrade() -> None:
    op.drop_table("policy_activation")
    op.drop_table("policy_versions")

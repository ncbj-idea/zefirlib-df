"""get_gis_data_for_given_terc_safe

Revision ID: 4c370616cffd
Revises: 0392f4c2a180
Create Date: 2025-11-25 12:20:11.951929

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c370616cffd"
down_revision: str | None = "0392f4c2a180"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql_file = Path(__file__).resolve().parents[2] / "sql_queries" / "get_gis_data_for_given_terc_safe.sql"

    with open(sql_file, encoding="utf-8") as f:
        op.execute(f.read())


def downgrade() -> None:
    op.execute("DROP function if exists get_gis_data_for_given_terc_safe;")

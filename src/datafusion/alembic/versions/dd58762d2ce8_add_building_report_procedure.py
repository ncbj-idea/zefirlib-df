"""add building report procedure

Revision ID: dd58762d2ce8
Revises: 09498fff9fa5
Create Date: 2024-10-28 16:28:42.027786

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd58762d2ce8"
down_revision: str | None = "595fa6eb22e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql_queries_path = Path(__file__).resolve().parents[2] / "sql_queries"

    with (
        open(sql_queries_path / "get_gis_data_for_given_terc.sql", encoding="utf-8") as f1,
        open(
            sql_queries_path / "create_and_fill_dict_funkcja_szczegolowa_table.sql",
            encoding="utf-8",
        ) as f2,
    ):
        op.execute(f1.read())
        op.execute(f2.read())


def downgrade() -> None:
    op.execute("DROP function if exists get_gis_data_for_given_terc;")

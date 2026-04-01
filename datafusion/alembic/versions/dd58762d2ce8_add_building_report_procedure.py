"""add building report procedure

Revision ID: dd58762d2ce8
Revises: 09498fff9fa5
Create Date: 2024-10-28 16:28:42.027786

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd58762d2ce8"
down_revision: str | None = "595fa6eb22e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    # Read the SQL file and execute its content
    with (
        open("datafusion/sql_queries/get_gis_data_for_given_terc.sql") as f1,
        open(
            "datafusion/sql_queries/create_and_fill_dict_funkcja_szczegolowa_table.sql",
        ) as f2,
    ):
        op.execute(f1.read())
        op.execute(f2.read())


def downgrade():
    op.execute("DROP function if exists get_gis_data_for_given_terc;")

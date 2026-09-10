"""El cliente marca un día de nutrición como cumplido.

La pantalla de nutrición del cliente termina en un botón —"Marcar día como
completado"— que hasta ahora no tenía dónde guardar nada, y en una barra de
"consumido hoy" que por eso decía siempre 0.

Se guarda el DÍA, no cada comida: la pantalla no tiene ninguna casilla por
comida, así que una tabla por comida sería una tabla que nadie sabría
rellenar. Ver `app/models/nutrition_day.py`.

Revision ID: n1u2t3d4i5a6
Revises: f8a90b12c3d4
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

revision = "n1u2t3d4i5a6"
down_revision = "f8a90b12c3d4"
branch_labels = None
depends_on = None

TABLA = "client_nutrition_days"


def upgrade():
    # Idempotente a propósito: estas migraciones corren en cada despliegue con
    # `alembic upgrade heads` sobre bases que pueden venir de estados
    # distintos, y fallar por "ya existe" deja el arranque a medias.
    if TABLA in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLA,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_user_detail_id", sa.String(36), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_user_detail_id"], ["user_details.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Marcar dos veces el mismo día no son dos días cumplidos.
        sa.UniqueConstraint("client_user_detail_id", "day",
                            name="uq_nutricion_dia_cliente"),
    )
    op.create_index("ix_nutricion_dia_cliente", TABLA, ["client_user_detail_id"])


def downgrade():
    if TABLA not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_nutricion_dia_cliente", table_name=TABLA)
    op.drop_table(TABLA)

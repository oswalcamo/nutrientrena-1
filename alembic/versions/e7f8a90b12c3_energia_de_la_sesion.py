"""Con qué energía llegó el cliente al entreno.

Al terminar la sesión se le preguntan dos cosas en una escala de 1 a 10: con
qué energía llegó y cuánto se esforzó. El esfuerzo ya tenía sitio —`rpe`—;
la energía no, y son datos distintos: dos sesiones con el mismo esfuerzo no se
parecen en nada si a una llegó a 3 y a la otra a 9. Sin esta columna la
respuesta se perdía al guardar.

Revision ID: e7f8a90b12c3
Revises: d1e2f3a4b5c6, d6e7f8a90b12
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op

revision = "e7f8a90b12c3"
down_revision = ("d1e2f3a4b5c6", "d6e7f8a90b12")
branch_labels = None
depends_on = None


def _tiene_columna(bind, tabla, columna):
    return columna in {c["name"] for c in sa.inspect(bind).get_columns(tabla)}


def upgrade():
    bind = op.get_bind()
    if not _tiene_columna(bind, "workout_sessions", "energy"):
        op.add_column("workout_sessions", sa.Column("energy", sa.Integer(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if _tiene_columna(bind, "workout_sessions", "energy"):
        op.drop_column("workout_sessions", "energy")

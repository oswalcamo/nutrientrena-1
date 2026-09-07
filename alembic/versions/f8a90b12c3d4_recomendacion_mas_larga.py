"""La recomendación del ejercicio no siempre es una cifra.

`rec_series`, `rec_reps` y `rec_rest` se pensaron para «3-4», «8-12» y «90s»,
y con 40 caracteres sobraba. Pero el catálogo que entrega el cliente trae
frases enteras —«Continuo: 10-15 min, o 8-10 rondas de subida/bajada», 51
caracteres— porque un ejercicio de cardio no se prescribe en series y
repeticiones.

En 40 eso se cortaba por la mitad y quedaba «Continuo: 10-15 min, o 8-10
rondas de», que además de perder la mitad de la prescripción parece un dato
correcto. Se ensancha a 120 en vez de recortar lo que escribió el coach.

Revision ID: f8a90b12c3d4
Revises: e7f8a90b12c3
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op

revision = "f8a90b12c3d4"
down_revision = "e7f8a90b12c3"
branch_labels = None
depends_on = None

COLUMNAS = ("rec_series", "rec_reps", "rec_rest")


def upgrade():
    for c in COLUMNAS:
        op.alter_column("trainings", c, type_=sa.String(120),
                        existing_type=sa.String(40), existing_nullable=True)


def downgrade():
    # Volver a 40 recortaría lo que no quepa, así que esto solo es seguro si
    # nadie ha escrito una recomendación larga todavía.
    for c in COLUMNAS:
        op.alter_column("trainings", c, type_=sa.String(40),
                        existing_type=sa.String(120), existing_nullable=True)

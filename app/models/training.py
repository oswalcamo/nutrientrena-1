from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Training(Base):
    __tablename__ = "trainings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    # Otros nombres del mismo ejercicio, separados por comas: el inglés, la
    # jerga de gimnasio, las variantes. Solo sirven para BUSCAR: el ejercicio se
    # sigue llamando `name` en todas partes. Sin esto, quien escribe "bench
    # press" no encuentra el press de banca y acaba creándolo otra vez.
    aliases = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    muscle_group_id = Column(Integer, ForeignKey("muscle_groups.id"), nullable=True)
    secondary_muscle_group_id = Column(Integer, ForeignKey("muscle_groups.id"), nullable=True)  # first of the set (back-compat)
    secondary_muscle_group_ids = Column(Text, nullable=True)  # comma-separated muscle group ids
    image = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    exercise_type = Column(String(20), nullable=True)  # compound/isolation/cardio/mobility
    location = Column(String(20), nullable=True)  # gym/home/outdoor/both
    material = Column(String(120), nullable=True)  # Barra, Mancuernas, Sin equipo…
    difficulty = Column(Integer, nullable=True)  # nivel más bajo del set (back-compat)
    difficulty_levels = Column(Text, nullable=True)  # niveles separados por coma: 1 Principiante / 2 Intermedio / 3 Avanzado
    movement_pattern = Column(String(255), nullable=True)  # Empuje horizontal, Bisagra de cadera…
    # 120 y no 40: la recomendacion no siempre es una cifra. El catalogo del
    # cliente trae frases enteras —"Continuo: 10-15 min, o 8-10 rondas de
    # subida/bajada"— y en 40 caracteres se cortaba a media prescripcion.
    rec_series = Column(String(120), nullable=True)  # series, ej. "3-4"
    rec_reps = Column(String(120), nullable=True)    # reps, ej. "8-12"
    rec_rest = Column(String(120), nullable=True)    # descanso, ej. "60-90s"
    state = Column(Integer, default=1)
    # NULL = catálogo maestro de la plataforma, visible para todos. Con valor =
    # ejercicio privado de esa organización.
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)
    # Quién lo creó: su autor siempre puede editar lo suyo, tenga organización
    # o no (un coach sin organización crea con organization_id NULL).
    created_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    muscle_group = relationship("MuscleGroup", foreign_keys=[muscle_group_id], back_populates="trainings")
    secondary_muscle_group = relationship("MuscleGroup", foreign_keys=[secondary_muscle_group_id])
    routine_day_details = relationship("RoutineDayDetail", back_populates="training")


class TrainingClient(Base):
    __tablename__ = "training_clients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    training_id = Column(Integer, ForeignKey("trainings.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    training = relationship("Training")
    user = relationship("User")

from sqlalchemy import Column, Integer, String, Float, Text, Boolean, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_user_detail_id = Column(String(36), ForeignKey("user_details.id"), nullable=False)
    routine_id = Column(Integer, ForeignKey("routines.id"), nullable=True)
    # Qué día de la rutina fue ("Día 4"), copiado como texto. Es lo que se
    # lee en el historial; con solo `routine_id` la columna diría el nombre
    # de la rutina entera, que es el mismo en las cincuenta sesiones.
    day_name = Column(String(255), nullable=True)
    session_date = Column(Date, nullable=False)
    duration_min = Column(Integer, nullable=True)
    rpe = Column(Float, nullable=True)
    # Cómo se ha sentido, de 1 (fatal) a 5 (genial). Lo marca el cliente al
    # terminar y es OPCIONAL: las sesiones de antes no lo tienen y las de ahora
    # tampoco si prefiere no decirlo. Vacío es vacío, no "normal".
    mood = Column(Integer, nullable=True)
    # Con qué energía LLEGÓ al entreno, de 1 a 10. Es otra cosa que el esfuerzo
    # (`rpe`, cuánto se vació) y que el ánimo (`mood`, cómo salió): dos sesiones
    # con el mismo esfuerzo no se parecen si a una llegó a 3 y a la otra a 9.
    # Opcional, como las demás: vacío es vacío.
    energy = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    routine = relationship("Routine")
    exercises = relationship(
        "WorkoutSessionExercise", back_populates="session",
        cascade="all, delete-orphan", order_by="WorkoutSessionExercise.order_index",
    )


class WorkoutSessionExercise(Base):
    """Ejercicio realizado dentro de una sesión (con sus series)."""
    __tablename__ = "workout_session_exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False)
    training_id = Column(Integer, ForeignKey("trainings.id"), nullable=True)
    # Nombre/grupo guardados como copia: el historial se conserva aunque el
    # ejercicio se renombre o se borre del catálogo.
    name = Column(String(255), nullable=True)
    muscle_group_name = Column(String(255), nullable=True)
    order_index = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("WorkoutSession", back_populates="exercises")
    sets = relationship(
        "WorkoutSessionSet", back_populates="exercise",
        cascade="all, delete-orphan", order_by="WorkoutSessionSet.set_number",
    )


class WorkoutSessionSet(Base):
    """Serie registrada por el cliente (reps, kg, RPE y si la completó)."""
    __tablename__ = "workout_session_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_exercise_id = Column(Integer, ForeignKey("workout_session_exercises.id", ondelete="CASCADE"), nullable=False)
    set_number = Column(Integer, nullable=False)
    reps = Column(String(20), nullable=True)   # texto: admite "8", "8-10", "40s"
    weight = Column(Float, nullable=True)      # kg
    rpe = Column(Float, nullable=True)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    exercise = relationship("WorkoutSessionExercise", back_populates="sets")

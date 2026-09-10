from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class ClientNutritionDay(Base):
    """Un día de nutrición que el cliente ha dado por cumplido.

    Es lo único que hay detrás de "Marcar día como completado", y a propósito:
    se guarda el DÍA, no cada comida. La pantalla no tiene ninguna casilla por
    comida —solo el botón del final—, así que un modelo por comida sería una
    tabla que nadie sabría rellenar, y "consumido hoy" no podría estar nunca en
    un punto intermedio. Con esto, la barra dice 0 o el total, que es
    exactamente lo que el diseño puede expresar.

    Si algún día se pide marcar comida a comida, esta tabla no estorba: se le
    añade la comida y el día pasa a ser el resumen de ellas.

    Se apunta contra el DÍA del calendario y no contra la dieta: la dieta puede
    cambiarse, y lo que el cliente marcó el martes lo marcó el martes.
    """

    __tablename__ = "client_nutrition_days"
    __table_args__ = (
        # Marcar dos veces el mismo día no son dos días cumplidos. Sin esto,
        # dos toques seguidos —o dos pestañas abiertas— dejaban filas repetidas
        # y el recuento dejaba de cuadrar.
        UniqueConstraint("client_user_detail_id", "day", name="uq_nutricion_dia_cliente"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_user_detail_id = Column(String(36), ForeignKey("user_details.id", ondelete="CASCADE"),
                                   nullable=False, index=True)
    day = Column(Date, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)

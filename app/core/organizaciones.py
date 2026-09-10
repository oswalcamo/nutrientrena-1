"""A qué organización pertenece alguien.

Vivía dentro de `app/routers/chat.py`, que era donde primero hizo falta. Ahora
lo necesita también la nutrición del cliente —para saber de qué catálogo de
recetas puede tirar— y copiarlo habría dejado dos versiones de "cuál es tu
centro" que tarde o temprano dicen cosas distintas. Es el mismo camino que ya
se hizo con `macros.py` y `entrenos.py`.

Son tres sitios donde puede estar la pertenencia, y hay que mirar los tres:
ser el dueño, estar en el equipo, o estar como miembro.
"""
from sqlalchemy.orm import Session

from app.models.user import UserDetail


def detalle_de(db: Session, user_id: int):
    return db.query(UserDetail).filter(UserDetail.user_id == user_id).first()


def organizacion_de_detalle(db: Session, detalle):
    """La organización de la que este UserDetail es dueño o miembro, o None."""
    from app.models.organization import Organization, OrganizationMember
    from app.models.team_member import TeamMember

    if not detalle:
        return None

    org = db.query(Organization).filter(Organization.owner_id == detalle.id).first()
    if org:
        return org

    fila = db.query(TeamMember).filter(
        TeamMember.user_detail_id == detalle.id,
        TeamMember.organization_id.isnot(None),
    ).first()
    if fila:
        return db.query(Organization).filter(Organization.id == fila.organization_id).first()

    miembro = db.query(OrganizationMember).filter(
        OrganizationMember.user_detail_id == detalle.id
    ).first()
    if miembro:
        return db.query(Organization).filter(Organization.id == miembro.organization_id).first()

    return None


def organizacion_de(db: Session, user_id: int):
    """Lo mismo, partiendo del id de usuario."""
    return organizacion_de_detalle(db, detalle_de(db, user_id))

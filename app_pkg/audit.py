from flask import g
from app_pkg.models import AuditLog, db

def audit(action, entity_type, entity_id, payload=None):
    try:
        actor = getattr(g, 'current_user', None)
        entry = AuditLog(actor_user_id=(actor.id if actor else None), action=action, entity_type=entity_type, entity_id=entity_id, payload=(payload or ''))
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass


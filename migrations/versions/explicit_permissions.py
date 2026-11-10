"""Make every non-admin user's permissions explicit before switching to deny-by-default

Before this revision an empty `user.permissions` meant "allowed everything", and most pages
didn't check permissions at all. Now permissions are enforced and empty means "nothing".
To keep everyone's current access:

- users with no stored permissions get every key (what they effectively had);
- users with custom permissions keep them, plus energy.view (the energy dashboard was shown
  to everyone), plus hr/email/performance.view if they hold dashboard.view (those dashboards
  were reachable from the admin panel, which dashboard.view opens).

Revision ID: explicit_permissions
Revises: login_attempt
"""
import json

import sqlalchemy as sa
from alembic import op

revision = 'explicit_permissions'
down_revision = 'login_attempt'
branch_labels = None
depends_on = None

# Snapshot of the permission keys at this revision (don't import app code into migrations).
ALL_KEYS = [
    'dashboard.view', 'today.view', 'meetings.view', 'meetings.manage', 'resolutions.view',
    'resolutions.manage', 'tasks.view', 'tasks.manage', 'projects.view', 'projects.manage',
    'timeline.view', 'events.view', 'agreements.view', 'org_chart.view', 'users.manage',
    'hr.view', 'email.view', 'performance.view', 'energy.view',
]
ADMIN_PANEL_DASHBOARDS = ['hr.view', 'email.view', 'performance.view']


def upgrade():
    conn = op.get_bind()
    users = sa.table('user', sa.column('id', sa.Integer), sa.column('role', sa.String),
                     sa.column('permissions', sa.Text))
    for uid, role, raw in conn.execute(sa.select(users.c.id, users.c.role, users.c.permissions)).all():
        if role == 'admin':
            continue
        try:
            perms = json.loads(raw) if raw else {}
            if not isinstance(perms, dict):
                perms = {}
        except ValueError:
            perms = {}
        perms = {k: True for k, v in perms.items() if v is True}

        if not perms:
            new = {k: True for k in ALL_KEYS}
        else:
            new = dict(perms, **{'energy.view': True})
            if perms.get('dashboard.view'):
                new.update({k: True for k in ADMIN_PANEL_DASHBOARDS})
        conn.execute(users.update().where(users.c.id == uid).values(permissions=json.dumps(new)))


def downgrade():
    # The old semantics can't be reconstructed exactly; leaving explicit permissions in place
    # grants nothing beyond what they granted before.
    pass

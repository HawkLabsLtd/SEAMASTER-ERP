"""Deny-by-default permissions, enforced on the server (not just hidden in the menu)."""
import pytest

from conftest import csrf_headers

JSON = {'Accept': 'application/json'}

# (path, permission that opens it)
GUARDED_PAGES = [
    ('/', 'dashboard.view'),
    ('/today', 'today.view'),
    ('/meetings', 'meetings.view'),
    ('/resolutions', 'resolutions.view'),
    ('/tasks/', 'tasks.view'),
    ('/kanban/', 'tasks.view'),
    ('/projects/', 'projects.view'),
    ('/timeline', 'timeline.view'),
    ('/events', 'events.view'),
    ('/agreements/', 'agreements.view'),
    ('/org_chart/', 'org_chart.view'),
    ('/hr/', 'hr.view'),
    ('/email/', 'email.view'),
    ('/performance/', 'performance.view'),
    ('/energy/', 'energy.view'),
    ('/admin', 'dashboard.view'),
]


@pytest.mark.parametrize('path,perm', GUARDED_PAGES)
def test_user_without_permissions_is_denied(login, path, perm):
    c = login('noperm')
    assert c.get(path, headers=JSON).status_code == 403


@pytest.mark.parametrize('path,perm', GUARDED_PAGES)
def test_user_with_permissions_is_allowed(login, path, perm):
    assert login('staff').get(path).status_code == 200


def test_single_permission_opens_only_that_page(login):
    c = login('limited')
    assert c.get('/org_chart/').status_code == 200
    assert c.get('/hr/api/employees', headers=JSON).status_code == 403
    assert c.get('/meetings', headers=JSON).status_code == 403


def test_user_without_permissions_lands_on_profile(app, login):
    c = login('noperm')
    r = c.get('/')
    assert r.status_code == 302 and r.headers['Location'].endswith('/profile')
    assert c.get('/profile').status_code == 200


def test_denied_page_redirects_to_users_home(login):
    r = login('limited').get('/meetings')
    assert r.status_code == 302 and r.headers['Location'].endswith('/org_chart/')


def test_staff_cannot_move_kanban_cards(login):
    c = login('staff')
    r = c.post('/kanban/api/update_status', json={'id': 1, 'column': 'completed'}, headers=csrf_headers(c))
    assert r.status_code == 403


def test_staff_cannot_add_resolution_to_meeting(app, login):
    from datetime import datetime
    from app_pkg.models import db, Meeting, Resolution
    with app.app_context():
        m = Meeting(title='perm-test', scheduled_at=datetime.utcnow())
        db.session.add(m)
        db.session.commit()
        mid = m.id
    c = login('staff')
    c.post(f'/meetings/{mid}/resolutions/new', data={'title': 'sneaky'}, headers=csrf_headers(c))
    with app.app_context():
        assert Resolution.query.filter_by(title='sneaky').first() is None


@pytest.mark.parametrize('path', ['/hr/import', '/email/update', '/performance/update', '/energy/reload', '/events/upload'])
def test_staff_cannot_upload_dashboard_data(login, path):
    c = login('staff')
    assert c.post(path, headers={**csrf_headers(c), **JSON}).status_code == 403


def test_hr_reset_is_post_and_admin_only(login):
    c = login('manager')
    assert c.get('/hr/init').status_code == 405
    assert c.post('/hr/init', headers={**csrf_headers(c), **JSON}).status_code == 403


def test_post_without_csrf_token_is_rejected(app, login):
    from app_pkg.models import User
    c = login('manager')
    r = c.post('/users/new', data={'name': 'no-csrf', 'role': 'staff'})
    assert r.status_code in (302, 400)
    with app.app_context():
        assert User.query.filter_by(name='no-csrf').first() is None


def test_unknown_permission_keys_are_dropped(app, login):
    import json
    from app_pkg.models import User
    c = login('admin')
    c.post('/users/new', data={'name': 'odd-perms', 'role': 'staff',
                               'permissions[]': ['today.view', 'root.everything']}, headers=csrf_headers(c))
    with app.app_context():
        assert json.loads(User.query.filter_by(name='odd-perms').one().permissions) == {'today.view': True}

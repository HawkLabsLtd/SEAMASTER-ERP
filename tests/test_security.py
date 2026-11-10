"""Regression tests for the security bugs found in the code review."""
from conftest import TEST_PASSWORD, csrf_headers, csrf_token


def test_self_registration_is_disabled_by_default(app):
    from app_pkg.models import User
    c = app.test_client()
    r = c.post('/register', data={'name': 'stranger', 'email': 'stranger@example.test', 'password': TEST_PASSWORD,
                                  'csrf_token': csrf_token(c)})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    with app.app_context():
        assert User.query.filter_by(email='stranger@example.test').first() is None


def test_login_page_hides_register_link(client):
    assert b'/register' not in client.get('/login').data


def test_org_chart_data_requires_login(client):
    assert client.get('/org_chart/data').status_code == 302


def test_org_chart_data_available_with_permission(login):
    assert login('limited').get('/org_chart/data').status_code == 200


def test_ai_chat_requires_login(client):
    assert client.post('/api/ai/chat', json={'message': 'hi'}).status_code == 401


def test_ai_chat_works_when_logged_in_with_csrf(login):
    c = login('staff')
    r = c.post('/api/ai/chat', json={'message': 'hi'}, headers=csrf_headers(c))
    assert r.status_code == 200
    assert 'response' in r.get_json()


def test_seed_routes_are_not_get(app):
    methods = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert '/seed' not in methods  # replaced by `flask init-db` / `flask create-admin`
    assert 'GET' not in methods['/seed/fa']


def test_destructive_seed_refused_without_opt_in(app, login):
    from app_pkg.models import User
    c = login('admin')
    with app.app_context():
        before = User.query.count()
    assert c.post('/seed/fa', headers=csrf_headers(c)).status_code == 403
    with app.app_context():
        assert User.query.count() == before


def test_staff_cannot_seed(login):
    c = login('staff')
    r = c.post('/seed/fa', headers=csrf_headers(c))
    assert r.status_code == 302


def test_manager_cannot_create_admin(app, login):
    from app_pkg.models import User
    c = login('manager')
    c.post('/users/new', data={'name': 'escalated', 'role': 'admin'}, headers=csrf_headers(c))
    with app.app_context():
        assert User.query.filter_by(name='escalated').first() is None


def test_manager_can_create_staff(app, login):
    from app_pkg.models import User
    c = login('manager')
    c.post('/users/new', data={'name': 'new-staff', 'role': 'staff'}, headers=csrf_headers(c))
    with app.app_context():
        u = User.query.filter_by(name='new-staff').first()
        assert u is not None and u.role == 'staff'


def test_manager_cannot_edit_admin(app, login, users):
    from app_pkg.models import db, User
    c = login('manager')
    admin_id = users['admin']
    c.post(f'/users/{admin_id}/edit', data={'name': 'hijacked', 'role': 'admin', 'password': 'x' * 8},
           headers=csrf_headers(c))
    with app.app_context():
        assert db.session.get(User, admin_id).name == 'test-admin'


def test_manager_cannot_promote_to_admin(app, login):
    from app_pkg.models import db, User
    with app.app_context():
        u = User(name='promote-me', role='staff')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    c = login('manager')
    c.post(f'/users/{uid}/edit', data={'name': 'promote-me', 'role': 'admin'}, headers=csrf_headers(c))
    with app.app_context():
        assert db.session.get(User, uid).role == 'staff'


def test_admin_can_delete_user(app, login):
    from app_pkg.models import db, User
    with app.app_context():
        u = User(name='to-delete', role='staff')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    c = login('admin')
    c.post(f'/users/{uid}/delete', headers=csrf_headers(c))
    with app.app_context():
        assert db.session.get(User, uid) is None


def test_chat_widget_only_for_logged_in_users(client, login):
    assert 'Kaveh AI' not in client.get('/login').get_data(as_text=True)
    assert 'Kaveh AI' in login('noperm').get('/profile').get_data(as_text=True)

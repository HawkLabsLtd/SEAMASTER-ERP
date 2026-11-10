from conftest import TEST_PASSWORD, post_login


def test_login_page_renders(client):
    assert client.get('/login').status_code == 200


def test_protected_route_redirects_anonymous_to_login(client):
    r = client.get('/meetings')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_anonymous_json_request_gets_401(client):
    r = client.get('/org_chart/data', headers={'Accept': 'application/json'})
    assert r.status_code == 401


def test_login_with_username_succeeds(client, users):
    r = post_login(client, 'test-admin', TEST_PASSWORD)
    assert r.status_code == 302
    assert '/login' not in r.headers['Location']
    assert client.get_cookie('seamaster_auth') is not None


def test_login_with_email_succeeds(client, users):
    post_login(client, 'test-staff@example.test', TEST_PASSWORD)
    assert client.get_cookie('seamaster_auth') is not None


def test_login_with_wrong_password_fails(client, users):
    r = post_login(client, 'test-manager', 'wrong')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']
    assert client.get_cookie('seamaster_auth') is None


def test_login_without_csrf_token_is_rejected(client, users):
    client.post('/login', data={'email': 'test-admin', 'password': TEST_PASSWORD})
    assert client.get_cookie('seamaster_auth') is None


def test_unknown_user_and_wrong_password_look_the_same(app, users):
    msgs = []
    for ident in ('no-such-user', 'test-limited'):
        c = app.test_client()
        post_login(c, ident, 'wrong-password')
        msgs.append(c.get('/login').get_data(as_text=True).count('نام کاربری یا رمز عبور نادرست است'))
    assert msgs == [1, 1]


def test_password_with_angle_brackets_works(app, client, users):
    from werkzeug.security import generate_password_hash
    from app_pkg.models import db, User
    pw = 'a<b>c&d e'
    with app.app_context():
        u = User(name='brackets', username='brackets', role='staff', permissions='{"today.view": true}',
                 password_hash=generate_password_hash(pw))
        db.session.add(u)
        db.session.commit()
    post_login(client, 'brackets', pw)
    assert client.get_cookie('seamaster_auth') is not None


def test_failed_logins_are_throttled_per_account(app, users):
    from app_pkg.models import db, User
    from werkzeug.security import generate_password_hash
    with app.app_context():
        db.session.add(User(name='throttled', username='throttled', role='staff',
                            password_hash=generate_password_hash(TEST_PASSWORD)))
        db.session.commit()
    for _ in range(5):
        post_login(app.test_client(), 'throttled', 'wrong')
    c = app.test_client()
    post_login(c, 'throttled', TEST_PASSWORD)  # correct password, but locked out for now
    assert c.get_cookie('seamaster_auth') is None
    # Another account from the same IP is unaffected.
    c2 = app.test_client()
    post_login(c2, 'test-limited', TEST_PASSWORD)
    assert c2.get_cookie('seamaster_auth') is not None


def test_successful_login_clears_failures(app, users):
    for _ in range(4):
        post_login(app.test_client(), 'test-noperm', 'wrong')
    c = app.test_client()
    post_login(c, 'test-noperm', TEST_PASSWORD)
    assert c.get_cookie('seamaster_auth') is not None
    for _ in range(4):
        post_login(app.test_client(), 'test-noperm', 'wrong')
    c = app.test_client()
    post_login(c, 'test-noperm', TEST_PASSWORD)
    assert c.get_cookie('seamaster_auth') is not None


def test_logout_revokes_token(app, login):
    from app_pkg.models import AuthToken
    c = login('staff')
    token = c.get_cookie('seamaster_auth').value
    c.get('/logout')
    with app.app_context():
        assert AuthToken.query.filter_by(token=token).first() is None
    c.set_cookie('seamaster_auth', token)
    assert c.get('/meetings').status_code == 302


def test_staff_cannot_open_user_management(login):
    r = login('staff').get('/users')
    assert r.status_code == 302


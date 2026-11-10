"""Hit every parameterless GET route. Nothing should 500, and anonymous users
should be bounced to /login except on the deliberately public paths."""

# GET routes that mutate or wipe data; never call them from the smoke test.
UNSAFE = {'/seed', '/seed/fa', '/logout', '/hr/init'}
PUBLIC_PREFIXES = ('/login', '/register')


def get_routes(app):
    routes = []
    for rule in app.url_map.iter_rules():
        if 'GET' in rule.methods and not rule.arguments and rule.rule not in UNSAFE:
            routes.append(rule.rule)
    return sorted(routes)


def test_route_list_is_not_empty(app):
    assert len(get_routes(app)) > 20


def test_admin_get_routes_do_not_error(app, login):
    c = login('admin')
    failures = {}
    for path in get_routes(app):
        try:
            status = c.get(path).status_code
        except Exception as e:  # TESTING propagates exceptions
            status = f'{type(e).__name__}: {e}'
        if not isinstance(status, int) or status >= 500:
            failures[path] = status
    assert failures == {}


def test_anonymous_is_redirected_to_login(app, client):
    leaks = {}
    for path in get_routes(app):
        if path.startswith(PUBLIC_PREFIXES):
            continue
        r = client.get(path)
        if r.status_code != 302 or '/login' not in r.headers.get('Location', ''):
            leaks[path] = r.status_code
    assert leaks == {}


def test_budget_dashboard_is_mounted_behind_login(client, login):
    r = client.get('/dash/budget/')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert login('noperm').get('/dash/budget/').status_code == 302  # staff role: not allowed
    assert login('admin').get('/dash/budget/').status_code == 200

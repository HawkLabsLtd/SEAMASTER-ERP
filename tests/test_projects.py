"""Project & task flows. The JSON keys asserted here are read by templates/projects/dashboard.html."""
import pytest

from conftest import csrf_headers

AJAX = {'X-Requested-With': 'XMLHttpRequest'}


@pytest.fixture
def admin(login):
    c = login('admin')
    c.headers = {**csrf_headers(c), **AJAX}
    return c


@pytest.fixture
def project(app):
    from app_pkg.models import db, Project
    with app.app_context():
        p = Project(title='Test project', code=None, start_date_shamsi='1404/01/01',
                    end_date_shamsi='1404/12/29', status='in_progress', progress=0)
        db.session.add(p)
        db.session.commit()
        return p.id


def new_task(c, project_id, **extra):
    r = c.post('/projects/tasks/new', json={'project_id': project_id, 'title': 'Task A', **extra}, headers=c.headers)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def test_create_task_assigns_next_wbs(admin, project):
    first = new_task(admin, project)
    second = new_task(admin, project, title='Task B')
    assert (first['wbs'], second['wbs']) == ('1.1', '1.2')
    assert set(first) >= {'status', 'message', 'task_id', 'wbs', 'title', 'assignee_name', 'start_date_shamsi',
                          'end_date_shamsi', 'duration_days', 'progress', 'status_code', 'project_progress', 'kpis'}
    assert first['start_date_shamsi'] == '1404/01/01'  # inherits project dates
    assert second['kpis']['total'] == 2


def test_task_json_edit_progress_status_delete(admin, project):
    tid = new_task(admin, project)['task_id']

    j = admin.get(f'/projects/tasks/{tid}/json', headers=AJAX).get_json()
    assert j['title'] == 'Task A' and j['task_status'] == 'pending'

    r = admin.post(f'/projects/tasks/{tid}/edit', json={'title': 'Renamed', 'progress': 100}, headers=admin.headers).get_json()
    assert (r['title'], r['progress'], r['task_status']) == ('Renamed', 100, 'completed')
    assert r['kpis']['completed'] >= 1

    r = admin.post(f'/projects/tasks/{tid}/progress', json={'progress': 40}, headers=admin.headers).get_json()
    assert (r['task_progress'], r['task_status']) == (40, 'in_progress')
    assert set(r) >= {'task_id', 'project_progress', 'kpis', 'message'}

    r = admin.post(f'/projects/tasks/{tid}/status', json={'status': 'completed'}, headers=admin.headers).get_json()
    assert (r['task_status'], r['task_progress']) == ('completed', 100)
    r = admin.post(f'/projects/tasks/{tid}/status', json={'status': 'pending'}, headers=admin.headers).get_json()
    assert (r['task_status'], r['task_progress']) == ('pending', 0)

    r = admin.post(f'/projects/tasks/{tid}/delete', headers=admin.headers).get_json()
    assert r['status'] == 'ok' and 'kpis' in r
    assert admin.get(f'/projects/tasks/{tid}/json', headers=AJAX).status_code == 404


def test_project_progress_is_average_of_tasks(app, admin, project):
    a = new_task(admin, project)['task_id']
    b = new_task(admin, project)['task_id']
    admin.post(f'/projects/tasks/{a}/progress', json={'progress': 100}, headers=admin.headers)
    r = admin.post(f'/projects/tasks/{b}/progress', json={'progress': 50}, headers=admin.headers).get_json()
    assert r['project_progress'] == 75


def test_bad_numbers_do_not_crash(admin, project):
    r = admin.post('/projects/tasks/new', json={'project_id': project, 'title': 'x', 'duration_days': 'abc'},
                   headers=admin.headers)
    assert r.status_code == 200 and r.get_json()['duration_days'] == 1
    tid = r.get_json()['task_id']
    r = admin.post(f'/projects/tasks/{tid}/progress', json={'progress': 'lots'}, headers=admin.headers)
    assert r.status_code == 200 and r.get_json()['task_progress'] == 0


def test_dashboard_renders_single_and_all(admin, project):
    new_task(admin, project)
    assert admin.get(f'/projects/?project_id={project}').status_code == 200
    assert admin.get('/projects/?project_id=all').status_code == 200


def test_non_member_cannot_touch_tasks(app, login, project):
    admin_c = login('admin')
    admin_c.headers = {**csrf_headers(admin_c), **AJAX}
    tid = new_task(admin_c, project)['task_id']
    c = login('staff')  # has projects.* permissions but is not a member of this project
    h = {**csrf_headers(c), **AJAX}
    assert c.get(f'/projects/tasks/{tid}/json', headers=AJAX).status_code == 403
    assert c.post(f'/projects/tasks/{tid}/progress', json={'progress': 90}, headers=h).status_code == 403
    assert c.post('/projects/tasks/new', json={'project_id': project, 'title': 'intruder'}, headers=h).status_code == 403


def test_member_can_update_tasks(app, login, users, project):
    from app_pkg.models import db, Project, User
    with app.app_context():
        p = db.session.get(Project, project)
        p.members.append(db.session.get(User, users['staff']))
        db.session.commit()
    admin_c = login('admin')
    admin_c.headers = {**csrf_headers(admin_c), **AJAX}
    tid = new_task(admin_c, project)['task_id']
    c = login('staff')
    r = c.post(f'/projects/tasks/{tid}/progress', json={'progress': 90}, headers={**csrf_headers(c), **AJAX})
    assert r.status_code == 200 and r.get_json()['task_progress'] == 90

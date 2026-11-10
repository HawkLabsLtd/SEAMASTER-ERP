"""Project/task rules shared by the projects blueprint: access, KPIs, WBS numbering, progress."""
from app_pkg.models import db, Project, ProjectTask, User

STATUSES = ('pending', 'in_progress', 'completed', 'delayed')
STATUS_LABELS = {
    'pending': 'در نوبت اقدام',
    'in_progress': 'در حال اجرا',
    'completed': 'تکمیل شده',
    'delayed': 'دارای تاخیر',
}

# Gantt columns for the current project (Esfand 1404).
GANTT_WEEKS = [
    {'id': 1, 'title': 'هفته اول', 'dates': '۵ الی ۸ اسفند', 'start_day': 5, 'end_day': 8},
    {'id': 2, 'title': 'هفته دوم', 'dates': '۹ الی ۱۵ اسفند', 'start_day': 9, 'end_day': 15},
    {'id': 3, 'title': 'هفته سوم', 'dates': '۱۶ الی ۲۲ اسفند', 'start_day': 16, 'end_day': 22},
    {'id': 4, 'title': 'هفته چهارم', 'dates': '۲۳ الی ۲۷ اسفند', 'start_day': 23, 'end_day': 27},
]


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# --- access -----------------------------------------------------------------

def accessible_projects(user):
    """Admins see all projects; others see projects they're a member of, manage, or have tasks in."""
    if not user:
        return []
    if user.role == 'admin':
        return Project.query.order_by(Project.id.desc()).all()
    assigned = user.assigned_projects.all()
    managed = Project.query.filter(Project.manager_name == user.name).all() if user.name else []
    task_project_ids = db.session.query(ProjectTask.project_id).filter(
        (ProjectTask.assignee_user_id == user.id) | (ProjectTask.assignee_name == user.name)
    ).distinct()
    with_tasks = Project.query.filter(Project.id.in_(task_project_ids)).all()
    return list({p.id: p for p in assigned + managed + with_tasks}.values())


def can_access_project(user, project):
    if not user or not project:
        return False
    if user.role == 'admin':
        return True
    return project.id in {p.id for p in accessible_projects(user)}


# --- KPIs -------------------------------------------------------------------

def is_done(t):
    return (t.progress or 0) >= 100 or t.status == 'completed'


def task_counts(tasks):
    return {
        'total': len(tasks),
        'completed': sum(1 for t in tasks if is_done(t)),
        'in_progress': sum(1 for t in tasks if 0 < (t.progress or 0) < 100 or t.status == 'in_progress'),
        'pending': sum(1 for t in tasks if (t.progress or 0) == 0 and t.status == 'pending'),
        'delayed': sum(1 for t in tasks if t.status == 'delayed'),
    }


def kpi_payload(project):
    """KPIs returned to the dashboard's JavaScript after every task change."""
    return {**task_counts(project.tasks), 'project_progress': project.progress}


def wbs_sort_key(t):
    return [t.project_id or 0] + [int(p) for p in (t.wbs or '').split('.') if p.isdigit()]


def assignee_workload(tasks):
    workload = {}
    for t in tasks:
        row = workload.setdefault(t.assignee_name or 'نامشخص', {'total': 0, 'completed': 0, 'in_progress': 0})
        row['total'] += 1
        if is_done(t):
            row['completed'] += 1
        elif (t.progress or 0) > 0 or t.status == 'in_progress':
            row['in_progress'] += 1
    return workload


class AllProjectsView:
    """Stands in for a Project when the dashboard shows every accessible project at once."""
    id = 'all'
    title = 'همه پروژه‌ها (نمای تجمیعی کل فعالیت‌ها)'
    manager_name = 'کلیه مدیران و مسئولین اقدامات'
    description = 'مشاهده، فیلتر و مرتب‌سازی یکپارچه فعالیت‌های تمامی پروژه‌ها بر اساس افراد و مسئولین'
    status = 'in_progress'
    members = []

    def __init__(self, projects, tasks):
        starts = [p.start_date_shamsi for p in projects if p.start_date_shamsi]
        ends = [p.end_date_shamsi for p in projects if p.end_date_shamsi]
        self.code = f'{len(projects)} پروژه'
        self.start_date_shamsi = min(starts) if starts else '1404/01/01'
        self.end_date_shamsi = max(ends) if ends else '1404/12/29'
        self.progress = round(sum(p.progress or 0 for p in projects) / len(projects)) if projects else 0
        self.tasks = tasks


def ensure_default_project():
    """Import data/projects/current_pm.xlsx, or create an empty default project, when no project exists yet."""
    from app_pkg.services.pm_ingest import ingest_current_pm, DEFAULT_PROJECT
    try:
        project, _ = ingest_current_pm()
        if project:
            return project
    except Exception:
        db.session.rollback()
    project = Project(
        title=DEFAULT_PROJECT['title'],
        code=DEFAULT_PROJECT['code'],
        manager_name=DEFAULT_PROJECT['manager'],
        start_date_shamsi=DEFAULT_PROJECT['start'],
        end_date_shamsi=DEFAULT_PROJECT['end'],
        status='in_progress',
        progress=0,
    )
    db.session.add(project)
    db.session.commit()
    return project


# --- projects ---------------------------------------------------------------

def unique_project_code(code):
    if not code:
        code = f'PRJ-1404-{Project.query.count() + 1:02d}'
    if not Project.query.filter_by(code=code).first():
        return code
    suffix = 1
    while Project.query.filter_by(code=f'{code}-{suffix}').first():
        suffix += 1
    return f'{code}-{suffix}'


# --- tasks ------------------------------------------------------------------

def next_wbs(project):
    """Next top-level WBS code: '1.N' after the highest existing '1.x'."""
    highest = 0
    for t in project.tasks:
        parts = (t.wbs or '').split('.')
        if len(parts) >= 2 and parts[1].isdigit():
            highest = max(highest, int(parts[1]))
    return f'1.{highest + 1}'


def set_progress(task, value):
    """Set progress (clamped 0-100) and derive the status from it."""
    task.progress = max(0, min(100, to_int(value)))
    task.status = 'completed' if task.progress >= 100 else 'in_progress' if task.progress > 0 else 'pending'


def set_status(task, status):
    """Set status and keep progress consistent with it. Unknown statuses are ignored."""
    if status not in STATUSES:
        return False
    task.status = status
    if status == 'completed' and task.progress < 100:
        task.progress = 100
    elif status == 'pending' and task.progress == 100:
        task.progress = 0
    return True


def reconcile_progress_and_status(task):
    if task.progress >= 100 and task.status != 'completed':
        task.status = 'completed'
    elif task.status == 'completed' and task.progress < 100:
        task.progress = 100


def refresh_project_progress(project):
    project.progress = project.calculate_progress()


def assignee_name_for(user_id):
    user = db.session.get(User, to_int(user_id)) if user_id else None
    return user.name if user else None

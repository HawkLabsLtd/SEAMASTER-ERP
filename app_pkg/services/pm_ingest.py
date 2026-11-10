import os
import openpyxl
from app_pkg.models import db, Project, ProjectTask, User
from app_pkg.paths import data_dir

# Metadata for the imported plan; override per import via keyword arguments.
DEFAULT_PROJECT = {
    'code': 'PRJ-001',
    'title': 'پروژه نمونه',
    'manager': 'مدیر پروژه',
    'start': '1404/01/01',
    'end': '1404/12/29',
    'description': 'برنامه پروژه وارد شده از فایل اکسل',
}


def default_plan_path():
    return data_dir('projects', 'current_pm.xlsx')


def ingest_current_pm(filepath=None, **project):
    """
    Ingests a project-plan workbook (default data/projects/current_pm.xlsx) into the
    Project and ProjectTask tables. Rows from 12 on: WBS, title, assignee, predecessor,
    start, end, duration, progress. Matches assignees with existing User records.
    Project metadata comes from DEFAULT_PROJECT, overridden by keyword arguments
    (code, title, manager, start, end, description).
    """
    filepath = filepath or default_plan_path()
    meta = {**DEFAULT_PROJECT, **{k: v for k, v in project.items() if v}}
    if not os.path.exists(filepath):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alt_path = os.path.join(base_dir, filepath)
        if os.path.exists(alt_path):
            filepath = alt_path
        else:
            return None, f"File {filepath} not found"

    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active

        proj_code = meta['code']
        proj_title = meta['title']
        proj_start = meta['start']
        proj_end = meta['end']
        proj_manager = meta['manager']

        # Check for existing project or create new
        project = Project.query.filter_by(code=proj_code).first()
        if not project:
            project = Project(
                code=proj_code,
                title=proj_title,
                start_date_shamsi=proj_start,
                end_date_shamsi=proj_end,
                manager_name=proj_manager,
                description=meta['description'],
                status='in_progress',
                progress=0
            )
            db.session.add(project)
            db.session.commit()
        else:
            project.title = proj_title
            project.start_date_shamsi = proj_start
            project.end_date_shamsi = proj_end

        # Map users by (partial) name
        all_users = User.query.all()
        user_map = {}
        for u in all_users:
            user_map[u.name.strip()] = u.id

        tasks_created = 0
        tasks_updated = 0

        # Scan rows starting from row 12 onwards (header is at row 11)
        for r_idx in range(12, ws.max_row + 1):
            wbs_val = ws.cell(row=r_idx, column=1).value
            if wbs_val is None:
                continue

            wbs_str = str(wbs_val).strip()
            # Skip top parent category row '1' if it has no assignee/dates
            if wbs_str == '1' and ws.cell(row=r_idx, column=3).value is None:
                continue

            title_val = ws.cell(row=r_idx, column=2).value or ''
            title_str = str(title_val).strip()
            if not title_str or title_str == '-':
                continue

            assignee_val = ws.cell(row=r_idx, column=3).value or ''
            assignee_str = str(assignee_val).strip()

            pred_val = ws.cell(row=r_idx, column=4).value or ''
            pred_str = str(pred_val).strip() if pred_val else None

            start_val = ws.cell(row=r_idx, column=5).value or proj_start
            start_str = str(start_val).strip()

            end_val = ws.cell(row=r_idx, column=6).value or proj_end
            end_str = str(end_val).strip()

            dur_val = ws.cell(row=r_idx, column=7).value
            try:
                duration = int(float(dur_val)) if dur_val is not None else 1
            except Exception:
                duration = 1

            prog_val = ws.cell(row=r_idx, column=8).value
            try:
                prog_num = int(float(prog_val) * 100) if float(prog_val) <= 1.0 else int(float(prog_val))
            except Exception:
                prog_num = 0

            # Determine task status
            if prog_num >= 100:
                t_status = 'completed'
            elif prog_num > 0:
                t_status = 'in_progress'
            else:
                t_status = 'pending'

            # Find matching user ID
            matched_user_id = None
            if assignee_str:
                for uname, uid in user_map.items():
                    if assignee_str in uname or uname in assignee_str:
                        matched_user_id = uid
                        break

            # Find existing task by WBS and project
            task = ProjectTask.query.filter_by(project_id=project.id, wbs=wbs_str).first()
            if not task:
                task = ProjectTask(
                    project_id=project.id,
                    wbs=wbs_str,
                    title=title_str,
                    assignee_name=assignee_str or None,
                    assignee_user_id=matched_user_id,
                    predecessor=pred_str,
                    start_date_shamsi=start_str,
                    end_date_shamsi=end_str,
                    duration_days=duration,
                    progress=prog_num,
                    status=t_status
                )
                db.session.add(task)
                tasks_created += 1
            else:
                task.title = title_str
                task.assignee_name = assignee_str or None
                if matched_user_id:
                    task.assignee_user_id = matched_user_id
                task.predecessor = pred_str
                task.start_date_shamsi = start_str
                task.end_date_shamsi = end_str
                task.duration_days = duration
                tasks_updated += 1

        db.session.commit()

        # Update overall project progress
        project.progress = project.calculate_progress()
        db.session.commit()

        return project, f"Successfully ingested project {project.code}: {tasks_created} created, {tasks_updated} updated"

    except Exception as e:
        db.session.rollback()
        return None, f"Error ingesting {filepath}: {str(e)}"

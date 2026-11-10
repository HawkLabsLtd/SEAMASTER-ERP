import os
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, url_for, request, redirect, current_app
from sqlalchemy import text
from app_pkg.models import db, Meeting, Resolution, OperationalTask
from app_pkg.utils.dates_fa import (
    to_farsi_digits,
    format_jalali_datetime,
    format_jalali_weekday_dm,
)

from app_pkg.auth import require_permissions, require_roles
from app_pkg.paths import data_dir
bp = Blueprint('main_bp', __name__)

@bp.route('/', endpoint='index')
@require_permissions('dashboard.view')
def index():
    total_meetings = Meeting.query.count()
    total_resolutions = Resolution.query.count()
    counts = {
        'pending': Resolution.query.filter_by(status='pending').count(),
        'approved': Resolution.query.filter_by(status='approved').count(),
        'in_progress': Resolution.query.filter_by(status='in_progress').count(),
        'completed': Resolution.query.filter_by(status='completed').count(),
    }
    overdue = Resolution.query.filter(
        Resolution.due_date.isnot(None),
        Resolution.due_date < date.today(),
        Resolution.status != 'completed'
    ).count()
    today_g = date.today()
    day_start = datetime.combine(today_g, datetime.min.time())
    try:
        from flask import request
        up_page = max(int(request.args.get('up_page', 1)), 1)
        open_page = max(int(request.args.get('open_page', 1)), 1)
        past_page = max(int(request.args.get('past_page', 1)), 1)
        closed_page = max(int(request.args.get('closed_page', 1)), 1)
    except Exception:
        up_page = open_page = past_page = closed_page = 1
    PAGE_SIZE_MEETINGS = 5
    PAGE_SIZE_RESOLUTIONS = 5
    q_up = Meeting.query.filter(Meeting.scheduled_at >= day_start).order_by(Meeting.scheduled_at.asc())
    upcoming_total = q_up.count()
    upcoming_meetings = q_up.offset((up_page - 1) * PAGE_SIZE_MEETINGS).limit(PAGE_SIZE_MEETINGS).all()
    up_has_prev = up_page > 1
    up_has_next = (up_page * PAGE_SIZE_MEETINGS) < upcoming_total
    q_open = Resolution.query.filter(Resolution.status != 'completed').order_by(Resolution.created_at.desc())
    open_total = q_open.count()
    open_resolutions = q_open.offset((open_page - 1) * PAGE_SIZE_RESOLUTIONS).limit(PAGE_SIZE_RESOLUTIONS).all()
    open_has_prev = open_page > 1
    open_has_next = (open_page * PAGE_SIZE_RESOLUTIONS) < open_total
    q_past = Meeting.query.filter(Meeting.scheduled_at < day_start).order_by(Meeting.scheduled_at.desc())
    past_total = q_past.count()
    past_meetings = q_past.offset((past_page - 1) * PAGE_SIZE_MEETINGS).limit(PAGE_SIZE_MEETINGS).all()
    past_has_prev = past_page > 1
    past_has_next = (past_page * PAGE_SIZE_MEETINGS) < past_total
    q_closed = Resolution.query.filter(Resolution.status == 'completed').order_by(Resolution.updated_at.desc())
    closed_total = q_closed.count()
    closed_resolutions = q_closed.offset((closed_page - 1) * PAGE_SIZE_RESOLUTIONS).limit(PAGE_SIZE_RESOLUTIONS).all()
    closed_has_prev = closed_page > 1
    closed_has_next = (closed_page * PAGE_SIZE_RESOLUTIONS) < closed_total
    today_g = date.today()
    start_days = 7 * 12
    start_date = today_g - timedelta(days=start_days - 1)
    activity = {}
    meetings = db.session.execute(text("SELECT DATE(scheduled_at) AS d, COUNT(*) AS c FROM meeting WHERE DATE(scheduled_at) BETWEEN :sd AND :td GROUP BY DATE(scheduled_at)"), { 'sd': start_date, 'td': today_g }).mappings().all()
    for row in meetings:
        activity.setdefault(row['d'], {'meetings': 0, 'resolutions': 0, 'actions': 0})
        activity[row['d']]['meetings'] = int(row['c'])
    resolutions = db.session.execute(text("SELECT DATE(created_at) AS d, COUNT(*) AS c FROM resolution WHERE DATE(created_at) BETWEEN :sd AND :td GROUP BY DATE(created_at)"), { 'sd': start_date, 'td': today_g }).mappings().all()
    for row in resolutions:
        activity.setdefault(row['d'], {'meetings': 0, 'resolutions': 0, 'actions': 0})
        activity[row['d']]['resolutions'] = int(row['c'])
    audits = db.session.execute(text("SELECT DATE(created_at) AS d, COUNT(*) AS c FROM audit_log WHERE DATE(created_at) BETWEEN :sd AND :td GROUP BY DATE(created_at)"), { 'sd': start_date, 'td': today_g }).mappings().all()
    for row in audits:
        activity.setdefault(row['d'], {'meetings': 0, 'resolutions': 0, 'actions': 0})
        activity[row['d']]['actions'] = int(row['c'])
    weeks = []
    day_iter = start_date
    for w in range(12):
        week = []
        for d in range(7):
            dt = day_iter
            key = dt.isoformat()
            counts_day = activity.get(key, {'meetings': 0, 'resolutions': 0, 'actions': 0})
            total = counts_day['meetings'] + counts_day['resolutions'] + counts_day['actions']
            week.append({
                'date': key,
                'total': total,
                'meetings': counts_day['meetings'],
                'resolutions': counts_day['resolutions'],
                'actions': counts_day['actions'],
            })
            day_iter = day_iter + timedelta(days=1)
        weeks.append(week)
    end_date = today_g + timedelta(days=14)
    upcoming_due = (
        Resolution.query
        .filter(Resolution.due_date.isnot(None))
        .filter(Resolution.due_date >= today_g)
        .filter(Resolution.due_date <= end_date)
        .filter(Resolution.status != 'completed')
        .order_by(Resolution.due_date.asc())
        .limit(8)
        .all()
    )
    deadline_alerts = []
    for r in upcoming_due:
        try:
            days_left = (r.due_date - today_g).days if r.due_date else None
        except Exception:
            days_left = None
        deadline_alerts.append({'res': r, 'days_left': days_left})
    selected_date_str = None
    meetings_on_day = []
    resolutions_on_day = []
    try:
        from flask import request
        selected_date_str = request.args.get('selected_date')
        if selected_date_str:
            sel = date.fromisoformat(selected_date_str)
            d_start = datetime.combine(sel, datetime.min.time())
            d_end = datetime.combine(sel, datetime.max.time())
            meetings_on_day = Meeting.query.filter(Meeting.scheduled_at >= d_start, Meeting.scheduled_at <= d_end).order_by(Meeting.scheduled_at.asc()).all()
            resolutions_on_day = Resolution.query.filter(Resolution.created_at >= d_start, Resolution.created_at <= d_end).order_by(Resolution.created_at.asc()).all()
    except Exception:
        pass
    return render_template('index.html',
                           now_dt=datetime.now(),
                           datetime=datetime,
                           total_meetings=total_meetings,
                           total_resolutions=total_resolutions,
                           counts=counts,
                           overdue=overdue,
                           upcoming_meetings=upcoming_meetings,
                           up_page=up_page,
                           up_has_prev=up_has_prev,
                           up_has_next=up_has_next,
                           open_resolutions=open_resolutions,
                           open_page=open_page,
                           open_has_prev=open_has_prev,
                           open_has_next=open_has_next,
                           past_meetings=past_meetings,
                           past_page=past_page,
                           past_has_prev=past_has_prev,
                           past_has_next=past_has_next,
                           closed_resolutions=closed_resolutions,
                           closed_page=closed_page,
                           closed_has_prev=closed_has_prev,
                           closed_has_next=closed_has_next,
                           activity_weeks=weeks,
                           deadline_alerts=deadline_alerts,
                           selected_date_str=selected_date_str,
                           meetings_on_day=meetings_on_day,
                           resolutions_on_day=resolutions_on_day)

@bp.route('/events', endpoint='events_calendar')
@require_permissions('events.view')
def events_calendar():
    from app_pkg.utils.events import load_events_from_csv
    from flask import current_app
    events_dir = data_dir('events')
    try:
        from flask import request
        q_year = request.args.get('year')
        q_month = request.args.get('month')
        year = int(q_year) if q_year else date.today().year
        month = int(q_month) if q_month else date.today().month
        hide_past = (str(request.args.get('hide_past')).lower() in ['1','true','yes'])
        dow_param = request.args.get('dow')
        active_dow = int(dow_param) if dow_param is not None else None
    except Exception:
        year = date.today().year
        month = date.today().month
        hide_past = False
        active_dow = None
    preferred = os.path.join(events_dir, f'events-{year}-{str(month).rjust(2, "0")}.csv')
    events = []
    if os.path.exists(preferred):
        events = load_events_from_csv(preferred)
    else:
        for name in os.listdir(events_dir):
            if name.endswith('.csv'):
                events.extend(load_events_from_csv(os.path.join(events_dir, name)))
    events_by_day = {}
    for ev in events:
        if ev['start'].year == year and ev['start'].month == month:
            d = ev['start'].day
            events_by_day.setdefault(d, []).append(ev)
    if hide_past:
        today_g = date.today()
        filtered = {}
        for d, lst in events_by_day.items():
            keep = []
            for ev in lst:
                try:
                    if ev['start'].date() >= today_g:
                        keep.append(ev)
                except Exception:
                    keep.append(ev)
            if keep:
                filtered[d] = keep
        events_by_day = filtered
    import calendar as pycalendar
    cal = pycalendar.Calendar(firstweekday=5)
    weeks = cal.monthdayscalendar(year, month)
    weekdays_fa = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    from app_pkg.utils.dates_fa import gregorian_to_jalali
    jy, jm, _ = gregorian_to_jalali(year, month, 1)
    jalali_months_fa = {
        1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
        7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
    }
    month_title = f"{jalali_months_fa.get(jm, jm)} {to_farsi_digits(jy)}"
    if active_dow is not None:
        wd_map = {}
        for week in weeks:
            for idx, dn in enumerate(week):
                if dn:
                    wd_map[dn] = idx
        filtered = {}
        for d, lst in events_by_day.items():
            if wd_map.get(d) == active_dow:
                filtered[d] = lst
        events_by_day = filtered
    for d, lst in events_by_day.items():
        lst.sort(key=lambda e: e['start'])
    prev_y = year
    prev_m = month - 1
    if prev_m == 0:
        prev_m = 12
        prev_y -= 1
    next_y = year
    next_m = month + 1
    if next_m == 13:
        next_m = 1
        next_y += 1
    return render_template('events/agenda.html',
                           weeks=weeks,
                           events_by_day=events_by_day,
                           weekdays_fa=weekdays_fa,
                           month_title=month_title,
                           active_dow=active_dow,
                           hide_past=hide_past,
                           year=year,
                           month=month,
                           prev_year=prev_y,
                           prev_month=prev_m,
                           next_year=next_y,
                           next_month=next_m,
                           to_farsi_digits=to_farsi_digits,
                           format_jalali_datetime=format_jalali_datetime)

@bp.route('/events/upload', methods=['POST'])
@require_roles('manager', 'admin')
def events_upload():
    y = request.form.get('year')
    m = request.form.get('month')
    try:
        year = int(y) if y else None
        month = int(m) if m else None
    except Exception:
        year = None
        month = None
    file = request.files.get('csv_file')
    if not file or not file.filename.lower().endswith('.csv'):
        return redirect(url_for('main_bp.events_calendar', year=year or date.today().year, month=month or date.today().month))
    events_dir = data_dir('events')
    try:
        os.makedirs(events_dir, exist_ok=True)
    except Exception:
        pass
    target_year = year or date.today().year
    target_month = month or date.today().month
    fname = f"events-{target_year}-{str(target_month).rjust(2,'0')}.csv"
    path = os.path.join(events_dir, fname)
    file.save(path)
    return redirect(url_for('main_bp.events_calendar', year=target_year, month=target_month))

@bp.route('/today', endpoint='today_view')
@require_permissions('today.view')
def today_view():
    today_g = date.today()
    try:
        from flask import current_app
        from app_pkg.utils.events import load_events_from_csv
        events_dir = data_dir('events')
        year = today_g.year
        month = today_g.month
        preferred = os.path.join(events_dir, f'events-{year}-{str(month).rjust(2, "0")}.csv')
        events = []
        if os.path.exists(events_dir):
            if os.path.exists(preferred):
                events = load_events_from_csv(preferred)
            else:
                for name in os.listdir(events_dir):
                    if name.endswith('.csv'):
                        events.extend(load_events_from_csv(os.path.join(events_dir, name)))
        local_tz = datetime.now().astimezone().tzinfo
        day_start = datetime.combine(today_g, datetime.min.time()).replace(tzinfo=local_tz)
        day_end = datetime.combine(today_g, datetime.max.time()).replace(tzinfo=local_tz)
        todays_events = []
        for ev in events:
            try:
                start = ev.get('start')
                if isinstance(start, str):
                    try:
                        start_dt = datetime.fromisoformat(start)
                    except Exception:
                        start_dt = None
                        # If not ISO, skip safely
                else:
                    start_dt = start
                if start_dt is None:
                    continue
                if getattr(start_dt, 'tzinfo', None):
                    start_dt = start_dt.astimezone(local_tz)
                else:
                    start_dt = start_dt.replace(tzinfo=local_tz)
                if day_start <= start_dt <= day_end:
                    todays_events.append(ev)
            except Exception:
                try:
                    if ev.get('start') and ev.get('start').date() == today_g:
                        todays_events.append(ev)
                except Exception:
                    continue
        todays_meetings = Meeting.query.filter(
            Meeting.scheduled_at >= day_start,
            Meeting.scheduled_at <= day_end
        ).order_by(Meeting.scheduled_at.asc()).all()
        todays_resolutions = Resolution.query.filter(
            Resolution.due_date == today_g,
            Resolution.status != 'completed'
        ).order_by(Resolution.updated_at.desc()).all()
        todays_operations = OperationalTask.query.filter(
            OperationalTask.due_date == today_g,
            OperationalTask.status != 'completed'
        ).order_by(OperationalTask.updated_at.desc()).all()
        now_dt = datetime.now()
        return render_template('today.html',
                               todays_events=todays_events,
                               todays_resolutions=todays_resolutions,
                               todays_operations=todays_operations,
                               todays_meetings=todays_meetings,
                               now_dt=now_dt,
                               format_jalali_datetime=format_jalali_datetime,
                               format_jalali_weekday_dm=format_jalali_weekday_dm,
                               to_farsi_digits=to_farsi_digits)
    except Exception:
        current_app.logger.exception('today view failed')
        raise  # rendered by the app's 500 handler; never send tracebacks to the browser

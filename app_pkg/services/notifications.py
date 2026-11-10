from app_pkg.models import OperationalTask, MemberBirthday
from app_pkg.utils.dates_fa import gregorian_to_jalali, to_farsi_digits
from datetime import datetime, timedelta, date

def get_user_notifications(user):
    """
    Returns a list of notifications for the given user.
    Each notification is a dict:
    {
        'title': str,
        'message': str,
        'category': 'warning' | 'info' | 'success' | 'danger',
        'link': str,
        'icon': str
    }
    """
    notifications = []
    
    # 1. Operational Tasks (Due soon)
    # Tasks assigned to user or if user is admin/manager check all? 
    # Usually notifications are personal.
    if user:
        # Tasks assigned to me, pending, due within 3 days
        today = date.today()
        upcoming = today + timedelta(days=3)
        
        tasks_due = OperationalTask.query.filter(
            OperationalTask.assigned_to_user_id == user.id,
            OperationalTask.status == 'pending',
            OperationalTask.due_date <= upcoming,
            OperationalTask.due_date >= today
        ).all()
        
        overdue = OperationalTask.query.filter(
            OperationalTask.assigned_to_user_id == user.id,
            OperationalTask.status == 'pending',
            OperationalTask.due_date < today
        ).all()
        
        for t in overdue:
            notifications.append({
                'title': 'تاخیر در وظیفه',
                'message': f'وظیفه "{t.title}" سررسید شده است!',
                'category': 'danger',
                'link': f'/tasks/dashboard',
                'icon': 'fas fa-exclamation-triangle'
            })
            
        for t in tasks_due:
            notifications.append({
                'title': 'سررسید نزدیک',
                'message': f'وظیفه "{t.title}" به زودی سررسید می‌شود.',
                'category': 'warning',
                'link': f'/tasks/dashboard',
                'icon': 'fas fa-clock'
            })

    # 2. Member Birthdays (Strictly ONLY for Sys Admin: user.role == 'admin')
    if user and user.role == 'admin':
        now = datetime.now()
        jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
        
        # Check Today
        birthdays_today = MemberBirthday.query.filter_by(birth_month=jm, birth_day=jd).count()
        if birthdays_today > 0:
            notifications.append({
                'title': 'تولد اعضا',
                'message': f'امروز تولد {to_farsi_digits(birthdays_today)} نفر از اعضا است.',
                'category': 'info',
                'link': '/members/birthdays',
                'icon': 'fas fa-birthday-cake'
            })
        
    return notifications

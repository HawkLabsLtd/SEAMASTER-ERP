from flask import Blueprint, redirect, url_for, flash, abort
from datetime import datetime
import os
from app_pkg.models import db, User, Meeting, Resolution
from app_pkg.auth import require_roles

bp = Blueprint('seed_bp', __name__)

# Schema setup and admin creation live in app_pkg/db_setup.py (flask init-db / create-admin).

@bp.route('/seed/fa', methods=['POST'])
@require_roles('admin')
def seed_fa():
    # Drops every table. Only allowed when explicitly enabled (dev/demo machines).
    if os.getenv('ALLOW_DESTRUCTIVE_SEED') != '1':
        abort(403)
    db.drop_all()
    db.create_all()
    users = [
        User(name='مدیر', email='admin@example.com'),
        User(name='علی رضا', email='ali@example.com'),
        User(name='سارا نور', email='sara@example.com'),
    ]
    db.session.add_all(users)
    db.session.commit()
    m1 = Meeting(title='جلسه راهبردی فصل چهارم', scheduled_at=datetime.utcnow(), description='برنامه‌ریزی فصلی و بررسی شاخص‌ها.')
    m2 = Meeting(title='هماهنگی عملیات', scheduled_at=datetime.utcnow(), description='هماهنگی هفتگی عملیات و بررسی موانع.')
    db.session.add_all([m1, m2])
    db.session.commit()
    r1 = Resolution(meeting_id=m1.id, title='نهایی‌سازی تخصیص بودجه', description='تهیه نسخه نهایی تقسیم بودجه.', status='pending')
    r2 = Resolution(meeting_id=m1.id, title='تأیید برنامه جذب نیرو', description='بررسی و تصویب نقشه راه جذب.', status='pending')
    r3 = Resolution(meeting_id=m2.id, title='کاهش عقب‌ماندگی تیکت‌ها', description='پاکسازی ۶۰٪ عقب‌ماندگی تا پایان ماه.', status='in_progress', progress=35)
    db.session.add_all([r1, r2, r3])
    db.session.commit()
    flash('داده‌های فارسی بارگذاری شد.', 'success')
    return redirect(url_for('main_bp.index'))

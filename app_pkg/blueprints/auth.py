import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, current_app, session
from werkzeug.security import check_password_hash, generate_password_hash

from app_pkg.models import db, User, AuthToken, LoginAttempt
from app_pkg.security import request_is_https
from app_pkg.auth import safe_next_url, get_user_home_url
from app_pkg.utils.sanitize import sanitize_input, validate_email

bp = Blueprint('auth_bp', __name__)

def create_auth_token(user_id, hours=12):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=hours)
    at = AuthToken(user_id=user_id, token=token, expires_at=expires_at)
    db.session.add(at)
    db.session.commit()
    return token, expires_at

# Failed-login throttling (stored in the DB so every worker process sees it).
LOGIN_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_ACCOUNT = 5
MAX_FAILURES_PER_IP = 30
LOGIN_FAILED_MSG = 'نام کاربری یا رمز عبور نادرست است.'


def _failures_since(key, since):
    return LoginAttempt.query.filter(LoginAttempt.key == key, LoginAttempt.created_at >= since).count()


def _record_failure(*keys):
    now = datetime.utcnow()
    LoginAttempt.query.filter(LoginAttempt.created_at < now - timedelta(days=1)).delete()
    db.session.add_all([LoginAttempt(key=k, created_at=now) for k in keys])
    db.session.commit()


def _password_matches(user, password):
    if not user.password_hash:
        return False
    # Older code ran passwords through sanitize_input (strips <...> and whitespace) before
    # hashing/checking, so accept that form too.
    return any(check_password_hash(user.password_hash, candidate)
               for candidate in dict.fromkeys([password, password.strip(), sanitize_input(password) or '']))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ident = sanitize_input(request.form.get('email', '')).strip()
        email_lower = ident.lower() if ident else ''
        password = request.form.get('password', '')
        next_url = safe_next_url(sanitize_input(request.args.get('next') or request.form.get('next') or ''))
        if not ident or not password:
            flash('ایمیل یا نام کاربری و رمز عبور مورد نیاز است.', 'danger')
            return redirect(url_for('auth_bp.login', next=next_url))

        ip_key = f'ip:{request.remote_addr or "unknown"}'
        user_key = f'user:{email_lower}'
        since = datetime.utcnow() - LOGIN_WINDOW
        if (_failures_since(user_key, since) >= MAX_FAILURES_PER_ACCOUNT
                or _failures_since(ip_key, since) >= MAX_FAILURES_PER_IP):
            flash('تلاش‌های ورود بیش از حد. لطفاً ۱۵ دقیقه دیگر تلاش کنید.', 'danger')
            return redirect(url_for('auth_bp.login', next=next_url))

        # Case-insensitive and prefix lookup
        user = (
            User.query.filter(User.email.ilike(email_lower)).first() or
            User.query.filter(User.username.ilike(email_lower)).first() or
            User.query.filter(User.name.ilike(ident)).first() or
            User.query.filter(User.email.ilike(f"{email_lower}@%")).first()
        )

        # Same message whether the account is unknown or the password is wrong (no user enumeration).
        if not user or not _password_matches(user, password):
            _record_failure(ip_key, user_key)
            flash(LOGIN_FAILED_MSG, 'danger')
            return redirect(url_for('auth_bp.login', next=next_url))

        if not user.is_active or not user.is_login_enabled:
            flash('حساب کاربری شما غیرفعال است. با مدیر سیستم تماس بگیرید.', 'danger')
            return redirect(url_for('auth_bp.login', next=next_url))

        LoginAttempt.query.filter_by(key=user_key).delete()
        token, expires_at = create_auth_token(user.id)
        session.clear()  # new session on login (prevents session fixation)
        session['user_id'] = user.id
        session.permanent = True

        target_url = next_url
        if not target_url or target_url in ('/', url_for('main_bp.index'), url_for('auth_bp.login')):
            target_url = get_user_home_url(user)

        resp = make_response(redirect(target_url))
        max_age = int((expires_at - datetime.utcnow()).total_seconds())
        resp.set_cookie('seamaster_auth', token, max_age=max_age, path='/', httponly=True, samesite='Lax', secure=request_is_https())
        flash('ورود با موفقیت انجام شد.', 'success')
        return resp
    next_url = request.args.get('next') or url_for('main_bp.index')
    return render_template('login.html', next_url=next_url)

@bp.route('/logout')
def logout():
    token = request.cookies.get('seamaster_auth')
    if token:
        try:
            at = AuthToken.query.filter_by(token=token).first()
            if at:
                db.session.delete(at)
                db.session.commit()
        except Exception:
            pass
    from flask import session
    session.pop('user_id', None)
    resp = make_response(redirect(url_for('auth_bp.login')))
    resp.delete_cookie('seamaster_auth', path='/')
    flash('خروج انجام شد.', 'info')
    return resp

@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Accounts are created by admins/managers under /users unless self-registration is explicitly enabled.
    if not current_app.config.get('ALLOW_SELF_REGISTRATION'):
        flash('ثبت‌نام آزاد غیرفعال است. برای دریافت حساب کاربری با مدیر سیستم تماس بگیرید.', 'warning')
        return redirect(url_for('auth_bp.login'))
    if request.method == 'POST':
        name = sanitize_input(request.form.get('name', ''))
        email = validate_email(request.form.get('email', ''))
        password = sanitize_input(request.form.get('password', ''))
        if not name or not email or not password:
            flash('همه فیلدها الزامی است.', 'danger')
            return redirect(url_for('auth_bp.register'))
        if User.query.filter(User.email == email).first():
            flash('این ایمیل قبلاً ثبت شده است.', 'danger')
            return redirect(url_for('auth_bp.register'))
        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('ثبت‌نام انجام شد. لطفاً وارد شوید.', 'success')
    return render_template('register.html')

@bp.route('/profile', methods=['GET', 'POST'])
def profile():
    from flask import g
    user = getattr(g, 'current_user', None)
    if not user:
        return redirect(url_for('auth_bp.login'))
    
    if request.method == 'POST':
        name = sanitize_input(request.form.get('name', '')).strip()
        email = sanitize_input(request.form.get('email', '')).strip() or None
        if not name:
            flash('نام الزامی است.', 'danger')
            return redirect(url_for('auth_bp.profile'))
        
        # Check duplicate email if changed
        if email and email.lower() != (user.email or '').lower():
            existing = User.query.filter(User.email == email.lower()).first()
            if existing and existing.id != user.id:
                flash('این ایمیل قبلاً توسط کاربر دیگری ثبت شده است.', 'danger')
                return redirect(url_for('auth_bp.profile'))
        
        user.name = name
        user.email = email
        db.session.commit()
        flash('مشخصات با موفقیت ذخیره شد.', 'success')
        return redirect(url_for('auth_bp.profile'))
        
    return render_template('profile.html', user=user)

@bp.route('/profile/password', methods=['POST'])
def change_password():
    from flask import g
    user = getattr(g, 'current_user', None)
    if not user:
        return redirect(url_for('auth_bp.login'))
    
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash('تکمیل تمامی فیلدها الزامی است.', 'danger')
        return redirect(url_for('auth_bp.profile'))

    if new_password != confirm_password:
        flash('رمز عبور جدید با تکرار آن یکسان نیست.', 'danger')
        return redirect(url_for('auth_bp.profile'))

    if len(new_password) < 6:
        flash('رمز عبور جدید باید حداقل ۶ کاراکتر باشد.', 'danger')
        return redirect(url_for('auth_bp.profile'))

    if not user.password_hash or not check_password_hash(user.password_hash, current_password):
        flash('رمز عبور فعلی نادرست است.', 'danger')
        return redirect(url_for('auth_bp.profile'))

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash('رمز عبور با موفقیت تغییر یافت.', 'success')
    return redirect(url_for('auth_bp.profile'))

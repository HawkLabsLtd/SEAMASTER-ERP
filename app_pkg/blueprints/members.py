from flask import Blueprint, render_template, request, redirect, url_for, flash
from app_pkg.models import db, MemberBirthday
from app_pkg.utils.dates_fa import gregorian_to_jalali, to_farsi_digits
from app_pkg.auth import require_roles
from datetime import datetime, timedelta
import pandas as pd

bp = Blueprint('members', __name__, url_prefix='/members')

@bp.route('/birthdays')
@require_roles('admin')
def birthdays():
    # Calculate Today and Tomorrow in Jalali
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    
    jy_now, jm_now, jd_now = gregorian_to_jalali(now.year, now.month, now.day)
    jy_tom, jm_tom, jd_tom = gregorian_to_jalali(tomorrow.year, tomorrow.month, tomorrow.day)
    
    # Query for Today
    birthdays_today = MemberBirthday.query.filter_by(birth_month=jm_now, birth_day=jd_now).all()
    
    # Query for Tomorrow
    birthdays_tomorrow = MemberBirthday.query.filter_by(birth_month=jm_tom, birth_day=jd_tom).all()
    
    # Format current date for display
    today_fa = f"{to_farsi_digits(jy_now)}/{to_farsi_digits(jm_now)}/{to_farsi_digits(jd_now)}"
    
    return render_template('members/birthdays.html',
                           birthdays_today=birthdays_today,
                           birthdays_tomorrow=birthdays_tomorrow,
                           today_fa=today_fa)

@bp.route('/upload', methods=['GET', 'POST'])
@require_roles('admin')
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        replace = request.form.get('replace') == 'on'
        
        if not file or file.filename == '':
            flash('لطفاً یک فایل انتخاب کنید', 'danger')
            return redirect(request.url)
        
        if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            try:
                # Read Excel without header first to find the header row
                df_raw = pd.read_excel(file, header=None)
                
                # Find header row index
                header_idx = -1
                for idx, row in df_raw.iterrows():
                    row_str = " ".join([str(x) for x in row.values])
                    if "نام" in row_str and "تولد" in row_str:
                        header_idx = idx
                        break
                
                if header_idx != -1:
                    # Reload with correct header
                    file.seek(0)
                    df = pd.read_excel(file, header=header_idx)
                else:
                    # Fallback to default
                    file.seek(0)
                    df = pd.read_excel(file)
                
                # normalize columns: strip, lower
                df.columns = [str(c).strip().lower() for c in df.columns]
                
                col_map = {
                    'name': 'full_name', 'nam': 'full_name', 'full_name': 'full_name', 
                    'نام': 'full_name', 'نام و نام خانوادگی': 'full_name', 'نام خانوادگی': 'full_name',
                    
                    'phone': 'phone_number', 'mobile': 'phone_number', 'cell': 'phone_number', 
                    'موبایل': 'phone_number', 'تلفن': 'phone_number', 'شماره تماس': 'phone_number', 'شماره موبایل': 'phone_number',
                    
                    'birthday': 'birth_raw', 'birthdate': 'birth_raw', 'tavalod': 'birth_raw', 
                    'تاریخ تولد': 'birth_raw', 'تولد': 'birth_raw', 'تاریخ': 'birth_raw'
                }
                
                # Identify valid columns
                found_map = {}
                for col in df.columns:
                    if col in col_map:
                        found_map[col] = col_map[col]
                
                if 'full_name' not in found_map.values():
                     flash('ستون "نام" (Name) در فایل یافت نشد.', 'danger')
                     return redirect(request.url)

                if replace:
                    MemberBirthday.query.delete()
                    db.session.commit()
                    flash('لیست قبلی حذف شد.', 'warning')

                count = 0
                for _, row in df.iterrows():
                    # Extract data
                    full_name = None
                    phone = None
                    birth_raw = None
                    
                    for col, target in found_map.items():
                        val = str(row[col]).strip()
                        if val == 'nan': continue
                        if target == 'full_name': full_name = val
                        elif target == 'phone_number': phone = val
                        elif target == 'birth_raw': birth_raw = val
                    
                    if not full_name: continue
                    
                    # Parse Date (Try to guess format: YYYY/MM/DD or DD/MM/YYYY or YYYY-MM-DD)
                    # We need month and day for the query
                    b_month = None
                    b_day = None
                    
                    if birth_raw:
                        # Cleaning
                        clean_date = birth_raw.replace('-', '/').replace('.', '/')
                        parts = clean_date.split('/')
                        if len(parts) == 3:
                            try:
                                # Assume Jalali YYYY/MM/DD usually
                                p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
                                if p1 > 1000: # YYYY/MM/DD
                                    b_month = p2
                                    b_day = p3
                                elif p3 > 1000: # DD/MM/YYYY
                                    b_month = p2
                                    b_day = p1
                            except:
                                pass
                    
                    member = MemberBirthday(
                        full_name=full_name,
                        phone_number=phone,
                        birth_raw=birth_raw,
                        birth_month=b_month,
                        birth_day=b_day
                    )
                    db.session.add(member)
                    count += 1
                
                db.session.commit()
                flash(f'{count} عضو با موفقیت بارگذاری شدند.', 'success')
                return redirect(url_for('members.birthdays'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'خطا در پردازش فایل: {e}', 'danger')
                return redirect(request.url)
        else:
            flash('فرمت فایل نامعتبر است. فقط Excel پشتیبانی می‌شود.', 'danger')
            return redirect(request.url)
            
    return render_template('members/upload.html')

"""
HR Dashboard Blueprint - Flask + Chart.js implementation
Uses SQLite database for employee data
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import pandas as pd
from app_pkg.models import db, Employee

from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.uploads import save_upload, UploadError
bp = Blueprint('hr_dashboard', __name__, url_prefix='/hr')

from app_pkg.paths import data_dir
DATA_DIR = data_dir('hr')


def calculate_age(birth_date_str):
    """Calculate age from Jalali birth date string"""
    if not birth_date_str or pd.isna(birth_date_str):
        return None
    try:
        # Parse Jalali date (e.g., "1354/05/07")
        parts = str(birth_date_str).strip().split('/')
        if len(parts) == 3:
            birth_year = int(parts[0])
            current_jalali_year = 1403  # Approximate current Jalali year
            return current_jalali_year - birth_year
    except:
        pass
    return None


def import_hr_data_from_csv(filepath):
    """Import HR data from CSV file"""
    df = pd.read_csv(filepath)
    count = 0
    
    with db.session.no_autoflush:
        for _, row in df.iterrows():
            personnel_code = str(row.get('کد پرسنلی کارمند', '')).strip()
            if not personnel_code or personnel_code == 'nan':
                continue
            
            # Check if employee exists by personnel_code
            emp = Employee.query.filter_by(personnel_code=personnel_code).first()
            if not emp:
                # Also try to find by full name
                first_name = str(row.get('نام کارمند', '')).strip()
                last_name = str(row.get('نام خانوادگی کارمند', '')).strip()
                full_name = f"{first_name} {last_name}".strip()
                emp = Employee.query.filter_by(full_name=full_name).first()
            
            if not emp:
                emp = Employee(
                    personnel_code=personnel_code,
                    full_name=f"{row.get('نام کارمند', '')} {row.get('نام خانوادگی کارمند', '')}".strip()
                )
                db.session.add(emp)
            else:
                # Update personnel_code if not set
                if not emp.personnel_code:
                    emp.personnel_code = personnel_code
            
            # Update fields
            emp.first_name = str(row.get('نام کارمند', '')).strip() or emp.first_name
            emp.last_name = str(row.get('نام خانوادگی کارمند', '')).strip() or emp.last_name
            emp.full_name = f"{emp.first_name or ''} {emp.last_name or ''}".strip() or emp.full_name
            emp.location = str(row.get('محل استخدام', '')).strip() or emp.location
            emp.marital_status = str(row.get('وضعیت تأهل وضعیت تاهل', '')).strip() or emp.marital_status
            emp.education = str(row.get('مقطع تحصیلی مدرک تحصیلی', '')).strip() or emp.education
            emp.birth_date = str(row.get('تاریخ تولد کارمند', '')).strip() or emp.birth_date
            emp.employment_type = str(row.get('عنوان نوع استخدام', '')).strip() or emp.employment_type
            emp.consultant_type = str(row.get('نوع مشاور', '')).strip() or emp.consultant_type
            emp.gender = str(row.get('جنسیت کارمند', '')).strip() or emp.gender
            count += 1
    
    db.session.commit()
    return count


def import_people_data_from_excel(filepath):
    """Import people/organizational data from Excel file"""
    df = pd.read_excel(filepath)
    count = 0
    
    # Forward-fill the department column (hierarchical structure)
    df['نام واحد'] = df['نام واحد'].ffill()
    
    with db.session.no_autoflush:
        for _, row in df.iterrows():
            full_name = str(row.get('نام و نام  خانوادگی', '')).strip()
            if not full_name or full_name == 'nan' or pd.isna(row.get('نام و نام  خانوادگی')):
                continue
            
            # Try to find by full name
            emp = Employee.query.filter_by(full_name=full_name).first()
            if not emp:
                # Create new entry
                emp = Employee(full_name=full_name)
                db.session.add(emp)
            
            # Update organizational fields
            dept = str(row.get('نام واحد', '')).strip()
            pos = str(row.get('سمت', '')).strip()
            ctype = str(row.get('نوع قرارداد', '')).strip()
            cdur = str(row.get('مدت قرارداد', '')).strip()
            
            if dept and dept != 'nan':
                emp.department = dept
            if pos and pos != 'nan':
                emp.position = pos
            if ctype and ctype != 'nan':
                emp.contract_type = ctype
            if cdur and cdur != 'nan':
                emp.contract_duration = cdur
            count += 1
    
    db.session.commit()
    return count


def get_kpis():
    """Calculate KPIs from database"""
    total = Employee.query.count()
    male = Employee.query.filter_by(gender='مذکر').count()
    female = Employee.query.filter_by(gender='مؤنث').count()
    
    # Calculate average age
    employees = Employee.query.filter(Employee.birth_date.isnot(None)).all()
    ages = [calculate_age(e.birth_date) for e in employees]
    ages = [a for a in ages if a is not None]
    avg_age = sum(ages) / len(ages) if ages else 0
    
    # Count departments
    dept_count = db.session.query(Employee.department).filter(Employee.department.isnot(None)).distinct().count()
    
    return {
        'total': total,
        'male': male,
        'female': female,
        'avg_age': round(avg_age, 1),
        'departments': dept_count
    }


def get_chart_data():
    """Get data for charts"""
    # Gender distribution
    gender_data = db.session.query(
        Employee.gender, db.func.count(Employee.id)
    ).filter(Employee.gender.isnot(None)).group_by(Employee.gender).all()
    
    # Education distribution
    education_data = db.session.query(
        Employee.education, db.func.count(Employee.id)
    ).filter(Employee.education.isnot(None)).group_by(Employee.education).all()
    
    # Employment type distribution
    emp_type_data = db.session.query(
        Employee.employment_type, db.func.count(Employee.id)
    ).filter(Employee.employment_type.isnot(None)).group_by(Employee.employment_type).all()
    
    # Department distribution
    dept_data = db.session.query(
        Employee.department, db.func.count(Employee.id)
    ).filter(Employee.department.isnot(None)).group_by(Employee.department).all()
    
    return {
        'gender': {r[0]: r[1] for r in gender_data},
        'education': {r[0]: r[1] for r in education_data},
        'employment_type': {r[0]: r[1] for r in emp_type_data},
        'department': dict(sorted([(r[0], r[1]) for r in dept_data], key=lambda x: x[1], reverse=True)[:10])
    }


def get_filter_options():
    """Get unique values for filter dropdowns"""
    locations = db.session.query(Employee.location).filter(Employee.location.isnot(None)).distinct().all()
    emp_types = db.session.query(Employee.employment_type).filter(Employee.employment_type.isnot(None)).distinct().all()
    education = db.session.query(Employee.education).filter(Employee.education.isnot(None)).distinct().all()
    departments = db.session.query(Employee.department).filter(Employee.department.isnot(None)).distinct().all()
    
    return {
        'locations': [r[0] for r in locations],
        'employment_types': [r[0] for r in emp_types],
        'education': [r[0] for r in education],
        'departments': [r[0] for r in departments]
    }


@bp.route('/')
@require_permissions('hr.view')
def index():
    """Main HR dashboard page"""
    kpis = get_kpis()
    chart_data = get_chart_data()
    filters = get_filter_options()
    
    # Get employees for table (limited)
    employees = Employee.query.limit(50).all()
    
    return render_template('hr_dashboard/index.html',
                           kpis=kpis,
                           chart_data=chart_data,
                           filters=filters,
                           employees=employees)


@bp.route('/api/employees')
@require_permissions('hr.view')
def get_employees():
    """API endpoint for filtered employee data"""
    query = Employee.query
    
    location = request.args.get('location')
    emp_type = request.args.get('employment_type')
    education = request.args.get('education')
    department = request.args.get('department')
    search = request.args.get('search')
    
    if location:
        query = query.filter_by(location=location)
    if emp_type:
        query = query.filter_by(employment_type=emp_type)
    if education:
        query = query.filter_by(education=education)
    if department:
        query = query.filter_by(department=department)
    if search:
        query = query.filter(Employee.full_name.ilike(f'%{search}%'))
    
    employees = query.limit(100).all()
    
    # Calculate KPIs for filtered data
    total = len(employees)
    male = len([e for e in employees if e.gender == 'مذکر'])
    female = len([e for e in employees if e.gender == 'مؤنث'])
    ages = [calculate_age(e.birth_date) for e in employees if e.birth_date]
    ages = [a for a in ages if a]
    avg_age = round(sum(ages) / len(ages), 1) if ages else 0
    depts = len(set([e.department for e in employees if e.department]))
    
    return jsonify({
        'employees': [{
            'id': e.id,
            'full_name': e.full_name,
            'position': e.position,
            'department': e.department,
            'gender': e.gender,
            'education': e.education,
            'employment_type': e.employment_type
        } for e in employees],
        'kpis': {
            'total': total,
            'male': male,
            'female': female,
            'avg_age': avg_age,
            'departments': depts
        }
    })


@bp.route('/import', methods=['POST'])
@require_roles('manager', 'admin')
def import_data():
    """Handle file upload and import"""
    hr_count = 0
    people_count = 0
    errors = []

    # HR Data file (CSV or Excel)
    file = request.files.get('hr_file')
    if file and file.filename:
        try:
            filepath = save_upload(file, DATA_DIR, {'csv', 'xlsx', 'xls'})
            if not filepath.lower().endswith('.csv'):
                csv_path = os.path.splitext(filepath)[0] + '.csv'
                pd.read_excel(filepath).to_csv(csv_path, index=False)
                filepath = csv_path
            hr_count = import_hr_data_from_csv(filepath)
        except UploadError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"HR Data: {str(e)}")

    # People/Org file (Excel)
    file = request.files.get('people_file')
    if file and file.filename:
        try:
            people_count = import_people_data_from_excel(save_upload(file, DATA_DIR, {'xlsx', 'xls'}))
        except UploadError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"People Data: {str(e)}")

    if hr_count > 0:
        flash(f'{hr_count} رکورد از فایل HR وارد شد.', 'success')
    if people_count > 0:
        flash(f'{people_count} رکورد از فایل People وارد شد.', 'success')
    if errors:
        flash(f'خطا: {", ".join(errors)}', 'danger')
    if hr_count == 0 and people_count == 0 and not errors:
        flash('هیچ فایلی انتخاب نشده یا فایل‌ها خالی هستند.', 'warning')
    
    return redirect(url_for('hr_dashboard.index'))


@bp.route('/init', methods=['POST'])
@require_roles('admin')
def init_data():
    """Initialize database with existing CSV/Excel files"""
    hr_count = 0
    people_count = 0
    
    try:
        # Clear existing employees to avoid conflicts
        Employee.query.delete()
        db.session.commit()
        print("Cleared existing employee data")
        
        # Import HR-DATA-1.csv
        hr_path = os.path.join(DATA_DIR, 'HR-DATA-1.csv')
        if os.path.exists(hr_path):
            hr_count = import_hr_data_from_csv(hr_path)
            print(f"Imported {hr_count} HR records")
        
        # Import people.xlsx
        people_path = os.path.join(DATA_DIR, 'people.xlsx')
        if os.path.exists(people_path):
            people_count = import_people_data_from_excel(people_path)
            print(f"Imported {people_count} People records")
        
        flash(f'داده‌ها وارد شد: {hr_count} کارمند از HR, {people_count} از People', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا: {str(e)}', 'danger')
        print(f"Import error: {e}")
    
    return redirect(url_for('hr_dashboard.index'))


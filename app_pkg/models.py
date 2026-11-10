from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    username = db.Column(db.String(100), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='staff')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_login_enabled = db.Column(db.Boolean, nullable=False, default=True)
    permissions = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<User {self.name}>"


class Meeting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resolutions = db.relationship('Resolution', backref='meeting', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Meeting {self.title} at {self.scheduled_at:%Y-%m-%d}>"


class Resolution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meeting.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)

    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id], lazy=True)

    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id], lazy=True)

    due_date = db.Column(db.Date, nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Resolution {self.title} ({self.status})>"


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    payload = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class AuthToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CouncilMeeting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=True)  # Meeting number
    date = db.Column(db.Date, nullable=True, index=True)
    type = db.Column(db.String(50), nullable=False, index=True)  # 'presidency' or 'representatives'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resolutions = db.relationship('CouncilResolution', backref='meeting', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CouncilMeeting {self.number} ({self.type})>"


class CouncilResolution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('council_meeting.id'), nullable=False, index=True)
    
    topic = db.Column(db.Text, nullable=True)
    responsible = db.Column(db.String(200), nullable=True)
    progress = db.Column(db.Integer, default=0)  # 0-100
    status = db.Column(db.String(100), nullable=True, index=True)
    due_date = db.Column(db.String(100), nullable=True)  # Storing as string for now as Excel might have text
    description = db.Column(db.Text, nullable=True)
    letter_number = db.Column(db.String(100), nullable=True)
    referrals = db.Column(db.String(200), nullable=True)
    
    row_index = db.Column(db.Integer, nullable=True) # To keep order if needed

    def __repr__(self):
        return f"<CouncilResolution {self.id} - {self.topic[:20]}...>"


class OperationalTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_user_id], lazy=True)
    due_date = db.Column(db.Date, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    def __repr__(self):
        return f"<OperationalTask {self.title} ({self.status})>"


class MoU(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=True, index=True)
    letter_no = db.Column(db.String(100), nullable=True)
    incoming_no = db.Column(db.String(100), nullable=True)
    sender = db.Column(db.Text, nullable=True)
    receiver = db.Column(db.Text, nullable=True)
    subject = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(50), nullable=True, index=True)
    
    # New fields for workflow and analysis
    status = db.Column(db.String(50), default='New', index=True)  # New, Under Review, Signed, Archived
    sender_type = db.Column(db.String(100), default='Other') # University, Company, Government, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MoU {self.subject[:20]}...>"


class MemberBirthday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    phone_number = db.Column(db.String(50), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    birth_month = db.Column(db.Integer, nullable=True, index=True)
    birth_day = db.Column(db.Integer, nullable=True, index=True)
    birth_raw = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def __repr__(self):
        return f"<MemberBirthday {self.full_name}>"


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    personnel_code = db.Column(db.String(50), nullable=True, unique=True, index=True)  # کد پرسنلی
    first_name = db.Column(db.String(100), nullable=True)  # نام
    last_name = db.Column(db.String(100), nullable=True)  # نام خانوادگی
    full_name = db.Column(db.String(200), nullable=False)  # نام کامل
    
    # From HR-DATA
    location = db.Column(db.String(100), nullable=True)  # محل استخدام
    marital_status = db.Column(db.String(20), nullable=True)  # وضعیت تأهل
    education = db.Column(db.String(50), nullable=True)  # مقطع تحصیلی
    birth_date = db.Column(db.String(20), nullable=True)  # تاریخ تولد (Jalali)
    employment_type = db.Column(db.String(50), nullable=True)  # عنوان نوع استخدام
    consultant_type = db.Column(db.String(100), nullable=True)  # نوع مشاور
    gender = db.Column(db.String(10), nullable=True)  # جنسیت
    
    # From people.xlsx
    department = db.Column(db.String(200), nullable=True, index=True)  # نام واحد
    position = db.Column(db.String(200), nullable=True)  # سمت
    contract_type = db.Column(db.String(50), nullable=True)  # نوع قرارداد
    contract_duration = db.Column(db.String(50), nullable=True)  # مدت قرارداد
    
    # For Org Chart
    unit = db.Column(db.String(200), nullable=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True, index=True)
    manager = db.relationship('Employee', remote_side=[id], backref='subordinates')
    
    # Extra Info
    mobile = db.Column(db.String(50), nullable=True)
    photo_path = db.Column(db.String(200), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


    def __repr__(self):
        return f"<Employee {self.full_name} ({self.position})>"


project_members = db.Table(
    'project_members',
    db.Column('project_id', db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    code = db.Column(db.String(50), nullable=True, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)
    manager_name = db.Column(db.String(150), nullable=True)
    start_date_shamsi = db.Column(db.String(20), nullable=True)
    end_date_shamsi = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(30), nullable=False, default='in_progress', index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('ProjectTask', backref='project', lazy=True, cascade="all, delete-orphan", order_by="ProjectTask.wbs")
    members = db.relationship('User', secondary='project_members', backref=db.backref('assigned_projects', lazy='dynamic'), lazy='select')

    def calculate_progress(self):
        if not self.tasks:
            return 0
        total = sum(t.progress for t in self.tasks)
        return int(total / len(self.tasks))

    def __repr__(self):
        return f"<Project {self.title}>"


class ProjectTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    wbs = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    assignee_name = db.Column(db.String(150), nullable=True, index=True)
    assignee_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    assignee_user = db.relationship('User', foreign_keys=[assignee_user_id], lazy=True)
    predecessor = db.Column(db.String(100), nullable=True)
    start_date_shamsi = db.Column(db.String(20), nullable=True)
    end_date_shamsi = db.Column(db.String(20), nullable=True)
    duration_days = db.Column(db.Integer, nullable=True, default=1)
    progress = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ProjectTask {self.wbs} - {self.title[:20]}>"



class LoginAttempt(db.Model):
    """Failed logins, shared by all worker processes; used for throttling."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(200), nullable=False, index=True)  # 'ip:<addr>' or 'user:<identifier>'
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

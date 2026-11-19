"""
NyayaDesk - SQLAlchemy Relational Models
Defines complete data layer: users, courts, courtrooms, cases,
case parties, hearings, documents, orders, payments, notifications,
audit logs, approval requests, and hearing reminders.
"""

import json
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints in SQLite."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

DEFAULT_PREFS = {
    "sms": True,
    "whatsapp": True,
    "email": True,
    "in_app": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00"
}


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # Roles: government, registrar, judge, clerk, lawyer, litigant, police
    role = db.Column(db.String(32), nullable=False, index=True)
    # Statuses: active, pending_gov, pending_registrar, rejected, suspended
    status = db.Column(db.String(32), default='active', nullable=False, index=True)
    court_id = db.Column(db.Integer, db.ForeignKey('courts.id'), nullable=True)
    id_proof_no = db.Column(db.String(100), nullable=True) # bar council no. / employee ID / aadhaar-last4 etc.
    designation = db.Column(db.String(100), nullable=True)
    avatar_color = db.Column(db.String(20), default='#15284F')
    language_pref = db.Column(db.String(10), default='en') # en, te, hi
    notification_prefs = db.Column(db.Text, default=json.dumps(DEFAULT_PREFS), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    # Relationships
    court = db.relationship('Court', backref='affiliated_users', foreign_keys=[court_id])
    approver = db.relationship('User', remote_side=[id], backref='approved_users')
    
    cases_filed = db.relationship('Case', foreign_keys='Case.filed_by', backref='filer', lazy='dynamic')
    cases_judged = db.relationship('Case', foreign_keys='Case.judge_id', backref='judge', lazy='dynamic')
    hearings_presided = db.relationship('Hearing', foreign_keys='Hearing.judge_id', backref='presiding_judge', lazy='dynamic')
    orders_issued = db.relationship('Order', foreign_keys='Order.judge_id', backref='issuing_judge', lazy='dynamic')
    notifications = db.relationship('Notification', foreign_keys='Notification.user_id', backref='recipient', lazy='dynamic')
    approval_requests = db.relationship('ApprovalRequest', foreign_keys='ApprovalRequest.applicant_user_id', backref='applicant', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_notification_prefs(self):
        """Return parsed notification preference dictionary."""
        try:
            if not self.notification_prefs:
                return DEFAULT_PREFS.copy()
            prefs = json.loads(self.notification_prefs)
            merged = DEFAULT_PREFS.copy()
            merged.update(prefs)
            return merged
        except Exception:
            return DEFAULT_PREFS.copy()

    def set_notification_prefs(self, prefs_dict):
        """Serialize and persist updated notification preferences."""
        merged = self.get_notification_prefs()
        merged.update(prefs_dict)
        self.notification_prefs = json.dumps(merged)

    @property
    def is_authenticated(self):
        return True

    def __repr__(self):
        return f"<User {self.email} [{self.role} / {self.status}]>"


class Court(db.Model):
    __tablename__ = 'courts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), nullable=False) # District / High / Supreme / Family / Magistrate
    city = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(64), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)

    courtrooms = db.relationship('Courtroom', backref='court', cascade='all, delete-orphan', lazy='dynamic')
    cases = db.relationship('Case', backref='court', lazy='dynamic')

    def __repr__(self):
        return f"<Court {self.code} - {self.name}>"


class Courtroom(db.Model):
    __tablename__ = 'courtrooms'

    id = db.Column(db.Integer, primary_key=True)
    court_id = db.Column(db.Integer, db.ForeignKey('courts.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False) # e.g. Courtroom 1, Chief Justice Court
    capacity = db.Column(db.Integer, default=50, nullable=False)

    hearings = db.relationship('Hearing', backref='courtroom', lazy='dynamic')

    def __repr__(self):
        return f"<Courtroom {self.name} (Court ID: {self.court_id})>"


class Case(db.Model):
    __tablename__ = 'cases'

    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(64), unique=True, nullable=False, index=True) # e.g. CIV/2026/00045
    title = db.Column(db.String(255), nullable=False, index=True)
    # Types: Civil, Criminal, Family, Property, Cheque Bounce, Bail, Writ, Consumer
    case_type = db.Column(db.String(50), nullable=False, index=True)
    # Statuses: Filed, Scrutiny, Registered, Hearing, Reserved, Judgment, Disposed, Appealed
    status = db.Column(db.String(50), default='Filed', nullable=False, index=True)
    # Priority: Low, Normal, High, Urgent
    priority = db.Column(db.String(20), default='Normal', nullable=False)
    court_id = db.Column(db.Integer, db.ForeignKey('courts.id'), nullable=False, index=True)
    judge_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    filed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    filed_on = db.Column(db.Date, default=date.today, nullable=False)
    description = db.Column(db.Text, nullable=True)
    next_hearing_date = db.Column(db.Date, nullable=True, index=True)

    parties = db.relationship('CaseParty', backref='case', cascade='all, delete-orphan', lazy='dynamic')
    hearings = db.relationship('Hearing', backref='case', cascade='all, delete-orphan', lazy='dynamic')
    documents = db.relationship('Document', backref='case', cascade='all, delete-orphan', lazy='dynamic')
    orders = db.relationship('Order', backref='case', cascade='all, delete-orphan', lazy='dynamic')
    payments = db.relationship('Payment', backref='case', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f"<Case {self.case_number} - {self.title}>"


class CaseParty(db.Model):
    __tablename__ = 'case_parties'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    # Party Types: Petitioner, Respondent, Witness, Accused, Complainant
    party_type = db.Column(db.String(50), nullable=False)
    advocate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref='case_affiliations')
    advocate = db.relationship('User', foreign_keys=[advocate_id], backref='represented_parties')

    def __repr__(self):
        return f"<CaseParty {self.name} ({self.party_type}) Case:{self.case_id}>"


class Hearing(db.Model):
    __tablename__ = 'hearings'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    courtroom_id = db.Column(db.Integer, db.ForeignKey('courtrooms.id'), nullable=True, index=True)
    judge_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    purpose = db.Column(db.String(150), nullable=False)
    # Status: Scheduled, Completed, Adjourned, Cancelled
    status = db.Column(db.String(32), default='Scheduled', nullable=False, index=True)
    adjournment_reason = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Attendance Tracking via simulated inbound reply
    attendance_status = db.Column(db.String(32), default='Unconfirmed', nullable=False) # Unconfirmed, Confirmed, Excused
    attendance_confirmed_at = db.Column(db.DateTime, nullable=True)

    reminders = db.relationship('HearingReminder', backref='hearing', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f"<Hearing Case:{self.case_id} Date:{self.scheduled_at} [{self.status}] Attendance:{self.attendance_status}>"


class HearingReminder(db.Model):
    __tablename__ = 'hearing_reminders'

    id = db.Column(db.Integer, primary_key=True)
    hearing_id = db.Column(db.Integer, db.ForeignKey('hearings.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reminder_type = db.Column(db.String(32), nullable=False, index=True) # 7_days, 1_day, 2_hours, manual
    channel = db.Column(db.String(32), nullable=False) # SMS, WhatsApp, Email, In-App
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(32), default='Delivered', nullable=False)

    recipient = db.relationship('User', backref='hearing_reminders_received')

    __table_args__ = (
        db.UniqueConstraint('hearing_id', 'user_id', 'reminder_type', name='uq_hearing_user_remtype'),
    )

    def __repr__(self):
        return f"<HearingReminder Hearing:{self.hearing_id} User:{self.user_id} Type:{self.reminder_type}>"


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(255), nullable=False)
    doc_type = db.Column(db.String(64), nullable=False, index=True) # Petition, Affidavit, Evidence, Vakalatnama, Order, ID Proof
    version = db.Column(db.Integer, default=1, nullable=False)
    visibility = db.Column(db.String(32), default='Public', nullable=False) # Public, Confidential, Bench Only
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploader = db.relationship('User', backref='uploaded_files')

    def __repr__(self):
        return f"<Document {self.filename} ({self.doc_type})>"


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    judge_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # Order Types: Interim, Final, Judgment, Notice
    order_type = db.Column(db.String(50), nullable=False)
    signed_hash = db.Column(db.String(128), nullable=True)
    verification_code = db.Column(db.String(32), nullable=True, index=True)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def judge(self):
        return self.issuing_judge

    def __repr__(self):
        return f"<Order {self.title} ({self.order_type})>"


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    purpose = db.Column(db.String(120), nullable=False) # Court Fee, Fine, Certified Copy, Bail Bond
    status = db.Column(db.String(32), default='Completed', nullable=False, index=True) # Completed, Pending, Failed, Refunded
    reference = db.Column(db.String(64), unique=True, nullable=False, index=True)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    payer = db.relationship('User', backref='payments_made')

    def __repr__(self):
        return f"<Payment {self.reference} - INR {self.amount}>"


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    channel = db.Column(db.String(32), nullable=False, index=True) # SMS, WhatsApp, Email, In-App
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default='Sent', nullable=False, index=True) # Queued, Sent, Delivered, Failed
    related_case_id = db.Column(db.Integer, db.ForeignKey('cases.id', ondelete='SET NULL'), nullable=True, index=True)
    scheduled_for = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Delivery tracking & gateway integration
    recipient_contact = db.Column(db.String(120), nullable=True)
    provider = db.Column(db.String(50), default='DEMO_GATEWAY', nullable=True)
    fallback_from = db.Column(db.String(32), nullable=True)
    reminder_type = db.Column(db.String(32), nullable=True, index=True)
    hearing_id = db.Column(db.Integer, db.ForeignKey('hearings.id', ondelete='SET NULL'), nullable=True, index=True)

    related_case = db.relationship('Case', backref='case_notifications')
    hearing = db.relationship('Hearing', backref='hearing_notifications')

    def __repr__(self):
        return f"<Notification to User:{self.user_id} via {self.channel} [{self.status}]>"


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True) # LOGIN, FAILED_LOGIN, LOGOUT, REGISTER, APPROVAL, REJECTION
    entity = db.Column(db.String(64), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref='audit_actions')

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.entity} by User:{self.user_id}>"


class ApprovalRequest(db.Model):
    __tablename__ = 'approval_requests'

    id = db.Column(db.Integer, primary_key=True)
    applicant_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    requested_role = db.Column(db.String(32), nullable=False, index=True) # judge, registrar, clerk
    court_name = db.Column(db.String(150), nullable=True)
    details_json = db.Column(db.Text, nullable=True) # JSON containing metadata
    # Status: Pending, Approved, Rejected
    status = db.Column(db.String(32), default='Pending', nullable=False, index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_approvals')

    def __repr__(self):
        return f"<ApprovalRequest Applicant:{self.applicant_user_id} Role:{self.requested_role} Status:{self.status}>"


class AILog(db.Model):
    __tablename__ = 'ai_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    feature = db.Column(db.String(64), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False, index=True) # gemini, demo
    model = db.Column(db.String(64), nullable=False)
    prompt_version = db.Column(db.String(16), default='1.0', nullable=False)
    prompt_tokens = db.Column(db.Integer, default=0)
    completion_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    latency_ms = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(32), default='success', index=True) # success, failed, cached, throttled, disabled
    fallback_used = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('ai_logs', lazy='dynamic'))

    def __repr__(self):
        return f"<AILog {self.feature} via {self.provider}:{self.model} [{self.status}] {self.latency_ms:.1f}ms>"


class AICache(db.Model):
    __tablename__ = 'ai_response_cache'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    feature = db.Column(db.String(64), nullable=False)
    provider = db.Column(db.String(32), nullable=False)
    model = db.Column(db.String(64), nullable=False)
    response_json = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at


class AISetting(db.Model):
    __tablename__ = 'ai_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def __repr__(self):
        return f"<AISetting {self.key}={self.value}>"


class PrecedentLibrary(db.Model):
    __tablename__ = 'precedent_library'

    id = db.Column(db.Integer, primary_key=True)
    citation = db.Column(db.String(120), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    court_name = db.Column(db.String(150), nullable=False, default="High Court of Judicature")
    bench = db.Column(db.String(150), nullable=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    case_type = db.Column(db.String(64), nullable=False, index=True)
    statutory_sections = db.Column(db.Text, nullable=True)
    headnote = db.Column(db.Text, nullable=False)
    key_passages = db.Column(db.Text, nullable=False)
    full_judgment_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Precedent {self.citation} - {self.title}>"


class HearingTranscription(db.Model):
    __tablename__ = 'hearing_transcriptions'

    id = db.Column(db.Integer, primary_key=True)
    hearing_id = db.Column(db.Integer, db.ForeignKey('hearings.id'), nullable=False, index=True)
    audio_filename = db.Column(db.String(255), nullable=True)
    raw_transcript = db.Column(db.Text, nullable=False)
    minutes_summary = db.Column(db.Text, nullable=True)
    action_items_json = db.Column(db.Text, nullable=True)
    suggested_next_hearing = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(32), default='Draft', nullable=False, index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hearing = db.relationship('Hearing', foreign_keys=[hearing_id], backref=db.backref('transcriptions', lazy='dynamic'))
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f"<HearingTranscription Hearing:{self.hearing_id} Status:{self.status}>"


class AIEvaluation(db.Model):
    __tablename__ = 'ai_evaluations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    feature = db.Column(db.String(64), nullable=False, index=True)
    rating = db.Column(db.String(16), nullable=False, index=True) # helpful, wrong, unsafe
    feedback_text = db.Column(db.Text, nullable=True)
    prompt = db.Column(db.Text, nullable=True)
    response_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(32), nullable=True)
    model = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('evaluations', lazy='dynamic'))

    def __repr__(self):
        return f"<AIEvaluation {self.feature} [{self.rating}] by User:{self.user_id}>"




def apply_schema_migrations(engine):
    """
    Ensure SQLite schema columns exist on existing databases
    without needing manual alembic migration migrations.
    """
    with engine.connect() as conn:
        tables = [r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        # 1. users
        if 'users' in tables:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
            if 'notification_prefs' not in cols:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN notification_prefs TEXT DEFAULT '{\"sms\": true, \"whatsapp\": true, \"email\": true, \"in_app\": true, \"quiet_hours_enabled\": false, \"quiet_hours_start\": \"22:00\", \"quiet_hours_end\": \"07:00\"}'")

        # 2. hearings
        if 'hearings' in tables:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(hearings)").fetchall()]
            if 'attendance_status' not in cols:
                conn.exec_driver_sql("ALTER TABLE hearings ADD COLUMN attendance_status VARCHAR(32) DEFAULT 'Unconfirmed'")
            if 'attendance_confirmed_at' not in cols:
                conn.exec_driver_sql("ALTER TABLE hearings ADD COLUMN attendance_confirmed_at DATETIME")

        # 3. notifications
        if 'notifications' in tables:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(notifications)").fetchall()]
            if 'recipient_contact' not in cols:
                conn.exec_driver_sql("ALTER TABLE notifications ADD COLUMN recipient_contact VARCHAR(120)")
            if 'provider' not in cols:
                conn.exec_driver_sql("ALTER TABLE notifications ADD COLUMN provider VARCHAR(50) DEFAULT 'DEMO_GATEWAY'")
            if 'fallback_from' not in cols:
                conn.exec_driver_sql("ALTER TABLE notifications ADD COLUMN fallback_from VARCHAR(32)")
            if 'reminder_type' not in cols:
                conn.exec_driver_sql("ALTER TABLE notifications ADD COLUMN reminder_type VARCHAR(32)")
            if 'hearing_id' not in cols:
                conn.exec_driver_sql("ALTER TABLE notifications ADD COLUMN hearing_id INTEGER REFERENCES hearings(id)")

        conn.commit()

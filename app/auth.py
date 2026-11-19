"""
NyayaDesk - Authentication & Role-Based Access Control (RBAC) System
Provides secure login, role-specific onboarding, approval queues,
rate limiting, password reset with simulated OTP, and audit logging.
"""

import os
import json
import random
import time
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, flash, g, render_template, current_app, abort, jsonify
from werkzeug.utils import secure_filename
from app.models import db, User, Court, ApprovalRequest, Notification, AuditLog

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# In-memory rate limiting tracker: { identifier: [timestamp, timestamp, ...] }
FAILED_LOGIN_ATTEMPTS = {}
LOCKOUT_SECONDS = 60
MAX_FAILED_ATTEMPTS = 5

class AnonymousUser:
    id = None
    email = None
    role = 'public'
    status = 'active'
    full_name = 'Public Citizen'
    is_authenticated = False


def get_current_user():
    """Retrieve the authenticated User or AnonymousUser."""
    if 'user_id' not in session:
        return AnonymousUser()
    
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return AnonymousUser()
    return user


def is_rate_limited(identifier):
    """Check if identifier (IP or username) is rate limited due to repeated failures."""
    now = time.time()
    attempts = FAILED_LOGIN_ATTEMPTS.get(identifier, [])
    # Keep attempts within recent window
    recent_attempts = [t for t in attempts if now - t < LOCKOUT_SECONDS]
    FAILED_LOGIN_ATTEMPTS[identifier] = recent_attempts
    return len(recent_attempts) >= MAX_FAILED_ATTEMPTS


def record_failed_attempt(identifier):
    """Record a failed login attempt timestamp."""
    now = time.time()
    if identifier not in FAILED_LOGIN_ATTEMPTS:
        FAILED_LOGIN_ATTEMPTS[identifier] = []
    FAILED_LOGIN_ATTEMPTS[identifier].append(now)


def clear_failed_attempts(identifier):
    """Clear failed attempts upon successful login."""
    if identifier in FAILED_LOGIN_ATTEMPTS:
        del FAILED_LOGIN_ATTEMPTS[identifier]


def login_user(user, remember=False):
    """Establish authenticated session."""
    session.clear()
    session['user_id'] = user.id
    session['role'] = user.role
    session['status'] = user.status
    session['full_name'] = user.full_name
    session['email'] = user.email
    session['_csrf_token'] = secrets.token_hex(16)
    if remember:
        session.permanent = True
    g.current_user = user

    # Write audit log
    log = AuditLog(
        user_id=user.id,
        action="LOGIN_SUCCESS",
        entity="users",
        entity_id=user.id,
        ip=request.remote_addr,
        details=f"User {user.email} authenticated successfully as {user.role} (status: {user.status})"
    )
    db.session.add(log)
    db.session.commit()


def logout_user():
    """Terminate authenticated session."""
    user_id = session.get('user_id')
    if user_id:
        log = AuditLog(
            user_id=user_id,
            action="LOGOUT",
            entity="users",
            entity_id=user_id,
            ip=request.remote_addr,
            details="User logged out"
        )
        db.session.add(log)
        db.session.commit()
    session.clear()
    session['_csrf_token'] = secrets.token_hex(16)


def login_required(f):
    """Enforce authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if not current_user.is_authenticated:
            flash("Please sign in to access this judicial workspace.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        
        # If pending approval, intercept and redirect to pending-approval page
        if current_user.status in ['pending_gov', 'pending_registrar']:
            return redirect(url_for('auth.pending_approval'))
        
        if current_user.status == 'suspended':
            flash("Your judicial account is currently suspended. Please contact the administrator.", "danger")
            logout_user()
            return redirect(url_for('auth.login'))
            
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Enforce strict Role-Based Access Control and active status."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_user = get_current_user()
            if not current_user.is_authenticated:
                flash("Authentication required to access this portal.", "warning")
                return redirect(url_for('auth.login', next=request.url))
            
            # Pending approvals cannot access active dashboards
            if current_user.status in ['pending_gov', 'pending_registrar']:
                return redirect(url_for('auth.pending_approval'))
                
            if current_user.status != 'active':
                flash(f"Account state '{current_user.status}' does not permit portal access.", "danger")
                return redirect(url_for('main.index'))

            if current_user.role not in allowed_roles:
                abort(403)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_dashboard_route_for_role(role):
    """Map role to its primary dashboard endpoint."""
    mapping = {
        'government': 'dashboards.government_dashboard',
        'registrar': 'dashboards.registrar_dashboard',
        'judge': 'dashboards.judge_dashboard',
        'clerk': 'dashboards.clerk_dashboard',
        'lawyer': 'dashboards.lawyer_dashboard',
        'litigant': 'dashboards.litigant_dashboard',
        'police': 'dashboards.police_dashboard'
    }
    return mapping.get(role, 'main.index')


# --------------------------------------------------------------------------
# Auth Routes
# --------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        is_json = request.is_json or request.headers.get('Accept') == 'application/json'
        identifier = request.remote_addr
        if request.is_json and request.json:
            email = str(request.json.get('email', '')).strip().lower()
            password = str(request.json.get('password', ''))
            remember = bool(request.json.get('remember', False))
        else:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            remember = bool(request.form.get('remember'))

        # 1. Rate Limiting Check
        if is_rate_limited(identifier) or is_rate_limited(email):
            # Audit log rate limit breach
            log = AuditLog(
                user_id=None,
                action="RATE_LIMIT_LOCKOUT",
                entity="auth",
                ip=identifier,
                details=f"Rate limit triggered for {email}"
            )
            db.session.add(log)
            db.session.commit()
            msg = "Security Alert: Too many failed login attempts. Temporarily locked for 1 minute. Please wait before retrying."
            if is_json:
                return jsonify({'error': msg}), 429
            flash(msg, "danger")
            return render_template('auth/login.html'), 429

        user = User.query.filter_by(email=email).first()

        # 2. Authentication Check
        if not user or not user.check_password(password):
            record_failed_attempt(identifier)
            record_failed_attempt(email)
            
            # Audit log failed login
            log = AuditLog(
                user_id=user.id if user else None,
                action="FAILED_LOGIN",
                entity="users",
                entity_id=user.id if user else None,
                ip=identifier,
                details=f"Invalid credentials submitted for {email}"
            )
            db.session.add(log)
            db.session.commit()

            if is_rate_limited(identifier) or is_rate_limited(email):
                msg = "Security Alert: Too many failed login attempts. Temporarily locked for 1 minute. Please wait before retrying."
                if is_json:
                    return jsonify({'error': msg}), 429
                flash(msg, "danger")
                return render_template('auth/login.html'), 429

            remaining = MAX_FAILED_ATTEMPTS - len(FAILED_LOGIN_ATTEMPTS.get(identifier, []))
            if remaining > 0:
                err_msg = f"Invalid email or password. ({remaining} attempts remaining before temporary lockout)"
            else:
                err_msg = "Invalid credentials. Account locked for 1 minute."

            if is_json:
                return jsonify({'error': err_msg}), 401
            flash(err_msg, "danger")
            return render_template('auth/login.html'), 401

        # Authentication successful - clear failures
        clear_failed_attempts(identifier)
        clear_failed_attempts(email)

        # 3. Status Validation
        if user.status == 'suspended':
            msg = "Account Suspended: Your access has been revoked by Court Administration."
            if is_json:
                return jsonify({'error': msg}), 403
            flash(msg, "danger")
            return render_template('auth/login.html'), 403

        if user.status in ['pending_gov', 'pending_registrar']:
            login_user(user, remember)
            redir = url_for('auth.pending_approval')
            if is_json:
                return jsonify({'success': True, 'status': user.status, 'redirect': redir, 'redirect_url': redir})
            flash("Your application is currently pending judicial authority approval.", "info")
            return redirect(redir)

        if user.status == 'rejected':
            login_user(user, remember)
            redir = url_for('auth.pending_approval')
            if is_json:
                return jsonify({'success': True, 'status': 'rejected', 'redirect': redir, 'redirect_url': redir})
            flash(f"Application Notice: Your request was declined. Reason: {user.rejection_reason or 'Eligibility criteria not met'}.", "warning")
            return redirect(redir)

        # Active user - proceed to dashboard
        login_user(user, remember)
        flash(f"Welcome back, {user.full_name} ({user.role.capitalize()})", "success")

        target_endpoint = get_dashboard_route_for_role(user.role)
        next_url = request.args.get('next')
        dest_url = next_url if (next_url and next_url.startswith('/') and not next_url.startswith('/auth')) else url_for(target_endpoint)
        
        if is_json:
            return jsonify({'success': True, 'role': user.role, 'status': user.status, 'redirect': dest_url, 'redirect_url': dest_url})

        try:
            return redirect(dest_url)
        except Exception:
            return redirect(url_for('main.index'))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@auth_bp.route('/signup', methods=['GET', 'POST'])
def register():
    courts = Court.query.order_by(Court.name).all()

    if request.method == 'POST':
        is_json = request.is_json or request.headers.get('Accept') == 'application/json'
        data = request.get_json(silent=True) or request.form
        full_name = str(data.get('full_name', '')).strip()
        email = str(data.get('email', '')).strip().lower()
        phone = str(data.get('phone', '')).strip()
        password = str(data.get('password', ''))
        confirm_password = str(data.get('confirm_password', password if is_json else ''))
        role = str(data.get('role', '')).strip().lower()

        # Validation
        errors = []
        if not full_name or len(full_name) < 3:
            errors.append("Full legal name is required (minimum 3 characters).")
        if not email or '@' not in email or '.' not in email:
            errors.append("Please enter a valid official email address.")
        if not phone or len(phone) < 10:
            errors.append("Please provide a valid 10-digit telephone number.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Password confirmation does not match.")
        
        valid_roles = ['judge', 'registrar', 'clerk', 'lawyer', 'litigant', 'police']
        if role not in valid_roles:
            errors.append("Please select a valid judicial role.")

        if User.query.filter_by(email=email).first():
            errors.append("An account with this email address is already registered.")

        # Role-specific fields extraction
        court_id = data.get('court_id')
        court_id = int(court_id) if court_id and str(court_id).isdigit() else None
        court_name_text = data.get('court_name', '')
        id_proof_no = None
        designation = None
        details = {}

        if role in ['judge', 'registrar']:
            designation = str(data.get('designation', '')).strip()
            employee_id = str(data.get('employee_id') or data.get('id_proof_no') or '').strip()
            years_service = str(data.get('years_service', '10 Years')).strip()
            id_proof_no = employee_id

            if not employee_id:
                errors.append("Judicial Employee / Service ID is required.")
            if not designation:
                errors.append("Judicial designation is required.")

            # File upload handling for ID proof
            id_file = request.files.get('id_proof_file')
            stored_file_path = None
            if id_file and id_file.filename:
                # 1. Path traversal check
                if '..' in id_file.filename or '/' in id_file.filename or '\\' in id_file.filename:
                    errors.append("Invalid filename: directory traversal characters are prohibited.")
                # 2. Dangerous executable double extension check
                DANGEROUS_EXTS = {'exe', 'bat', 'cmd', 'sh', 'php', 'py', 'js', 'vbs', 'ps1', 'dll', 'so', 'bin', 'msi'}
                name_parts = [p.lower() for p in id_file.filename.split('.')]
                if any(p in DANGEROUS_EXTS for p in name_parts):
                    errors.append("Prohibited file: executable script/binary extensions are not permitted.")
                # 3. Allowed extensions
                allowed_exts = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'txt'}
                ext = name_parts[-1] if len(name_parts) > 1 else ''
                if ext not in allowed_exts:
                    errors.append(f"Invalid file type '.{ext}'. Authorized formats: PDF, PNG, JPG, DOCX, TXT.")
                else:
                    # 4. Check executable magic bytes
                    head = id_file.read(512)
                    id_file.seek(0)
                    if head.startswith(b'MZ') or head.startswith(b'\x7fELF') or b'<?php' in head or b'<script' in head.lower():
                        errors.append("File rejected: executable binary or malicious script detected.")
                    else:
                        filename = secure_filename(f"{role}_{int(time.time())}_{id_file.filename}")
                        upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'id_proofs')
                        os.makedirs(upload_dir, exist_ok=True)
                        id_file.save(os.path.join(upload_dir, filename))
                        stored_file_path = f"uploads/id_proofs/{filename}"

            details = {
                'employee_id': employee_id,
                'designation': designation,
                'years_service': years_service,
                'court_id': court_id,
                'court_name': court_name_text,
                'id_proof_path': stored_file_path
            }

        elif role == 'lawyer':
            bar_no = str(data.get('bar_registration_no') or data.get('bar_no') or data.get('id_proof_no') or '').strip()
            enroll_year = str(data.get('enrollment_year', '2015')).strip()
            practice_area = str(data.get('practice_area', 'Civil & Constitutional')).strip()
            id_proof_no = bar_no
            designation = str(data.get('designation', 'Advocate')).strip() or "Advocate"

            if not bar_no:
                errors.append("Bar Council Registration Number is required.")
            details = {
                'bar_registration_no': bar_no,
                'enrollment_year': enroll_year,
                'practice_area': practice_area
            }

        elif role == 'clerk':
            employee_id = str(data.get('clerk_employee_id') or data.get('employee_id') or data.get('id_proof_no') or '').strip()
            id_proof_no = employee_id
            designation = str(data.get('designation', 'Court Master / Bench Clerk')).strip() or "Court Master / Bench Clerk"
            if not employee_id:
                errors.append("Court Clerk Employee ID is required.")
            details = {
                'employee_id': employee_id,
                'court_id': court_id,
                'court_name': court_name_text
            }

        elif role == 'police':
            station = str(data.get('police_station') or data.get('station') or 'Central Judicial Station').strip()
            badge = str(data.get('badge_number') or data.get('badge') or data.get('id_proof_no') or '').strip()
            id_proof_no = badge
            designation = str(data.get('designation', 'Police Officer')).strip() or "Police Officer"
            if not badge:
                errors.append("Police officer badge number is required.")
            details = {
                'police_station': station,
                'badge_number': badge
            }

        elif role == 'litigant':
            city = str(data.get('city', 'New Delhi')).strip()
            case_no = str(data.get('optional_case_no', '')).strip()
            id_proof_no = str(data.get('aadhaar_last4') or data.get('id_proof_no') or '').strip()
            designation = "Citizen / Litigant"
            details = {
                'city': city,
                'optional_case_no': case_no
            }

        if errors:
            if is_json:
                return jsonify({'error': errors[0], 'errors': errors}), 400
            for err in errors:
                flash(err, "danger")
            return render_template('auth/register.html', courts=courts, form_data=request.form)

        # Determine approval status based on rules:
        # Judge & Registrar -> pending_gov
        # Clerk -> pending_registrar
        # Lawyer, Litigant, Police -> active
        if role in ['judge', 'registrar']:
            initial_status = 'pending_gov'
        elif role == 'clerk':
            initial_status = 'pending_registrar'
        else:
            initial_status = 'active'

        # Create user
        new_user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            role=role,
            status=initial_status,
            court_id=court_id,
            id_proof_no=id_proof_no,
            designation=designation,
            avatar_color=random.choice(['#15284F', '#1E40AF', '#166534', '#9A3412', '#701A75'])
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()

        # Audit log creation
        reg_log = AuditLog(
            user_id=new_user.id,
            action="USER_REGISTRATION",
            entity="users",
            entity_id=new_user.id,
            ip=request.remote_addr,
            details=f"User {email} registered with role {role} (initial status: {initial_status})"
        )
        db.session.add(reg_log)

        # If approval required, create approval request & notifications
        if initial_status in ['pending_gov', 'pending_registrar']:
            req = ApprovalRequest(
                applicant_user_id=new_user.id,
                requested_role=role,
                court_name=court_name_text or (db.session.get(Court, court_id).name if court_id else "General Jurisdiction"),
                details_json=json.dumps(details),
                status='Pending'
            )
            db.session.add(req)
            db.session.flush()

            # Applicant notification
            notif = Notification(
                user_id=new_user.id,
                channel="In-App",
                message=f"Your application (Ref #{req.id:05d}) for {role.capitalize()} has been submitted for scrutiny.",
                status="Sent"
            )
            # Simulated SMS
            sms = Notification(
                user_id=new_user.id,
                channel="SMS",
                message=f"NyayaDesk: Application Ref #{req.id:05d} for {role.upper()} received. Verification in progress.",
                status="Sent"
            )
            db.session.add_all([notif, sms])
            db.session.commit()

            # Auto-login to session so they can see pending approval status immediately
            login_user(new_user)
            if is_json:
                return jsonify({
                    'success': True,
                    'user_id': new_user.id,
                    'role': role,
                    'status': initial_status,
                    'redirect': url_for('auth.pending_approval')
                }), 201
            flash("Registration Submitted: Your application has been dispatched to the competent judicial authority for approval.", "info")
            return redirect(url_for('auth.pending_approval'))

        else:
            # Active immediately
            db.session.commit()
            login_user(new_user)
            target_endpoint = get_dashboard_route_for_role(role)
            if is_json:
                return jsonify({
                    'success': True,
                    'user_id': new_user.id,
                    'role': role,
                    'status': initial_status,
                    'redirect': url_for(target_endpoint)
                }), 201
            flash(f"Account activated successfully! Welcome to NyayaDesk, {new_user.full_name}.", "success")
            return redirect(url_for(target_endpoint))

    return render_template('auth/register.html', courts=courts, form_data={})


@auth_bp.route('/pending-approval')
def pending_approval():
    current_user = get_current_user()
    if not current_user.is_authenticated:
        flash("Please log in to check your verification status.", "warning")
        return redirect(url_for('auth.login'))

    # If already active, direct them to their portal
    if current_user.status == 'active':
        flash("Your account is verified and active.", "success")
        return redirect(url_for(get_dashboard_route_for_role(current_user.role)))

    # Find the latest approval request
    req = ApprovalRequest.query.filter_by(applicant_user_id=current_user.id).order_by(ApprovalRequest.id.desc()).first()
    parsed_details = {}
    if req and req.details_json:
        try:
            parsed_details = json.loads(req.details_json)
        except Exception:
            pass

    return render_template('auth/pending_approval.html', user=current_user, request_obj=req, details=parsed_details)


@auth_bp.route('/reapply', methods=['POST'])
def reapply():
    current_user = get_current_user()
    if not current_user.is_authenticated or current_user.status != 'rejected':
        return redirect(url_for('main.index'))

    # Re-apply transitions user status back to pending
    new_status = 'pending_gov' if current_user.role in ['judge', 'registrar'] else 'pending_registrar'
    current_user.status = new_status
    current_user.rejection_reason = None
    
    # Create new approval request
    req = ApprovalRequest(
        applicant_user_id=current_user.id,
        requested_role=current_user.role,
        court_name="Re-application",
        details_json=json.dumps({'reapplied_at': datetime.utcnow().isoformat()}),
        status='Pending'
    )
    db.session.add(req)
    db.session.commit()

    flash("Re-application submitted successfully! Your dossier has been resubmitted for scrutiny.", "success")
    return redirect(url_for('auth.pending_approval'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password flow with simulated on-screen OTP for demonstration."""
    step = session.get('reset_step', 1)
    
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'request_otp':
            email = request.form.get('email', '').strip().lower()
            user = User.query.filter_by(email=email).first()
            if not user:
                flash("If this email address exists in the court registry, an OTP has been generated.", "info")
                return render_template('auth/forgot_password.html', step=1)

            otp = str(random.randint(100000, 999999))
            session['reset_email'] = email
            session['reset_otp'] = otp
            session['reset_expires'] = time.time() + 300 # 5 minutes validity
            session['reset_step'] = 2

            # Notification record for simulation
            notif = Notification(
                user_id=user.id,
                channel="SMS",
                message=f"NyayaDesk Security: Your password reset OTP is {otp}. Valid for 5 minutes.",
                status="Sent"
            )
            db.session.add(notif)
            db.session.commit()

            flash(f"[DEMO SMS / EMAIL GATEWAY] Secure OTP sent to {email}: {otp}", "success")
            return render_template('auth/forgot_password.html', step=2, email=email, demo_otp=otp)

        elif action == 'verify_and_reset':
            entered_otp = request.form.get('otp', '').strip()
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            reset_email = session.get('reset_email')
            stored_otp = session.get('reset_otp')
            expires = session.get('reset_expires', 0)

            if time.time() > expires:
                flash("OTP has expired. Please initiate a new password reset request.", "danger")
                session.pop('reset_step', None)
                return render_template('auth/forgot_password.html', step=1)

            if entered_otp != stored_otp:
                flash("Invalid OTP entered. Please try again.", "danger")
                return render_template('auth/forgot_password.html', step=2, email=reset_email, demo_otp=stored_otp)

            if len(new_password) < 8:
                flash("Password must be at least 8 characters in length.", "danger")
                return render_template('auth/forgot_password.html', step=2, email=reset_email, demo_otp=stored_otp)

            if new_password != confirm_password:
                flash("New password and confirmation do not match.", "danger")
                return render_template('auth/forgot_password.html', step=2, email=reset_email, demo_otp=stored_otp)

            user = User.query.filter_by(email=reset_email).first()
            if user:
                user.set_password(new_password)
                
                # Log reset
                log = AuditLog(
                    user_id=user.id,
                    action="PASSWORD_RESET_SUCCESS",
                    entity="users",
                    entity_id=user.id,
                    ip=request.remote_addr,
                    details=f"Password successfully reset via OTP for {reset_email}"
                )
                db.session.add(log)
                db.session.commit()

                # Clear reset session
                session.pop('reset_email', None)
                session.pop('reset_otp', None)
                session.pop('reset_expires', None)
                session.pop('reset_step', None)

                flash("Password updated successfully! You can now sign in with your new password.", "success")
                return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', step=step, email=session.get('reset_email'), demo_otp=session.get('reset_otp'))


@auth_bp.route('/demo-switch/<role>')
def demo_switch(role):
    """Instant switch to a seeded demo role account for presentation testing."""
    user = User.query.filter_by(role=role, status='active').first()
    if not user:
        # Check if there's any user with this role
        user = User.query.filter_by(role=role).first()

    if user:
        login_user(user)
        flash(f"Switched session to demo account: {user.full_name} ({user.role.upper()} - Status: {user.status.upper()})", "info")
        if user.status in ['pending_gov', 'pending_registrar']:
            return redirect(url_for('auth.pending_approval'))
        target_endpoint = get_dashboard_route_for_role(user.role)
        return redirect(url_for(target_endpoint))
    else:
        flash(f"No demo account found for role '{role}'.", "warning")
        return redirect(url_for('main.index'))


@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP code for password reset, conforming to api_endpoints.md."""
    data = request.get_json(silent=True) or request.form
    otp = str(data.get('otp', '')).strip()
    email = str(data.get('email', session.get('reset_email', ''))).strip().lower()
    stored_otp = session.get('reset_otp')
    expires = session.get('reset_expires', 0)

    if not otp:
        return jsonify({'error': 'OTP is required.'}), 400

    if time.time() > expires:
        return jsonify({'error': 'OTP has expired. Please request a new one.'}), 400

    if otp != stored_otp:
        return jsonify({'error': 'Invalid OTP code.'}), 400

    session['reset_verified'] = True
    session['reset_email'] = email
    return jsonify({'success': True, 'message': 'OTP verified successfully.'})


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Update password upon verified OTP, conforming to api_endpoints.md."""
    data = request.get_json(silent=True) or request.form
    email = str(data.get('email', session.get('reset_email', ''))).strip().lower()
    otp = str(data.get('otp', session.get('reset_otp', ''))).strip()
    new_password = str(data.get('new_password', ''))
    confirm_password = str(data.get('confirm_password', new_password))

    stored_otp = session.get('reset_otp')
    expires = session.get('reset_expires', 0)

    if not session.get('reset_verified') and otp != stored_otp:
        return jsonify({'error': 'Invalid or unverified OTP.'}), 400

    if time.time() > expires:
        return jsonify({'error': 'OTP has expired.'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters in length.'}), 400

    if new_password != confirm_password:
        return jsonify({'error': 'Password confirmation does not match.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found in registry.'}), 404

    user.set_password(new_password)
    db.session.commit()

    # Clear reset session
    session.pop('reset_email', None)
    session.pop('reset_otp', None)
    session.pop('reset_expires', None)
    session.pop('reset_step', None)
    session.pop('reset_verified', None)

    return jsonify({'success': True, 'message': 'Password has been updated successfully.'})


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for('auth.login'))

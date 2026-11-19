"""
NyayaDesk - Role Dashboards & Workspaces
Routes for /gov, /registrar, /judge, /clerk, /lawyer, /litigant, /police.
Enforces strict role-based access control.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from app.models import db, User, Court, Courtroom, Case, CaseParty, Hearing, Document, Order, Payment, Notification, AuditLog, ApprovalRequest
from app.auth import login_required, role_required, get_current_user
from app.services.notifier import send_notification

dashboards_bp = Blueprint('dashboards', __name__)

# --------------------------------------------------------------------------
# 1. Government Administration (/gov)
# --------------------------------------------------------------------------
@dashboards_bp.route('/gov')
@dashboards_bp.route('/government')
@dashboards_bp.route('/dashboards/gov')
@dashboards_bp.route('/dashboards/government')
@role_required('government')
def government_dashboard():
    user = get_current_user()
    pending_approvals = ApprovalRequest.query.filter_by(status='Pending').order_by(ApprovalRequest.created_at.desc()).all()
    recent_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(15).all()
    stats = {
        'total_courts': Court.query.count(),
        'total_judges': User.query.filter_by(role='judge', status='active').count(),
        'total_cases': Case.query.count(),
        'pending_approvals': len(pending_approvals)
    }
    return render_template('dashboards/government.html', user=user, stats=stats, pending_approvals=pending_approvals, recent_audits=recent_audits)


@dashboards_bp.route('/gov/approvals/<int:req_id>/<action>', methods=['POST'])
@role_required('government')
def government_review_approval(req_id, action):
    user = get_current_user()
    req = ApprovalRequest.query.get_or_404(req_id)
    applicant = db.session.get(User, req.applicant_user_id)
    remarks = request.form.get('remarks', '').strip()

    if action == 'approve':
        req.status = 'Approved'
        req.reviewed_by = user.id
        req.remarks = remarks or "Approved by Ministry of Law & Justice / State Judicial Secretariat."
        req.reviewed_at = datetime.utcnow()

        if applicant:
            applicant.status = 'active'
            applicant.approved_by = user.id
            applicant.approved_at = datetime.utcnow()
            applicant.rejection_reason = None

            send_notification(
                user=applicant,
                template_key='account_approved',
                context={'name': applicant.full_name, 'role': applicant.role.capitalize()},
                preferred_channel='SMS'
            )
            db.session.add(Notification(
                user_id=applicant.id,
                channel="In-App",
                message=f"Official Approval: Your appointment credentials as {applicant.role.capitalize()} have been validated. You now have full bench access.",
                status="Sent"
            ))

        flash(f"Application #{req.id:05d} for {applicant.full_name if applicant else 'User'} APPROVED successfully.", "success")

    elif action == 'reject':
        req.status = 'Rejected'
        req.reviewed_by = user.id
        req.remarks = remarks or "Eligibility or verification requirements not satisfied."
        req.reviewed_at = datetime.utcnow()

        if applicant:
            applicant.status = 'rejected'
            applicant.rejection_reason = req.remarks

            send_notification(
                user=applicant,
                template_key='account_rejected',
                context={'name': applicant.full_name, 'role': applicant.role.capitalize(), 'reason': req.remarks},
                preferred_channel='SMS'
            )
            db.session.add(Notification(
                user_id=applicant.id,
                channel="In-App",
                message=f"Application Notice: Your request for {applicant.role.capitalize()} was rejected. Remarks: {req.remarks}",
                status="Sent"
            ))

        flash(f"Application #{req.id:05d} has been REJECTED with remarks.", "warning")

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action=f"GOV_APPROVAL_{action.upper()}",
        entity="approval_requests",
        entity_id=req.id,
        ip=request.remote_addr,
        details=f"Government user {user.email} marked request #{req.id} as {req.status} for applicant #{applicant.id if applicant else 'Unknown'}"
    )
    db.session.add(audit)
    db.session.commit()

    return redirect(url_for('dashboards.government_dashboard'))


# --------------------------------------------------------------------------
# 2. Registrar General (/registrar)
# --------------------------------------------------------------------------
@dashboards_bp.route('/registrar')
@dashboards_bp.route('/dashboards/registrar')
@role_required('registrar')
def registrar_dashboard():
    user = get_current_user()
    clerk_requests = ApprovalRequest.query.filter_by(requested_role='clerk', status='Pending').all()
    cases_scrutiny = Case.query.filter_by(status='Scrutiny').all()
    stats = {
        'cases_scrutiny': len(cases_scrutiny),
        'clerk_requests': len(clerk_requests),
        'active_courtrooms': Courtroom.query.count(),
        'total_cases': Case.query.count()
    }
    return render_template('dashboards/registrar.html', user=user, stats=stats, clerk_requests=clerk_requests, cases_scrutiny=cases_scrutiny)


@dashboards_bp.route('/registrar/approvals/<int:req_id>/<action>', methods=['POST'])
@role_required('registrar')
def registrar_review_approval(req_id, action):
    user = get_current_user()
    req = ApprovalRequest.query.get_or_404(req_id)
    applicant = db.session.get(User, req.applicant_user_id)
    remarks = request.form.get('remarks', '').strip()

    if action == 'approve':
        req.status = 'Approved'
        req.reviewed_by = user.id
        req.remarks = remarks or "Approved by Registry Administration."
        req.reviewed_at = datetime.utcnow()
        if applicant:
            applicant.status = 'active'
            applicant.approved_by = user.id
            applicant.approved_at = datetime.utcnow()
        flash(f"Clerk credentials for {applicant.full_name} approved.", "success")
    else:
        req.status = 'Rejected'
        req.reviewed_by = user.id
        req.remarks = remarks or "Employee credentials could not be verified with court roster."
        req.reviewed_at = datetime.utcnow()
        if applicant:
            applicant.status = 'rejected'
            applicant.rejection_reason = req.remarks
        flash(f"Clerk application #{req.id} rejected.", "warning")

    db.session.commit()
    return redirect(url_for('dashboards.registrar_dashboard'))


# --------------------------------------------------------------------------
# 3. Presiding Judge (/judge)
# --------------------------------------------------------------------------
@dashboards_bp.route('/judge')
@dashboards_bp.route('/dashboards/judge')
@role_required('judge')
def judge_dashboard():
    user = get_current_user()
    today = datetime.utcnow().date()
    # Find hearings scheduled for this judge or courtroom
    hearings_today = Hearing.query.filter(Hearing.judge_id == user.id).order_by(Hearing.scheduled_at.asc()).all()
    cases_assigned = Case.query.filter_by(judge_id=user.id).all()
    return render_template('dashboards/judge.html', user=user, hearings_today=hearings_today, cases_assigned=cases_assigned)


# --------------------------------------------------------------------------
# 4. Court Clerk / Reader (/clerk)
# --------------------------------------------------------------------------
@dashboards_bp.route('/clerk')
@dashboards_bp.route('/dashboards/clerk')
@role_required('clerk')
def clerk_dashboard():
    user = get_current_user()
    hearings = Hearing.query.order_by(Hearing.scheduled_at.desc()).limit(15).all()
    return render_template('dashboards/clerk.html', user=user, hearings=hearings)


# --------------------------------------------------------------------------
# 5. Advocate / Lawyer (/lawyer)
# --------------------------------------------------------------------------
@dashboards_bp.route('/lawyer')
@dashboards_bp.route('/dashboards/lawyer')
@role_required('lawyer')
def lawyer_dashboard():
    user = get_current_user()
    # Find parties represented by this lawyer
    represented = CaseParty.query.filter_by(advocate_id=user.id).all()
    case_ids = list(set([p.case_id for p in represented]))
    my_cases = Case.query.filter(Case.id.in_(case_ids)).all() if case_ids else []
    return render_template('dashboards/lawyer.html', user=user, my_cases=my_cases)


# --------------------------------------------------------------------------
# 6. Litigant / Citizen (/litigant)
# --------------------------------------------------------------------------
@dashboards_bp.route('/litigant')
@dashboards_bp.route('/dashboards/litigant')
@role_required('litigant')
def litigant_dashboard():
    user = get_current_user()
    represented = CaseParty.query.filter_by(user_id=user.id).all()
    case_ids = list(set([p.case_id for p in represented]))
    my_cases = Case.query.filter(Case.id.in_(case_ids)).all() if case_ids else []
    my_payments = Payment.query.filter_by(user_id=user.id).all()
    return render_template('dashboards/litigant.html', user=user, my_cases=my_cases, my_payments=my_payments)


# --------------------------------------------------------------------------
# 7. Police Officer (/police)
# --------------------------------------------------------------------------
@dashboards_bp.route('/police')
@dashboards_bp.route('/dashboards/police')
@role_required('police')
def police_dashboard():
    user = get_current_user()
    criminal_cases = Case.query.filter(Case.case_type.in_(['Criminal', 'Bail'])).limit(15).all()
    return render_template('dashboards/police.html', user=user, criminal_cases=criminal_cases)


# --------------------------------------------------------------------------
# 8. Shared Notification Center (/notifications)
# --------------------------------------------------------------------------
@dashboards_bp.route('/notifications')
@login_required
def notification_center():
    user = get_current_user()
    return render_template('notifications.html', user=user)


# --------------------------------------------------------------------------
# 9. Hearing Reminders Console (/reminders)
# --------------------------------------------------------------------------
@dashboards_bp.route('/reminders')
@role_required('clerk', 'registrar', 'government', 'judge')
def reminders_console():
    user = get_current_user()
    return render_template('reminders.html', user=user)


# --------------------------------------------------------------------------
# 10. SMS & Multi-Channel Outbox (/outbox)
# --------------------------------------------------------------------------
@dashboards_bp.route('/outbox')
@role_required('clerk', 'registrar', 'government', 'judge')
def sms_outbox():
    user = get_current_user()
    return render_template('outbox.html', user=user)


# --------------------------------------------------------------------------
# 11. Case Detail View (/dashboards/cases/<case_id>)
# --------------------------------------------------------------------------
@dashboards_bp.route('/cases/<int:case_id>')
@dashboards_bp.route('/dashboards/cases/<int:case_id>')
@login_required
def case_detail_view(case_id):
    from flask import abort
    from app.routes.api import user_has_case_access
    user = get_current_user()
    c = Case.query.get_or_404(case_id)
    if not user_has_case_access(user, c):
        abort(403)
    return render_template('dashboards/case_detail.html', case=c, user=user)


# --------------------------------------------------------------------------
# 12. AI Status & Usage Observability (/admin/ai-status, /dashboards/ai-usage)
# --------------------------------------------------------------------------
@dashboards_bp.route('/admin/ai-status')
@dashboards_bp.route('/dashboards/ai-usage')
@dashboards_bp.route('/admin/ai-usage')
@role_required('government', 'registrar', 'judge')
def ai_status_dashboard():
    from app.services.ai import get_ai_service
    from app.models import AILog
    from sqlalchemy import func

    user = get_current_user()
    ai_srv = get_ai_service()
    status_info = ai_srv.get_status_info()

    # Query usage by feature
    feature_counts = db.session.query(
        AILog.feature,
        func.count(AILog.id).label('total'),
        func.avg(AILog.latency_ms).label('avg_lat'),
        func.sum(db.case((AILog.fallback_used == True, 1), else_=0)).label('fallbacks'),
        func.sum(db.case((AILog.status == 'failed', 1), else_=0)).label('failures')
    ).group_by(AILog.feature).all()

    feature_stats = [
        {
            'feature': r[0],
            'total': r[1],
            'avg_lat': round(float(r[2] or 0), 1),
            'fallbacks': int(r[3] or 0),
            'failures': int(r[4] or 0),
        }
        for r in feature_counts
    ]

    recent_logs = AILog.query.order_by(AILog.created_at.desc()).limit(50).all()

    return render_template(
        'dashboards/ai_usage.html',
        user=user,
        status_info=status_info,
        feature_stats=feature_stats,
        recent_logs=recent_logs
    )


@dashboards_bp.route('/precedents')
@dashboards_bp.route('/dashboards/precedent-search')
def precedent_search_view():
    """Semantic Case-Law and Precedent Search page."""
    user = get_current_user()
    initial_query = request.args.get('q', '')
    return render_template(
        'dashboards/precedent_search.html',
        user=user,
        initial_query=initial_query
    )


@dashboards_bp.route('/dashboards/translate')
def translate_view():
    """Multilingual Judicial Translation Engine page."""
    user = get_current_user()
    return render_template(
        'dashboards/translate.html',
        user=user
    )


@dashboards_bp.route('/admin/ai-evaluations')
@role_required('government', 'registrar')
def ai_evaluations_dashboard():
    """AI Evaluation Mode & Quality Assurance Monitoring dashboard."""
    from app.services.ai.evaluation import get_ai_evaluation_summary
    user = get_current_user()
    summary = get_ai_evaluation_summary()
    return render_template(
        'dashboards/ai_evaluations.html',
        user=user,
        summary=summary
    )





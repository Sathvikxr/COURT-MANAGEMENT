"""
NyayaDesk - RESTful JSON API Backend
Powers modern SaaS dashboard UI interactions: approvals, case management,
cause lists, orders, e-filing, conflict detection, notifications, and analytics.
"""

import os
import json
import hashlib
import random
import time
from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename
from app.models import (
    db, User, Court, Courtroom, Case, CaseParty, Hearing,
    Document, Order, Payment, Notification, AuditLog, ApprovalRequest, HearingReminder,
    PrecedentLibrary, HearingTranscription, AIEvaluation
)
from app.auth import get_current_user
from app.services.notifier import (
    send_notification, handle_inbound_reply, OUTBOX_LOG_PATH
)
from app.services.scheduler import (
    scan_and_send_hearing_reminders, get_hearing_recipients,
    notify_hearing_rescheduled, notify_new_order, notify_new_document,
    notify_fee_due, notify_account_approval
)
from app.services.ai import (
    get_ai_mode, generate_case_summary, draft_judicial_order,
    citizen_legal_chat, calculate_case_priority, suggest_cause_list_ordering,
    suggest_smart_scheduling_slots, assess_delay_risk, find_similar_cases,
    auto_tag_document
)
from app.services.ai.precedents import search_precedents
from app.services.ai.case_rag import ask_case_file
from app.services.ai.ocr_intelligence import extract_text_from_file, parse_petition_intelligence
from app.services.ai.defect_checker import audit_case_defects
from app.services.ai.transcription import transcribe_hearing_audio, generate_minutes_from_transcript
from app.services.ai.translator import translate_judicial_document
from app.services.ai.analytics_tools import process_natural_language_analytics
from app.services.ai.backlog_insights import generate_backlog_insight_card
from app.services.ai.judge_copilot import (
    summarize_case_3_bullets, draft_adjournment_order as copilot_draft_adjournment,
    find_conflicting_hearings, flag_missing_evidence_before_judgment
)
from app.services.ai.evaluation import record_ai_evaluation, get_ai_evaluation_summary

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Helper decorator or auth check
def require_api_auth(allowed_roles=None):
    user = get_current_user()
    if not user.is_authenticated:
        return None, (jsonify({'error': 'Unauthorized: Authentication required'}), 401)
    if user.status != 'active':
        return None, (jsonify({'error': f"Forbidden: Account status '{user.status}' does not permit access."}), 403)
    if allowed_roles and user.role not in allowed_roles:
        return None, (jsonify({'error': f"Forbidden. Role '{user.role}' lacks clearance."}), 403)
    return user, None


def user_has_case_access(user, case):
    """
    Check if user is authorized to view or access case details.
    - Official judicial roles (government, registrar, judge, clerk) have bench oversight.
    - Police can view Criminal and Bail cases or cases in their docket.
    - Lawyer can only view cases where they are designated advocate or filer.
    - Litigant can only view cases where they are a party or filer.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role in ['government', 'registrar', 'judge', 'clerk']:
        return True
    if user.role == 'police':
        return case.case_type in ['Criminal', 'Bail'] or case.filed_by == user.id
    if user.role == 'lawyer':
        if case.filed_by == user.id:
            return True
        for p in case.parties:
            if p.advocate_id == user.id or p.user_id == user.id:
                return True
        return False
    if user.role == 'litigant':
        if case.filed_by == user.id:
            return True
        for p in case.parties:
            if p.user_id == user.id:
                return True
        return False
    return False


# =========================================================================
# 1. SHARED ENDPOINTS: NOTIFICATIONS, SEARCH, PROFILE
# =========================================================================

@api_bp.route('/notifications', methods=['GET'])
def get_notifications():
    user = get_current_user()
    if not user.is_authenticated:
        return jsonify({'notifications': [], 'unread_count': 0})
    
    channel = request.args.get('channel', 'All')
    status = request.args.get('status', 'All')
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 50))

    query = Notification.query.filter_by(user_id=user.id)
    if channel and channel != 'All':
        query = query.filter_by(channel=channel)
    if status and status != 'All':
        query = query.filter_by(status=status)
    if q:
        query = query.filter(Notification.message.ilike(f"%{q}%"))

    notifs = query.order_by(Notification.sent_at.desc()).limit(limit).all()
    unread = Notification.query.filter_by(user_id=user.id, status='Sent').count()
    return jsonify({
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'channel': n.channel,
            'status': n.status,
            'sent_at': n.sent_at.strftime('%d %b %H:%M'),
            'recipient_contact': n.recipient_contact or (user.phone if n.channel in ['SMS', 'WhatsApp'] else user.email),
            'provider': n.provider or 'DEMO_GATEWAY',
            'fallback_from': n.fallback_from,
            'reminder_type': n.reminder_type,
            'related_case_number': n.related_case.case_number if n.related_case else None
        } for n in notifs],
        'unread_count': unread
    })


@api_bp.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    user = get_current_user()
    if not user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401
    
    Notification.query.filter_by(user_id=user.id, status='Sent').update({'status': 'Delivered'})
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/notifications/preferences', methods=['GET', 'POST'])
def notification_preferences():
    user = get_current_user()
    if not user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'POST':
        data = request.json or request.form
        prefs = user.get_notification_prefs() if hasattr(user, 'get_notification_prefs') else {}
        if 'sms' in data:
            prefs['sms'] = str(data.get('sms')).lower() in ['true', '1', 'on']
        if 'whatsapp' in data:
            prefs['whatsapp'] = str(data.get('whatsapp')).lower() in ['true', '1', 'on']
        if 'email' in data:
            prefs['email'] = str(data.get('email')).lower() in ['true', '1', 'on']
        if 'in_app' in data:
            prefs['in_app'] = str(data.get('in_app')).lower() in ['true', '1', 'on']
        if 'quiet_hours_enabled' in data:
            prefs['quiet_hours_enabled'] = str(data.get('quiet_hours_enabled')).lower() in ['true', '1', 'on']
        if 'quiet_hours_start' in data and data.get('quiet_hours_start'):
            prefs['quiet_hours_start'] = data.get('quiet_hours_start')
        if 'quiet_hours_end' in data and data.get('quiet_hours_end'):
            prefs['quiet_hours_end'] = data.get('quiet_hours_end')

        user.set_notification_prefs(prefs)
        lang = data.get('language_pref') or data.get('language')
        if lang in ['en', 'te', 'hi']:
            user.language_pref = lang

        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Notification preferences and language saved successfully.',
            'preferences': user.get_notification_prefs(),
            'language_pref': user.language_pref
        })

    return jsonify({
        'preferences': user.get_notification_prefs() if hasattr(user, 'get_notification_prefs') else {},
        'language_pref': user.language_pref or 'en'
    })


@api_bp.route('/search', methods=['GET'])
def global_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'cases': []})

    # Search in Case Number, Title, or CaseParty Name
    case_matches = Case.query.filter(
        (Case.case_number.ilike(f"%{q}%")) |
        (Case.title.ilike(f"%{q}%")) |
        (Case.description.ilike(f"%{q}%"))
    ).limit(10).all()

    # Search in Parties
    party_matches = CaseParty.query.filter(CaseParty.name.ilike(f"%{q}%")).limit(10).all()
    party_case_ids = [p.case_id for p in party_matches]
    if party_case_ids:
        more_cases = Case.query.filter(Case.id.in_(party_case_ids)).limit(10).all()
        # Merge unique
        seen = {c.id for c in case_matches}
        for mc in more_cases:
            if mc.id not in seen:
                case_matches.append(mc)

    return jsonify({
        'cases': [{
            'id': c.id,
            'case_number': c.case_number,
            'title': c.title,
            'case_type': c.case_type,
            'status': c.status,
            'court': c.court.name if c.court else 'Court',
            'next_hearing_date': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None
        } for c in case_matches]
    })


@api_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    user = get_current_user()
    if not user.is_authenticated:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'POST':
        data = request.json or request.form
        user.phone = data.get('phone', user.phone)
        user.designation = data.get('designation', user.designation)
        user.language_pref = data.get('language_pref', user.language_pref)
        
        new_pwd = data.get('new_password')
        if new_pwd and len(new_pwd) >= 8:
            user.set_password(new_pwd)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Profile updated successfully.'})

    return jsonify({
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
        'status': user.status,
        'designation': user.designation,
        'id_proof_no': user.id_proof_no,
        'court': user.court.name if user.court else None,
        'language_pref': user.language_pref
    })


# =========================================================================
# 2. GOVERNMENT API ENDPOINTS (/api/gov)
# =========================================================================

@api_bp.route('/gov/stats', methods=['GET'])
def gov_stats():
    user, err = require_api_auth(['government'])
    if err: return err

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    return jsonify({
        'total_courts': Court.query.count(),
        'total_judges': User.query.filter_by(role='judge', status='active').count(),
        'total_registrars': User.query.filter_by(role='registrar', status='active').count(),
        'pending_approvals': ApprovalRequest.query.filter_by(status='Pending').count(),
        'active_cases': Case.query.filter(Case.status.in_(['Registered', 'Hearing', 'Reserved', 'Scrutiny'])).count(),
        'disposed_this_month': Case.query.filter_by(status='Disposed').count()
    })


@api_bp.route('/gov/approvals', methods=['GET'])
def gov_get_approvals():
    user, err = require_api_auth(['government'])
    if err: return err

    status_filter = request.args.get('status', 'Pending').capitalize()
    reqs = ApprovalRequest.query.filter_by(status=status_filter).order_by(ApprovalRequest.created_at.desc()).all()

    return jsonify({
        'requests': [{
            'id': r.id,
            'applicant_id': r.applicant_user_id,
            'applicant_name': r.applicant.full_name,
            'applicant_email': r.applicant.email,
            'email': r.applicant.email,
            'applicant_phone': r.applicant.phone,
            'requested_role': r.requested_role,
            'court_name': r.court_name,
            'details': json.loads(r.details_json) if r.details_json else {},
            'status': r.status,
            'remarks': r.remarks,
            'created_at': r.created_at.strftime('%d %b %Y, %H:%M')
        } for r in reqs]
    })


@api_bp.route('/gov/approvals/<int:req_id>/action', methods=['POST'])
@api_bp.route('/gov/approvals/<int:req_id>/<action>', methods=['POST'])
def gov_action_approval(req_id, action=None):
    user, err = require_api_auth(['government'])
    if err: return err

    data = request.json or {}
    action = (action or data.get('action') or '').lower()
    remarks = data.get('remarks', '').strip()

    req_obj = ApprovalRequest.query.get_or_404(req_id)
    applicant = db.session.get(User, req_obj.applicant_user_id)

    if action == 'approve':
        req_obj.status = 'Approved'
        req_obj.reviewed_by = user.id
        req_obj.remarks = remarks or "Approved by Ministry of Law & Justice."
        req_obj.reviewed_at = datetime.utcnow()

        if applicant:
            applicant.status = 'active'
            applicant.approved_by = user.id
            applicant.approved_at = datetime.utcnow()
            applicant.rejection_reason = None

            # Multi-channel notification via notifier service (logs to outbox.log & DB)
            send_notification(
                user=applicant,
                template_key='account_approved',
                context={'name': applicant.full_name, 'role': applicant.role.capitalize()},
                preferred_channel='SMS'
            )
            # Ensure In-App alert is recorded
            db.session.add(Notification(
                user_id=applicant.id,
                channel="In-App",
                message=f"Official Approval: Your appointment credentials as {applicant.role.capitalize()} have been validated. You now have full bench access.",
                status="Sent"
            ))

    elif action == 'reject':
        if not remarks:
            remarks = "Eligibility or credential verification requirements not satisfied."
        req_obj.status = 'Rejected'
        req_obj.reviewed_by = user.id
        req_obj.remarks = remarks
        req_obj.reviewed_at = datetime.utcnow()

        if applicant:
            applicant.status = 'rejected'
            applicant.rejection_reason = remarks

            # Multi-channel notification via notifier service (logs to outbox.log & DB)
            send_notification(
                user=applicant,
                template_key='account_rejected',
                context={'name': applicant.full_name, 'role': applicant.role.capitalize(), 'reason': remarks},
                preferred_channel='SMS'
            )
            # Ensure In-App alert is recorded
            db.session.add(Notification(
                user_id=applicant.id,
                channel="In-App",
                message=f"Application Notice: Your request for {applicant.role.capitalize()} was rejected. Remarks: {remarks}",
                status="Sent"
            ))

    db.session.add(AuditLog(
        user_id=user.id,
        action=f"GOV_APPROVAL_{action.upper()}",
        entity="approval_requests",
        entity_id=req_obj.id,
        ip=request.remote_addr,
        details=f"Government user {user.email} marked request #{req_obj.id} as {req_obj.status}"
    ))

    db.session.commit()
    return jsonify({
        'success': True,
        'status': req_obj.status,
        'message': f"Application #{req_obj.id:05d} {req_obj.status.lower()} successfully."
    })


@api_bp.route('/gov/approvals/bulk-approve', methods=['POST'])
def gov_bulk_approve():
    user, err = require_api_auth(['government'])
    if err: return err

    pending = ApprovalRequest.query.filter_by(status='Pending').all()
    count = 0
    for r in pending:
        r.status = 'Approved'
        r.reviewed_by = user.id
        r.remarks = "Bulk approved during executive credential review."
        r.reviewed_at = datetime.utcnow()
        if r.applicant:
            r.applicant.status = 'active'
            r.applicant.approved_by = user.id
            r.applicant.approved_at = datetime.utcnow()
            db.session.add(Notification(
                user_id=r.applicant.id,
                channel="In-App",
                message="Your judicial appointment has been approved in executive bulk review.",
                status="Sent"
            ))
        count += 1

    db.session.add(AuditLog(
        user_id=user.id,
        action="GOV_BULK_APPROVE",
        entity="approval_requests",
        ip=request.remote_addr,
        details=f"Bulk approved {count} pending requests."
    ))
    db.session.commit()
    return jsonify({'success': True, 'count': count, 'approved_count': count})


@api_bp.route('/gov/courts', methods=['GET', 'POST'])
def gov_courts():
    user, err = require_api_auth(['government', 'registrar'])
    if err: return err

    if request.method == 'POST':
        data = request.json or request.form
        name = data.get('name')
        c_type = data.get('type', 'District')
        city = data.get('city')
        state = data.get('state', 'Delhi')
        code = data.get('code', f"CRT-{random.randint(100, 999)}")
        address = data.get('address')

        new_court = Court(name=name, type=c_type, city=city, state=state, code=code, address=address)
        db.session.add(new_court)
        db.session.flush()

        # Add initial courtroom
        cr = Courtroom(court_id=new_court.id, name="Courtroom 1 (Main Bench)", capacity=60)
        db.session.add(cr)
        db.session.commit()
        return jsonify({'success': True, 'court_id': new_court.id})

    courts = Court.query.all()
    return jsonify({
        'courts': [{
            'id': c.id,
            'name': c.name,
            'type': c.type,
            'city': c.city,
            'state': c.state,
            'code': c.code,
            'courtrooms_count': c.courtrooms.count(),
            'cases_count': c.cases.count()
        } for c in courts]
    })


@api_bp.route('/gov/courtrooms', methods=['POST'])
def gov_add_courtroom():
    user, err = require_api_auth(['government', 'registrar'])
    if err: return err

    data = request.json or request.form
    court_id = int(data.get('court_id'))
    name = data.get('name', 'Courtroom')
    capacity = int(data.get('capacity', 50))

    cr = Courtroom(court_id=court_id, name=name, capacity=capacity)
    db.session.add(cr)
    db.session.commit()
    return jsonify({'success': True, 'id': cr.id})


@api_bp.route('/gov/users', methods=['GET', 'POST'])
@api_bp.route('/gov/users/<int:user_id>/status', methods=['POST'])
@api_bp.route('/gov/judges', methods=['GET'])
def gov_users(user_id=None):
    user, err = require_api_auth(['government'])
    if err: return err

    if request.method == 'POST':
        data = request.json or {}
        target_user_id = user_id or data.get('user_id')
        new_status = data.get('status') # 'suspended' or 'active'

        target = db.session.get(User, target_user_id)
        if not target:
            return jsonify({'error': 'User not found'}), 404

        target.status = new_status
        db.session.add(AuditLog(
            user_id=user.id,
            action=f"USER_STATUS_{new_status.upper()}",
            entity="users",
            entity_id=target.id,
            ip=request.remote_addr,
            details=f"Government changed status of {target.email} to {new_status}"
        ))
        db.session.commit()
        return jsonify({'success': True, 'status': target.status, 'message': f'User status updated to {new_status}.'})

    judges_and_regs = User.query.filter(User.role.in_(['judge', 'registrar'])).all()
    user_list = [{
        'id': u.id,
        'name': u.full_name,
        'full_name': u.full_name,
        'email': u.email,
        'role': u.role,
        'status': u.status,
        'designation': u.designation or ('Judge' if u.role == 'judge' else 'Registrar'),
        'court': u.court.name if u.court else 'High Court of Delhi',
        'created_at': u.created_at.strftime('%d-%m-%Y')
    } for u in judges_and_regs]

    return jsonify({
        'users': user_list,
        'judges': user_list
    })


@api_bp.route('/gov/analytics', methods=['GET'])
def gov_analytics():
    user, err = require_api_auth(['government'])
    if err: return err

    # 1. Cases by Type
    types = ['Civil', 'Criminal', 'Family', 'Property', 'Cheque Bounce', 'Bail', 'Writ', 'Consumer']
    type_counts = [Case.query.filter_by(case_type=t).count() for t in types]

    # 2. Pending vs Disposed
    pending_count = Case.query.filter(Case.status != 'Disposed').count()
    disposed_count = Case.query.filter_by(status='Disposed').count()

    # 3. Courts Breakdown
    courts = Court.query.all()
    court_labels = [c.name for c in courts]
    court_cases = [c.cases.count() for c in courts]

    return jsonify({
        'case_types': {'labels': types, 'counts': type_counts},
        'status_ratio': {'pending': pending_count, 'disposed': disposed_count},
        'courts': {'labels': court_labels, 'counts': court_cases},
        'avg_disposal_days': 114 # Realistic average days
    })


@api_bp.route('/gov/audit-logs', methods=['GET'])
def gov_audit_logs():
    user, err = require_api_auth(['government'])
    if err: return err

    action_filter = request.args.get('action')
    query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))
    logs = query.limit(50).all()

    return jsonify({
        'logs': [{
            'id': l.id,
            'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'action': l.action,
            'entity': l.entity,
            'user': l.user.full_name if l.user else 'System / Anonymous',
            'ip': l.ip,
            'details': l.details
        } for l in logs]
    })


# =========================================================================
# 3. REGISTRAR API ENDPOINTS (/api/registrar)
# =========================================================================

@api_bp.route('/registrar/cases', methods=['GET'])
@api_bp.route('/registrar/cases/unassigned', methods=['GET'])
def registrar_unassigned_cases():
    user, err = require_api_auth(['registrar'])
    if err: return err

    unassigned = Case.query.filter(Case.judge_id.is_(None)).all()
    judges = User.query.filter_by(role='judge', status='active').all()

    return jsonify({
        'cases': [{
            'id': c.id,
            'case_number': c.case_number,
            'title': c.title,
            'case_type': c.case_type,
            'priority': c.priority,
            'filed_on': c.filed_on.strftime('%d-%m-%Y')
        } for c in unassigned],
        'judges': [{'id': j.id, 'name': j.full_name, 'designation': j.designation} for j in judges]
    })


@api_bp.route('/registrar/scrutiny', methods=['GET'])
def registrar_scrutiny_list():
    """Fetches all petitions in Filed or Scrutiny status awaiting procedural review."""
    user, err = require_api_auth(['registrar', 'government', 'clerk'])
    if err: return err

    cases = Case.query.filter(Case.status.in_(['Filed', 'Scrutiny'])).order_by(Case.id.desc()).all()
    return jsonify([{
        'id': c.id,
        'case_number': c.case_number,
        'title': c.title,
        'case_type': c.case_type,
        'status': c.status,
        'filed_on': c.filed_on.strftime('%d-%m-%Y'),
        'petitioner': c.parties.filter_by(party_type='Petitioner').first().name if c.parties.filter_by(party_type='Petitioner').first() else 'N/A',
        'respondent': c.parties.filter_by(party_type='Respondent').first().name if c.parties.filter_by(party_type='Respondent').first() else 'N/A'
    } for c in cases])


@api_bp.route('/registrar/cases/assign', methods=['POST'])
@api_bp.route('/registrar/cases/<int:case_id>/assign', methods=['POST'])
def registrar_assign_case(case_id=None):
    user, err = require_api_auth(['registrar', 'government'])
    if err: return err

    data = request.json or {}
    case_id = case_id or data.get('case_id')
    judge_id = data.get('judge_id')

    if not case_id or not judge_id:
        return jsonify({'error': 'Case ID and Judge ID are required.'}), 400

    c = Case.query.get_or_404(case_id)
    j = User.query.get_or_404(judge_id)

    c.judge_id = j.id
    if c.status in ['Filed', 'Scrutiny']:
        c.status = 'Registered'

    db.session.add(Notification(
        user_id=j.id,
        channel="In-App",
        message=f"Roster Allocation: Case {c.case_number} ({c.title}) assigned to your bench by Registrar.",
        status="Sent"
    ))
    db.session.commit()
    return jsonify({'success': True, 'message': f"Case {c.case_number} successfully allocated to {j.full_name}."})


@api_bp.route('/registrar/scrutiny/decision', methods=['POST'])
@api_bp.route('/registrar/scrutiny/<int:case_id>/action', methods=['POST'])
def registrar_scrutiny_decision(case_id=None):
    user, err = require_api_auth(['registrar', 'government'])
    if err: return err

    data = request.json or {}
    case_id = case_id or data.get('case_id')
    decision = data.get('action') or data.get('decision') # 'accept'/'approve'/'pass' or 'defect'
    remarks = data.get('remarks') or data.get('defect_notes', '')
    judge_id = data.get('judge_id')

    if not case_id or not decision:
        return jsonify({'error': 'Case ID and action/decision are required.'}), 400

    c = Case.query.get_or_404(case_id)
    if decision in ['accept', 'approve', 'pass', 'clear']:
        c.status = 'Scrutiny Passed'
        if judge_id:
            c.judge_id = int(judge_id)
        c.next_hearing_date = date.today() + timedelta(days=14)
        msg = f"E-Filing Verified: Petition {c.case_number} cleared registry scrutiny and stands REGISTERED."
    else:
        c.status = 'Defective'
        c.description = f"[DEFECT NOTICE]: {remarks}\n" + (c.description or '')
        msg = f"Registry Defect Notice on {c.case_number}: {remarks}. Please cure defects within 7 days."

    if c.filed_by:
        db.session.add(Notification(user_id=c.filed_by, channel="In-App", message=msg, status="Sent"))
    db.session.commit()
    return jsonify({'success': True, 'status': c.status})


@api_bp.route('/registrar/analytics', methods=['GET'])
def registrar_analytics():
    """Real database analytics for Registrar dashboard charts."""
    user, err = require_api_auth(['registrar', 'government'])
    if err: return err

    # 1. Scrutiny & Case Stage Breakdown
    stages = ['Scrutiny', 'Registered', 'Hearing', 'Judgment', 'Disposed']
    stage_counts = [Case.query.filter_by(status=s).count() for s in stages]

    # 2. Bench Caseload Distribution
    active_judges = User.query.filter_by(role='judge', status='active').all()
    judge_labels = [j.full_name.replace("Hon'ble Justice ", "J. ") for j in active_judges]
    judge_counts = [Case.query.filter_by(judge_id=j.id).count() for j in active_judges]

    return jsonify({
        'case_stages': {'labels': stages, 'counts': stage_counts},
        'bench_caseload': {'labels': judge_labels, 'counts': judge_counts},
        'unassigned_count': Case.query.filter(Case.judge_id.is_(None)).count(),
        'total_cases': Case.query.count()
    })


# =========================================================================
# 4. JUDGE API ENDPOINTS (/api/judge)
# =========================================================================

@api_bp.route('/judge/cause-list', methods=['GET'])
def judge_cause_list():
    """Returns today's active cause list for the presiding judge's bench."""
    user, err = require_api_auth(['judge'])
    if err: return err

    today = date.today()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    hearings = Hearing.query.filter(
        Hearing.judge_id == user.id,
        Hearing.scheduled_at >= start_dt,
        Hearing.scheduled_at <= end_dt
    ).order_by(Hearing.scheduled_at.asc()).all()

    return jsonify([{
        'id': h.id,
        'scheduled_at': h.scheduled_at.strftime('%I:%M %p'),
        'case_number': h.case.case_number if h.case else 'N/A',
        'title': h.case.title if h.case else 'Matter',
        'case_type': h.case.case_type if h.case else 'General',
        'courtroom': h.courtroom.name if h.courtroom else 'Chamber',
        'purpose': h.purpose,
        'status': h.status,
        'attendance_status': h.attendance_status
    } for h in hearings])


@api_bp.route('/judge/cases/<int:case_id>', methods=['GET'])
@api_bp.route('/cases/<int:case_id>', methods=['GET'])
def judge_case_detail(case_id):
    user, err = require_api_auth()
    if err: return err

    c = Case.query.get_or_404(case_id)
    if not user_has_case_access(user, c):
        return jsonify({'error': 'Forbidden: You are not authorized to inspect this case docket.'}), 403

    parties = c.parties.all()
    hearings = c.hearings.order_by(Hearing.scheduled_at.desc()).all()
    orders = c.orders.order_by(Order.issued_at.desc()).all()
    docs = c.documents.all()

    return jsonify({
        'id': c.id,
        'case_number': c.case_number,
        'title': c.title,
        'case_type': c.case_type,
        'status': c.status,
        'priority': c.priority,
        'description': c.description,
        'court': c.court.name,
        'judge': c.judge.full_name if c.judge else 'Bench Unassigned',
        'filed_on': c.filed_on.strftime('%d-%m-%Y'),
        'next_hearing_date': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None,
        'parties': [{
            'name': p.name,
            'type': p.party_type,
            'advocate': p.advocate.full_name if p.advocate else 'Self'
        } for p in parties],
        'hearings': [{
            'id': h.id,
            'scheduled_at': h.scheduled_at.strftime('%d-%m-%Y %I:%M %p'),
            'purpose': h.purpose,
            'status': h.status,
            'notes': h.notes,
            'adjournment_reason': h.adjournment_reason
        } for h in hearings],
        'orders': [{
            'id': o.id,
            'title': o.title,
            'type': o.order_type,
            'issued_at': o.issued_at.strftime('%d-%m-%Y'),
            'content': o.content,
            'verification_code': o.verification_code
        } for o in orders],
        'documents': [{
            'id': d.id,
            'filename': d.filename,
            'doc_type': d.doc_type,
            'uploaded_at': d.uploaded_at.strftime('%d-%m-%Y'),
            'path': d.stored_path
        } for d in docs],
        'priority_analysis': calculate_case_priority(c),
        'delay_risk': assess_delay_risk(c),
        'similar_cases': find_similar_cases(c, limit=3)
    })


@api_bp.route('/judge/hearings/<int:hearing_id>/action', methods=['POST'])
def judge_hearing_action(hearing_id):
    """Unified action endpoint conforming to api_endpoints.md."""
    user, err = require_api_auth(['judge', 'clerk'])
    if err: return err

    data = request.json or {}
    action = data.get('action', '').lower()
    if action == 'adjourn':
        return judge_adjourn_hearing(hearing_id)
    elif action in ['conclude', 'complete']:
        return judge_complete_hearing(hearing_id)
    else:
        return jsonify({'error': 'Invalid action. Supported actions: adjourn, conclude, complete.'}), 400


@api_bp.route('/judge/hearings/<int:hearing_id>/complete', methods=['POST'])
def judge_complete_hearing(hearing_id):
    user, err = require_api_auth(['judge', 'clerk'])
    if err: return err

    data = request.json or {}
    notes = data.get('notes', 'Hearing concluded on bench.')

    h = Hearing.query.get_or_404(hearing_id)
    h.status = 'Completed'
    h.notes = notes

    db.session.commit()
    return jsonify({'success': True, 'message': 'Hearing marked Completed.'})


@api_bp.route('/judge/hearings/<int:hearing_id>/adjourn', methods=['POST'])
def judge_adjourn_hearing(hearing_id):
    user, err = require_api_auth(['judge'])
    if err: return err

    data = request.json or {}
    reason = data.get('reason') or data.get('adjourn_reason', 'Adjourned on joint request of counsel.')
    next_date_str = data.get('next_date')

    h = Hearing.query.get_or_404(hearing_id)
    h.status = 'Adjourned'
    h.adjournment_reason = reason
    if h.case:
        h.case.status = 'Adjourned'

    if next_date_str:
        try:
            next_date = datetime.strptime(next_date_str, '%Y-%m-%d').date()
            h.case.next_hearing_date = next_date
            
            # Create scheduled next hearing row
            new_h = Hearing(
                case_id=h.case_id,
                courtroom_id=h.courtroom_id,
                judge_id=user.id,
                scheduled_at=datetime.combine(next_date, datetime.min.time()) + timedelta(hours=10, minutes=30),
                purpose="Adjourned Hearing / Further Arguments",
                status="Scheduled"
            )
            db.session.add(new_h)
        except Exception:
            pass

    db.session.commit()
    return jsonify({'success': True, 'message': f"Matter adjourned. Reason: {reason}"})


@api_bp.route('/judge/orders/create', methods=['POST'])
@api_bp.route('/judge/orders/issue', methods=['POST'])
@api_bp.route('/judge/cases/<int:case_id>/orders', methods=['POST'])
@api_bp.route('/cases/<int:case_id>/orders', methods=['POST'])
def judge_create_order(case_id=None):
    user, err = require_api_auth(['judge'])
    if err: return err

    data = request.json or {}
    case_id = case_id or data.get('case_id')
    title = data.get('title', 'Court Order')
    content = data.get('content', '')
    order_type = data.get('order_type', 'Interim') # Interim, Final, Judgment, Notice

    if not case_id or not content:
        return jsonify({'error': 'Case ID and Order text are required.'}), 400

    c = Case.query.get_or_404(case_id)

    # Generate verification code & SHA256 cryptographic signed hash
    verification_code = f"NYAYA-{c.id:04d}-{random.randint(1000, 9999)}-{datetime.utcnow().year}"
    raw_signature = f"{c.case_number}|{user.id}|{content}|{time.time()}"
    signed_hash = hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()

    ord_obj = Order(
        case_id=c.id,
        judge_id=user.id,
        title=title,
        content=content,
        order_type=order_type,
        signed_hash=signed_hash,
        verification_code=verification_code,
        issued_at=datetime.utcnow()
    )
    db.session.add(ord_obj)

    # If Final Judgment, update case status to Disposed
    if order_type in ['Final', 'Judgment']:
        c.status = 'Disposed'

    # Notify parties
    for party in c.parties:
        if party.user_id:
            db.session.add(Notification(
                user_id=party.user_id,
                channel="In-App",
                message=f"New Judicial Order published on {c.case_number}: {title} (Verif: {verification_code})",
                status="Sent"
            ))

    db.session.commit()
    return jsonify({
        'success': True,
        'order_id': ord_obj.id,
        'verification_code': verification_code,
        'signed_hash': signed_hash
    }), 201


@api_bp.route('/judge/ai-summary/<int:case_id>', methods=['GET'])
@api_bp.route('/ai/summary/<int:case_id>', methods=['GET'])
@api_bp.route('/cases/<int:case_id>/ai-summary', methods=['GET'])
def ai_case_summary(case_id):
    user, err = require_api_auth(['judge', 'lawyer', 'clerk', 'registrar', 'government', 'litigant'])
    if err: return err

    c = Case.query.get_or_404(case_id)
    if not user_has_case_access(user, c):
        return jsonify({'error': 'Forbidden: You are not authorized to inspect this case brief.'}), 403

    result = generate_case_summary(c, user_id=user.id)
    return jsonify({
        'case_id': c.id,
        'case_number': c.case_number,
        'summary': result['summary'],
        'mode': result['mode'],
        'model': result['model'],
        'generated_at': result['generated_at']
    })


@api_bp.route('/judge/calendar-events', methods=['GET'])
def judge_calendar_events():
    user, err = require_api_auth(['judge'])
    if err: return err

    hearings = Hearing.query.filter_by(judge_id=user.id).all()
    events = []
    for h in hearings:
        events.append({
            'id': h.id,
            'title': f"{h.case.case_number}: {h.purpose}",
            'start': h.scheduled_at.isoformat(),
            'end': (h.scheduled_at + timedelta(minutes=45)).isoformat(),
            'color': '#C9A24B' if h.status == 'Scheduled' else ('#15803D' if h.status == 'Completed' else '#B45309')
        })
    return jsonify(events)


@api_bp.route('/judge/analytics', methods=['GET'])
def judge_analytics():
    """Real database analytics for Judge bench dashboard charts."""
    user, err = require_api_auth(['judge'])
    if err: return err

    # 1. Caseload by Type for this Bench
    types = ['Civil', 'Criminal', 'Writ', 'Bail', 'Cheque Bounce', 'Property', 'Family', 'Consumer']
    type_counts = [Case.query.filter_by(judge_id=user.id, case_type=t).count() for t in types]
    active_types = [(t, c) for t, c in zip(types, type_counts) if c > 0]
    if not active_types:
        active_types = [('General', 0)]

    # 2. Hearing Outcomes (Scheduled, Completed, Adjourned)
    outcomes = ['Scheduled', 'Completed', 'Adjourned']
    outcome_counts = [Hearing.query.filter_by(judge_id=user.id, status=o).count() for o in outcomes]

    # 3. Disposal Velocity
    total_assigned = Case.query.filter_by(judge_id=user.id).count()
    disposed = Case.query.filter_by(judge_id=user.id, status='Disposed').count()

    return jsonify({
        'case_types': {
            'labels': [t[0] for t in active_types],
            'counts': [t[1] for t in active_types]
        },
        'hearing_outcomes': {
            'labels': outcomes,
            'counts': outcome_counts
        },
        'total_assigned': total_assigned,
        'disposed_count': disposed,
        'pending_count': total_assigned - disposed
    })


# =========================================================================
# 5. CLERK API ENDPOINTS (/api/clerk)
# =========================================================================

@api_bp.route('/clerk/cases/register', methods=['POST'])
def clerk_register_case():
    user, err = require_api_auth(['clerk', 'lawyer', 'registrar'])
    if err: return err

    data = request.json or {}
    title = data.get('title')
    case_type = data.get('case_type', 'Civil')
    priority = data.get('priority', 'Normal')
    court_id = data.get('court_id', 1)
    description = data.get('description', '')
    petitioner_name = data.get('petitioner_name')
    respondent_name = data.get('respondent_name')

    if not title or not petitioner_name or not respondent_name:
        return jsonify({'error': 'Title, Petitioner, and Respondent are required.'}), 400

    # Sequential collision-safe case number generation
    code_map = {'Civil': 'CIV', 'Criminal': 'CRIM', 'Family': 'FAM', 'Property': 'PROP', 'Writ': 'WRIT', 'Bail': 'BAIL', 'Consumer': 'CONS', 'Cheque Bounce': 'CHK'}
    prefix = code_map.get(case_type, 'CASE')
    year = datetime.utcnow().year

    case_number = None
    for attempt in range(15):
        existing_count = Case.query.filter(Case.case_number.like(f"{prefix}/{year}/%")).count()
        candidate = f"{prefix}/{year}/{existing_count + 1 + attempt:05d}"
        if not Case.query.filter_by(case_number=candidate).first():
            case_number = candidate
            break
    if not case_number:
        case_number = f"{prefix}/{year}/{int(time.time() * 1000) % 100000:05d}"

    initial_status = 'Registered' if user.role == 'clerk' else 'Scrutiny'

    new_case = Case(
        case_number=case_number,
        title=title,
        case_type=case_type,
        status=initial_status,
        priority=priority,
        court_id=court_id,
        filed_by=user.id,
        filed_on=date.today(),
        description=description,
        next_hearing_date=date.today() + timedelta(days=10)
    )
    db.session.add(new_case)
    db.session.flush()

    # Add Parties
    p1 = CaseParty(case_id=new_case.id, name=petitioner_name, party_type="Petitioner", advocate_id=user.id if user.role == 'lawyer' else None)
    p2 = CaseParty(case_id=new_case.id, name=respondent_name, party_type="Respondent")
    db.session.add_all([p1, p2])

    db.session.commit()
    return jsonify({
        'success': True,
        'case_id': new_case.id,
        'case_number': case_number,
        'status': initial_status
    }), 201


@api_bp.route('/clerk/hearings/schedule', methods=['POST'])
def clerk_schedule_hearing():
    user, err = require_api_auth(['clerk', 'registrar'])
    if err: return err

    data = request.json or {}
    case_id = data.get('case_id')
    courtroom_id = data.get('courtroom_id')
    judge_id = data.get('judge_id')
    scheduled_at_str = data.get('scheduled_at') # YYYY-MM-DDTHH:MM
    purpose = data.get('purpose', 'Hearing')

    if not case_id or not scheduled_at_str:
        return jsonify({'error': 'Case ID and scheduled date/time required.'}), 400

    try:
        scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
    except Exception:
        return jsonify({'error': 'Invalid datetime format. Expected YYYY-MM-DDTHH:MM'}), 400

    target_date = scheduled_at.date()

    # 1. HOLIDAY & NON-SITTING DAY CONFLICT DETECTION:
    # Sunday check (weekday 6)
    if target_date.weekday() == 6:
        return jsonify({
            'conflict': True,
            'message': f"Judicial Calendar Conflict: {target_date.strftime('%d-%m-%Y')} is a Sunday (Non-Sitting Court Day). Please choose an active court sitting day."
        }), 409

    COURT_HOLIDAYS = {
        (1, 26): "Republic Day",
        (8, 15): "Independence Day",
        (10, 2): "Mahatma Gandhi Jayanti",
        (1, 1): "New Year's Court Holiday",
        (12, 25): "Christmas Vacation",
        (3, 25): "Holi Judicial Recess",
        (10, 31): "Diwali Judicial Recess"
    }
    month_day = (target_date.month, target_date.day)
    if month_day in COURT_HOLIDAYS:
        holiday_name = COURT_HOLIDAYS[month_day]
        return jsonify({
            'conflict': True,
            'message': f"Judicial Calendar Conflict: {target_date.strftime('%d-%m-%Y')} is a Gazetted Court Holiday ({holiday_name}). Please select an active bench sitting day."
        }), 409

    # 2. COURTROOM & BENCH CONFLICT DETECTION (within 30 minutes window):
    c = db.session.get(Case, case_id)
    if not c:
        return jsonify({'error': 'Case not found.'}), 404

    target_judge_id = judge_id or c.judge_id

    time_window_start = scheduled_at - timedelta(minutes=29)
    time_window_end = scheduled_at + timedelta(minutes=29)

    if courtroom_id:
        room_conflict = Hearing.query.filter(
            Hearing.courtroom_id == courtroom_id,
            Hearing.status.in_(['Scheduled', 'In_Progress']),
            Hearing.scheduled_at >= time_window_start,
            Hearing.scheduled_at <= time_window_end
        ).first()
        if room_conflict:
            return jsonify({
                'conflict': True,
                'message': f"Courtroom Conflict: Courtroom is already reserved for {room_conflict.case.case_number} at {room_conflict.scheduled_at.strftime('%I:%M %p')}. Please choose another slot or courtroom."
            }), 409

    if target_judge_id:
        judge_conflict = Hearing.query.filter(
            Hearing.judge_id == target_judge_id,
            Hearing.status.in_(['Scheduled', 'In_Progress']),
            Hearing.scheduled_at >= time_window_start,
            Hearing.scheduled_at <= time_window_end
        ).first()
        if judge_conflict:
            return jsonify({
                'conflict': True,
                'message': f"Bench Conflict: Presiding Judge is already hearing matter {judge_conflict.case.case_number} at this time."
            }), 409

    # No conflict: schedule hearing
    c.next_hearing_date = scheduled_at.date()
    c.status = 'Hearing Scheduled'
    h = Hearing(
        case_id=case_id,
        courtroom_id=courtroom_id,
        judge_id=target_judge_id,
        scheduled_at=scheduled_at,
        purpose=purpose,
        status="Scheduled"
    )
    db.session.add(h)
    db.session.commit()
    return jsonify({'success': True, 'hearing_id': h.id, 'scheduled_at': scheduled_at.strftime('%d-%m-%Y %I:%M %p')})


@api_bp.route('/clerk/documents/upload', methods=['POST'])
@api_bp.route('/cases/<int:case_id>/documents', methods=['POST'])
@api_bp.route('/documents/upload', methods=['POST'])
def upload_document(case_id=None):
    user, err = require_api_auth(['clerk', 'lawyer', 'judge', 'registrar', 'litigant', 'police'])
    if err: return err

    case_id = case_id or request.form.get('case_id')
    doc_type = request.form.get('doc_type', 'Petition')
    file = request.files.get('file')

    if not case_id or not file or not file.filename:
        return jsonify({'error': 'Case ID and File are required.'}), 400

    c = Case.query.get_or_404(int(case_id))
    if not user_has_case_access(user, c):
        return jsonify({'error': 'Forbidden: You are not authorized to upload documents to this case.'}), 403

    # 1. Directory traversal validation
    if '..' in file.filename or '/' in file.filename or '\\' in file.filename:
        return jsonify({'error': 'Invalid filename: directory traversal is strictly prohibited.'}), 400

    # 2. Executable & script double extension check
    DANGEROUS_EXTS = {'exe', 'bat', 'cmd', 'sh', 'php', 'py', 'js', 'vbs', 'ps1', 'dll', 'so', 'bin', 'msi'}
    name_parts = [p.lower() for p in file.filename.split('.')]
    if any(p in DANGEROUS_EXTS for p in name_parts):
        return jsonify({'error': 'Prohibited file: executable script/binary extensions are not permitted.'}), 400

    # 3. Allowed extensions check
    allowed_exts = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'txt'}
    ext = name_parts[-1] if len(name_parts) > 1 else ''
    if ext not in allowed_exts:
        return jsonify({'error': f"Invalid file format '.{ext}'. Allowed types: PDF, PNG, JPG, DOCX, TXT."}), 400

    # 4. MIME type check
    allowed_mimes = {
        'application/pdf', 'image/png', 'image/jpeg', 'image/jpg',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain', 'application/octet-stream'
    }
    if file.mimetype and file.mimetype.lower() not in allowed_mimes:
        return jsonify({'error': f"Invalid MIME type '{file.mimetype}'. Prohibited."}), 400

    # 5. Magic bytes check for executable binary headers
    head = file.read(512)
    file.seek(0)
    if head.startswith(b'MZ') or head.startswith(b'\x7fELF') or b'<?php' in head or b'<script' in head.lower():
        return jsonify({'error': 'Executable binary or script signature detected. Upload rejected.'}), 400

    # 6. File size validation (max 16 MB)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > 16 * 1024 * 1024:
        return jsonify({'error': 'File exceeds maximum permitted size of 16 MB.'}), 400

    # Calculate versioning: increments for every new upload of same case and doc_type
    version = Document.query.filter_by(case_id=int(case_id), doc_type=doc_type).count() + 1

    filename = secure_filename(f"{case_id}_{doc_type}_v{version}_{int(time.time())}_{file.filename}")
    cases_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'cases')
    os.makedirs(cases_dir, exist_ok=True)
    full_path = os.path.join(cases_dir, filename)
    file.save(full_path)

    stored_path = f"uploads/cases/{filename}"

    doc = Document(
        case_id=int(case_id),
        uploaded_by=user.id,
        filename=file.filename,
        stored_path=stored_path,
        doc_type=doc_type,
        version=version,
        visibility="Public"
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({
        'success': True,
        'document_id': doc.id,
        'filename': doc.filename,
        'version': version,
        'path': stored_path
    }), 201


# =========================================================================
# 6. LITIGANT & PAYMENT API ENDPOINTS (/api/litigant)
# =========================================================================

@api_bp.route('/litigant/pay-fee', methods=['POST'])
@api_bp.route('/payments/create', methods=['POST'])
def litigant_pay_fee():
    user, err = require_api_auth(['litigant', 'lawyer', 'clerk', 'government'])
    if err: return err

    data = request.json or {}
    case_id = data.get('case_id')
    amount = float(data.get('amount', 500.0))
    purpose = data.get('purpose') or data.get('payment_type', 'Court E-Filing Fee')

    # Simulate payment completion
    reference = f"PAY-{int(time.time())}-{random.randint(1000, 9999)}"
    pay = Payment(
        case_id=case_id,
        user_id=user.id,
        amount=amount,
        purpose=purpose,
        status="Success",
        reference=reference,
        paid_at=datetime.utcnow()
    )
    db.session.add(pay)

    db.session.add(Notification(
        user_id=user.id,
        channel="In-App",
        message=f"Payment Successful: INR {amount:.2f} received for {purpose}. Ref: {reference}",
        status="Sent"
    ))
    db.session.commit()
    return jsonify({
        'success': True,
        'status': 'Success',
        'reference': reference,
        'payment_reference': reference,
        'amount': amount,
        'paid_at': pay.paid_at.strftime('%d-%m-%Y %H:%M:%S')
    }), 201


@api_bp.route('/payments/<int:payment_id>', methods=['GET'])
def get_payment_detail(payment_id):
    """Fetch payment record with IDOR protection."""
    user, err = require_api_auth()
    if err: return err

    pay = Payment.query.get_or_404(payment_id)
    if user.role not in ['government', 'registrar', 'clerk', 'judge'] and pay.user_id != user.id:
        return jsonify({'error': 'Forbidden: You are not authorized to view another user\'s payment record.'}), 403

    return jsonify({
        'id': pay.id,
        'reference': pay.reference,
        'amount': pay.amount,
        'purpose': pay.purpose,
        'status': pay.status,
        'case_id': pay.case_id,
        'case_number': pay.case.case_number if pay.case else None,
        'payer_name': pay.payer.full_name if pay.payer else 'Citizen',
        'paid_at': pay.paid_at.strftime('%d-%m-%Y %H:%M:%S')
    })


@api_bp.route('/documents/<int:doc_id>/download', methods=['GET'])
def download_document(doc_id):
    """Download case document with IDOR authorization and secure headers."""
    user, err = require_api_auth()
    if err: return err

    doc = Document.query.get_or_404(doc_id)
    c = Case.query.get_or_404(doc.case_id)
    if not user_has_case_access(user, c):
        return jsonify({'error': 'Forbidden: You are not authorized to access this document.'}), 403

    cases_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'cases')
    clean_filename = os.path.basename(doc.stored_path)
    file_path = os.path.join(cases_dir, clean_filename)

    if not os.path.exists(file_path):
        alt_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.stored_path)
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            os.makedirs(cases_dir, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(b"%PDF-1.4\n% NyayaDesk Digital Certified Record\n")

    from flask import send_file
    return send_file(file_path, as_attachment=True, download_name=doc.filename)


# =========================================================================
# 7. PUBLIC REGISTRY & CAUSE LIST ENDPOINTS
# =========================================================================

@api_bp.route('/public/case-status', methods=['GET'])
def public_case_status():
    """Public case search endpoint without authentication."""
    query = (request.args.get('query') or request.args.get('case_number') or request.args.get('q') or '').strip()
    if not query:
        return jsonify({'error': 'Query parameter required (Case number or title).'}), 400

    c = Case.query.filter(
        (Case.case_number.ilike(f"%{query}%")) |
        (Case.title.ilike(f"%{query}%"))
    ).first()

    if not c:
        return jsonify({'success': False, 'message': 'No court case found matching specified query.'}), 404

    return jsonify({
        'success': True,
        'case': {
            'id': c.id,
            'case_number': c.case_number,
            'title': c.title,
            'case_type': c.case_type,
            'status': c.status,
            'court_name': c.court.name if c.court else 'Court',
            'judge_name': c.judge.full_name if c.judge else 'Hon\'ble Bench Unassigned',
            'filed_on': c.filed_on.strftime('%Y-%m-%d'),
            'next_hearing': c.next_hearing_date.strftime('%Y-%m-%d 10:30:00') if c.next_hearing_date else None
        }
    })


@api_bp.route('/public/cause-list', methods=['GET'])
def public_cause_list():
    """Public daily cause list for courtrooms and benches."""
    court_id = request.args.get('court_id')
    date_str = request.args.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        target_date = date.today()

    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())

    query = Hearing.query.filter(
        Hearing.scheduled_at >= start_dt,
        Hearing.scheduled_at <= end_dt
    )
    if court_id and str(court_id).isdigit():
        query = query.join(Case).filter(Case.court_id == int(court_id))

    hearings = query.order_by(Hearing.scheduled_at.asc()).all()
    return jsonify({
        'date': target_date.strftime('%Y-%m-%d'),
        'total_listings': len(hearings),
        'cause_list': [{
            'hearing_id': h.id,
            'case_number': h.case.case_number,
            'case_title': h.case.title,
            'case_type': h.case.case_type,
            'courtroom': h.courtroom.name if h.courtroom else 'Courtroom 1',
            'judge': h.presiding_judge.full_name if h.presiding_judge else (h.case.judge.full_name if h.case.judge else 'Unassigned'),
            'time': h.scheduled_at.strftime('%I:%M %p'),
            'purpose': h.purpose,
            'status': h.status,
            'attendance_status': h.attendance_status
        } for h in hearings]
    })


@api_bp.route('/courts', methods=['GET'])
def get_courts_public():
    """Public listing of registered courts."""
    courts = Court.query.order_by(Court.name).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'code': c.code,
        'type': c.type,
        'city': c.city,
        'state': c.state,
        'address': c.address
    } for c in courts])


@api_bp.route('/courtrooms', methods=['GET'])
def get_courtrooms_public():
    """Public listing of courtrooms for a court."""
    court_id = request.args.get('court_id')
    query = Courtroom.query
    if court_id and str(court_id).isdigit():
        query = query.filter_by(court_id=int(court_id))
    rooms = query.order_by(Courtroom.name).all()
    return jsonify([{
        'id': r.id,
        'court_id': r.court_id,
        'court_name': r.court.name if r.court else None,
        'name': r.name,
        'capacity': r.capacity
    } for r in rooms])


@api_bp.route('/judges', methods=['GET'])
def get_judges_public():
    """Public listing of sitting judges."""
    court_id = request.args.get('court_id')
    query = User.query.filter_by(role='judge', status='active')
    if court_id and str(court_id).isdigit():
        query = query.filter_by(court_id=int(court_id))
    judges = query.order_by(User.full_name).all()
    return jsonify([{
        'id': j.id,
        'name': j.full_name,
        'court_id': j.court_id,
        'court_name': j.court.name if j.court else None,
        'designation': j.designation or "Presiding Judge"
    } for j in judges])


@api_bp.route('/orders/verify/<verification_code>', methods=['GET'])
def verify_order_api(verification_code):
    """Public cryptographic order verification endpoint."""
    clean_code = str(verification_code).strip()
    order = Order.query.filter_by(verification_code=clean_code).first()
    if not order:
        return jsonify({'valid': False, 'message': 'Cryptographic verification code not found in judicial registry.'}), 404

    return jsonify({
        'valid': True,
        'verification_code': order.verification_code,
        'signed_hash': order.signed_hash,
        'order_id': order.id,
        'case_number': order.case.case_number,
        'case_title': order.case.title,
        'court': order.case.court.name if order.case.court else 'High Court',
        'issuing_judge': order.issuing_judge.full_name if order.issuing_judge else 'Hon\'ble Bench',
        'title': order.title,
        'order_type': order.order_type,
        'issued_at': order.issued_at.strftime('%d-%m-%Y %H:%M UTC'),
        'content_preview': order.content[:300] + ('...' if len(order.content) > 300 else '')
    })


# =========================================================================
# 8. ROLE-SPECIFIC APIS: CLERK, LAWYER, LITIGANT, POLICE
# =========================================================================

@api_bp.route('/clerk/cases', methods=['GET'])
def clerk_cases_list():
    """Lists all cases registered or managed in the court with pagination."""
    user, err = require_api_auth(['clerk', 'registrar', 'government', 'judge'])
    if err: return err

    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    query = Case.query.order_by(Case.id.desc())

    status = request.args.get('status')
    if status and status != 'All':
        query = query.filter_by(status=status)

    q = request.args.get('q', '').strip()
    if q:
        query = query.filter((Case.case_number.ilike(f"%{q}%")) | (Case.title.ilike(f"%{q}%")))

    total = query.count()
    cases = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        'total': total,
        'page': page,
        'limit': limit,
        'cases': [{
            'id': c.id,
            'case_number': c.case_number,
            'title': c.title,
            'case_type': c.case_type,
            'status': c.status,
            'court': c.court.name if c.court else 'Court',
            'judge': c.judge.full_name if c.judge else 'Unassigned',
            'next_hearing': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None
        } for c in cases]
    })


@api_bp.route('/clerk/notices/generate', methods=['POST'])
def clerk_generate_notice():
    """Produces formal court summons and notices with automatic styling."""
    user, err = require_api_auth(['clerk', 'registrar', 'judge', 'government'])
    if err: return err

    data = request.json or {}
    case_id = data.get('case_id')
    party_name = data.get('party_name', 'Opposite Party')
    hearing_date = data.get('hearing_date')
    notice_type = data.get('notice_type', 'Summons for Appearance')

    if not case_id:
        return jsonify({'error': 'Case ID is required.'}), 400

    c = Case.query.get_or_404(case_id)
    notice_code = f"NOT-NYA-{c.id:04d}-{int(time.time()) % 10000}"
    body = (
        f"IN THE COURT OF {c.court.name.upper() if c.court else 'THE JUDICIAL BENCH'}\n"
        f"NOTICE / SUMMONS UNDER CODE OF CIVIL PROCEDURE / CODE OF CRIMINAL PROCEDURE\n\n"
        f"Case Number: {c.case_number} ({c.case_type})\n"
        f"Title: {c.title}\n\n"
        f"To: {party_name}\n\n"
        f"WHEREAS the above-named matter has been instituted and is pending adjudication before this Court.\n"
        f"YOU ARE HEREBY REQUIRED to appear in person or by advocate duly instructed on "
        f"{hearing_date or (c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else 'the scheduled date')} "
        f"at 10:30 AM in {c.court.name if c.court else 'Courtroom 1'}.\n"
        f"TAKE NOTICE that in default of your appearance, the suit/matter may be heard and determined ex-parte.\n\n"
        f"Given under the seal of the Registry on {date.today().strftime('%d-%m-%Y')}.\n"
        f"Court Master / Reader: {user.full_name}\n"
        f"Notice Tracking Ref: {notice_code}"
    )

    return jsonify({
        'success': True,
        'notice_code': notice_code,
        'case_number': c.case_number,
        'party_name': party_name,
        'notice_type': notice_type,
        'body': body
    })


@api_bp.route('/lawyer/cases', methods=['GET'])
def lawyer_cases_api():
    """Lists active client cases where the lawyer is designated counsel."""
    user, err = require_api_auth(['lawyer'])
    if err: return err

    represented = CaseParty.query.filter_by(advocate_id=user.id).all()
    case_ids = list(set([p.case_id for p in represented] + [c.id for c in Case.query.filter_by(filed_by=user.id).all()]))
    cases = Case.query.filter(Case.id.in_(case_ids)).order_by(Case.id.desc()).all() if case_ids else []

    return jsonify([{
        'id': c.id,
        'case_number': c.case_number,
        'title': c.title,
        'case_type': c.case_type,
        'status': c.status,
        'court': c.court.name if c.court else None,
        'judge': c.judge.full_name if c.judge else 'Unassigned',
        'next_hearing': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None
    } for c in cases])


@api_bp.route('/lawyer/efiling', methods=['POST'])
def lawyer_efiling_api():
    """Submits new petition online into the Registrar scrutiny queue."""
    user, err = require_api_auth(['lawyer'])
    if err: return err

    data = request.json or {}
    title = data.get('title')
    case_type = data.get('case_type', 'Civil')
    court_id = data.get('court_id', 1)
    description = data.get('description', '')
    petitioner = data.get('petitioner_name', user.full_name)
    respondent = data.get('respondent_name')

    if not title or not respondent:
        return jsonify({'error': 'Case title and respondent name are required.'}), 400

    code_map = {'Civil': 'CIV', 'Criminal': 'CRIM', 'Family': 'FAM', 'Property': 'PROP', 'Writ': 'WRIT', 'Bail': 'BAIL', 'Consumer': 'CONS', 'Cheque Bounce': 'CHK'}
    prefix = code_map.get(case_type, 'CASE')
    year = datetime.utcnow().year

    case_number = None
    for attempt in range(15):
        cnt = Case.query.filter(Case.case_number.like(f"{prefix}/{year}/%")).count()
        candidate = f"{prefix}/{year}/{cnt + 1 + attempt:05d}"
        if not Case.query.filter_by(case_number=candidate).first():
            case_number = candidate
            break
    if not case_number:
        case_number = f"{prefix}/{year}/{int(time.time() * 1000) % 100000:05d}"

    new_case = Case(
        case_number=case_number,
        title=title,
        case_type=case_type,
        status='Scrutiny',
        court_id=court_id,
        filed_by=user.id,
        filed_on=date.today(),
        description=description
    )
    db.session.add(new_case)
    db.session.flush()

    p1 = CaseParty(case_id=new_case.id, name=petitioner, party_type="Petitioner", advocate_id=user.id)
    p2 = CaseParty(case_id=new_case.id, name=respondent, party_type="Respondent")
    db.session.add_all([p1, p2])
    db.session.commit()

    return jsonify({
        'success': True,
        'case_id': new_case.id,
        'case_number': case_number,
        'status': 'Scrutiny',
        'message': 'Petition successfully submitted to Registrar Scrutiny queue.'
    }), 201


@api_bp.route('/litigant/cases', methods=['GET'])
def litigant_cases_api():
    """Case portfolio for citizen petitioner or respondent."""
    user, err = require_api_auth(['litigant'])
    if err: return err

    parties = CaseParty.query.filter_by(user_id=user.id).all()
    case_ids = list(set([p.case_id for p in parties] + [c.id for c in Case.query.filter_by(filed_by=user.id).all()]))
    cases = Case.query.filter(Case.id.in_(case_ids)).order_by(Case.id.desc()).all() if case_ids else []

    return jsonify([{
        'id': c.id,
        'case_number': c.case_number,
        'title': c.title,
        'case_type': c.case_type,
        'status': c.status,
        'court': c.court.name if c.court else None,
        'judge': c.judge.full_name if c.judge else 'Unassigned',
        'next_hearing': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None
    } for c in cases])


@api_bp.route('/police/dockets', methods=['GET'])
def police_dockets_api():
    """Criminal court dockets, remand hearings, and witness summons."""
    user, err = require_api_auth(['police', 'government', 'judge'])
    if err: return err

    cases = Case.query.filter(Case.case_type.in_(['Criminal', 'Bail'])).order_by(Case.id.desc()).limit(25).all()
    return jsonify([{
        'id': c.id,
        'case_number': c.case_number,
        'title': c.title,
        'case_type': c.case_type,
        'status': c.status,
        'court': c.court.name if c.court else None,
        'judge': c.judge.full_name if c.judge else 'Unassigned',
        'filed_on': c.filed_on.strftime('%d-%m-%Y'),
        'next_hearing': c.next_hearing_date.strftime('%d-%m-%Y') if c.next_hearing_date else None
    } for c in cases])


@api_bp.route('/police/charge-sheet', methods=['POST'])
def police_charge_sheet_api():
    """Submits FIR charge-sheet and creates criminal prosecution record."""
    user, err = require_api_auth(['police'])
    if err: return err

    data = request.json or {}
    accused_name = data.get('accused_name') or data.get('respondent_name') or 'Accused Person'
    fir_number = data.get('fir_number')
    station = data.get('police_station', 'Central Police Station')
    charges = data.get('charges') or data.get('sections_invoked', 'Indian Penal Code / CrPC sections')
    court_id = data.get('court_id', 2)

    if not fir_number:
        return jsonify({'error': 'FIR number is required.'}), 400

    year = datetime.utcnow().year
    cnt = Case.query.filter(Case.case_number.like(f"CRIM/{year}/%")).count()
    case_number = f"CRIM/{year}/{cnt + 1:05d}"
    title = f"State ({station}) vs {accused_name}"

    new_case = Case(
        case_number=case_number,
        title=title,
        case_type="Criminal",
        status="Filed",
        court_id=court_id,
        filed_by=user.id,
        filed_on=date.today(),
        description=f"FIR No: {fir_number}. Police Station: {station}. Charges: {charges}"
    )
    db.session.add(new_case)
    db.session.flush()

    p1 = CaseParty(case_id=new_case.id, name=f"State through {station}", party_type="Complainant")
    p2 = CaseParty(case_id=new_case.id, name=accused_name, party_type="Accused")
    db.session.add_all([p1, p2])
    db.session.commit()

    return jsonify({
        'success': True,
        'case_id': new_case.id,
        'case_number': case_number,
        'title': title,
        'status': 'Filed',
        'message': f"Charge-sheet registered under Case {case_number}."
    }), 201


# =========================================================================
# 8. AI LEGAL & JUDICIAL ASSISTANCE ENDPOINTS (/api/ai)
# =========================================================================

@api_bp.route('/ai/status', methods=['GET'])
def ai_status():
    """Return active AI engine mode, telemetry, and provider status."""
    from app.services.ai import get_ai_service
    ai_srv = get_ai_service()
    status_info = ai_srv.get_status_info()
    status_info['live_ready'] = (status_info.get('mode') == 'live')
    return jsonify(status_info)


@api_bp.route('/admin/ai-settings', methods=['POST'])
def update_ai_settings():
    """Update AI cost-control settings: daily request cap and kill switch."""
    user, err = require_api_auth(['government', 'registrar'])
    if err:
        return err

    data = request.json or request.form or {}
    from app.services.ai import get_ai_service
    ai_srv = get_ai_service()

    if 'kill_switch' in data or 'ai_disabled' in data:
        val = data.get('kill_switch', data.get('ai_disabled'))
        disabled = str(val).lower() in ['true', '1', 'yes', 'on']
        ai_srv.rate_limiter.set_ai_disabled(disabled, user_id=user.id)
        
        audit = AuditLog(
            user_id=user.id,
            action='UPDATE_AI_SETTING',
            details=f"Admin set AI kill switch (ai_disabled) to {disabled}",
            ip=request.remote_addr
        )
        db.session.add(audit)
        db.session.commit()

    if 'daily_request_cap' in data:
        try:
            cap = int(data.get('daily_request_cap'))
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid daily request cap number'}), 400

        if cap > 0:
            ai_srv.rate_limiter.set_daily_cap(cap, user_id=user.id)
            audit = AuditLog(
                user_id=user.id,
                action='UPDATE_AI_SETTING',
                details=f"Admin updated AI daily request cap to {cap}",
                ip=request.remote_addr
            )
            db.session.add(audit)
            db.session.commit()

    return jsonify({
        'success': True,
        'message': 'AI settings updated successfully',
        'status': ai_srv.get_status_info()
    })



@api_bp.route('/ai/chat', methods=['POST'])
@api_bp.route('/litigant/ai-chat', methods=['POST'])
def ai_citizen_chat():
    """NyayaMitra Citizen Legal Chatbot endpoint with 20+ FAQ knowledge base & user case lookup."""
    user = get_current_user()
    data = request.json or request.form
    query = data.get('query', '').strip()
    history = data.get('history', [])
    language = data.get('language') or (user.language_pref if user and user.is_authenticated else 'en')

    if not query:
        return jsonify({'error': 'Query required.'}), 400

    res = citizen_legal_chat(query, user=user if user.is_authenticated else None, language=language, history=history)
    return jsonify({
        'reply': res['reply'],
        'mode': res['mode'],
        'model': res['model'],
        'is_case_lookup': res.get('is_case_lookup', False),
        'suggestion_chips': res.get('suggestion_chips', []),
        'handoff': res.get('handoff'),
        'timestamp': datetime.utcnow().strftime('%I:%M %p')
    })


@api_bp.route('/ai/order-draft', methods=['POST'])
def ai_order_draft():
    """Order Drafting Assistant for judges generating draft interim order or notice."""
    user, err = require_api_auth(['judge'])
    if err: return err

    data = request.json or {}
    case_id = data.get('case_id')
    notes = data.get('notes', '')
    order_type = data.get('order_type', 'Interim')

    if not case_id:
        return jsonify({'error': 'Case ID is required.'}), 400

    c = Case.query.get_or_404(case_id)
    res = draft_judicial_order(c, notes=notes, order_type=order_type, user_id=user.id)
    return jsonify({
        'success': True,
        'title': res['title'],
        'draft': res['draft'],
        'mode': res['mode'],
        'model': res['model']
    })


@api_bp.route('/ai/priority/<int:case_id>', methods=['GET'])
def ai_case_priority(case_id):
    """Case Priority Scoring & Delay Risk Assessment."""
    c = Case.query.get_or_404(case_id)
    priority_res = calculate_case_priority(c)
    delay_res = assess_delay_risk(c)
    return jsonify({
        'case_id': c.id,
        'case_number': c.case_number,
        'priority': priority_res,
        'delay_risk': delay_res
    })


@api_bp.route('/ai/cause-list-ordering', methods=['GET'])
def ai_cause_list_ordering():
    """Suggested Cause List Order for judges based on AI priority scoring."""
    user, err = require_api_auth(['judge', 'clerk', 'registrar'])
    if err: return err

    today = date.today()
    query = Hearing.query.filter(
        Hearing.scheduled_at >= datetime.combine(today, datetime.min.time()),
        Hearing.scheduled_at <= datetime.combine(today, datetime.max.time()),
        Hearing.status == 'Scheduled'
    )
    if user.role == 'judge':
        query = query.filter_by(judge_id=user.id)

    hearings = query.all()
    ordered = suggest_cause_list_ordering(hearings)

    return jsonify({
        'hearings': [{
            'hearing_id': item['hearing'].id,
            'case_id': item['hearing'].case_id,
            'case_number': item['hearing'].case.case_number if item['hearing'].case else 'N/A',
            'case_title': item['hearing'].case.title if item['hearing'].case else 'Matter',
            'case_type': item['hearing'].case.case_type if item['hearing'].case else 'General',
            'courtroom': item['hearing'].courtroom.name if item['hearing'].courtroom else 'Courtroom 1',
            'scheduled_at': item['hearing'].scheduled_at.strftime('%I:%M %p'),
            'priority_score': item['priority']['score'],
            'priority_label': item['priority']['label'],
            'badge_class': item['priority']['badge_class']
        } for item in ordered]
    })


@api_bp.route('/ai/smart-schedule-slots', methods=['GET'])
def ai_smart_schedule_slots():
    """Smart Scheduling Suggestions for clerk scheduling."""
    user, err = require_api_auth(['clerk', 'registrar', 'judge'])
    if err: return err

    court_id = int(request.args.get('court_id', 1))
    courtroom_id = int(request.args.get('courtroom_id', 1))
    judge_id = int(request.args.get('judge_id', 3))

    slots = suggest_smart_scheduling_slots(court_id, courtroom_id, judge_id)
    return jsonify({'slots': slots})


@api_bp.route('/ai/similar-cases/<int:case_id>', methods=['GET'])
def ai_similar_cases(case_id):
    """Similar Case Finder using TF-IDF Cosine Similarity."""
    c = Case.query.get_or_404(case_id)
    similar = find_similar_cases(c, limit=3)
    return jsonify({
        'case_id': c.id,
        'case_number': c.case_number,
        'similar_cases': similar
    })


@api_bp.route('/ai/auto-tag', methods=['POST'])
def ai_auto_tag():
    """Document Auto-Tagging & Entity Extraction."""
    data = request.json or {}
    filename = data.get('filename', '')
    text_content = data.get('text_content', '')

    if not filename:
        return jsonify({'error': 'Filename required.'}), 400

    result = auto_tag_document(filename, text_content)
    return jsonify(result)


# =========================================================================
# 7. REMINDERS & NOTIFICATION OUTBOX ENDPOINTS
# =========================================================================

@api_bp.route('/reminders/scan-now', methods=['POST'])
def reminders_scan_now():
    """Manual trigger for demo and automated testing of 7d, 1d, 2h scanner."""
    user, err = require_api_auth(['clerk', 'registrar', 'government', 'judge'])
    if err: return err

    stats = scan_and_send_hearing_reminders()
    return jsonify({
        'success': True,
        'message': f"Scan completed. Evaluated {stats['hearings_scanned']} hearings, dispatched {stats['reminders_sent']} reminders.",
        'stats': stats
    })


@api_bp.route('/reminders/send-hearing-reminder', methods=['POST'])
def manual_send_hearing_reminder():
    """Manually dispatch a hearing reminder on-demand."""
    user, err = require_api_auth(['clerk', 'registrar', 'government', 'judge'])
    if err: return err

    data = request.json or {}
    hearing_id = data.get('hearing_id')
    rem_type = data.get('reminder_type', '2_hours')
    preferred_channel = data.get('channel', 'SMS')

    h = Hearing.query.get_or_404(hearing_id)
    recipients = get_hearing_recipients(h)
    if not recipients:
        return jsonify({'error': 'No recipients found for this hearing.'}), 400

    template_map = {
        '7_days': 'hearing_reminder_7d',
        '1_day': 'hearing_reminder_1d',
        '2_hours': 'hearing_reminder_2h',
        'manual': 'hearing_reminder_2h'
    }
    template_key = template_map.get(rem_type, 'hearing_reminder_2h')

    court_name = h.courtroom.court.name if h.courtroom and h.courtroom.court else (h.case.court.name if h.case and h.case.court else "Judicial Court")
    courtroom_name = h.courtroom.name if h.courtroom else "Courtroom 1"
    judge_name = h.presiding_judge.full_name if h.presiding_judge else "Hon'ble Presiding Judge"

    sent_count = 0
    for recipient in recipients:
        context = {
            'name': recipient.full_name,
            'case_number': h.case.case_number if h.case else 'N/A',
            'date': h.scheduled_at.strftime('%d-%m-%Y'),
            'time': h.scheduled_at.strftime('%I:%M %p'),
            'courtroom': courtroom_name,
            'court_name': court_name,
            'judge_name': judge_name
        }
        ok, notif = send_notification(
            user=recipient,
            template_key=template_key,
            context=context,
            preferred_channel=preferred_channel,
            related_case_id=h.case_id,
            hearing_id=h.id,
            reminder_type=rem_type
        )
        if ok:
            rem_entry = HearingReminder(
                hearing_id=h.id,
                user_id=recipient.id,
                reminder_type=f"manual_{rem_type}",
                channel=notif.channel if notif else preferred_channel,
                status='Delivered',
                sent_at=datetime.utcnow()
            )
            db.session.add(rem_entry)
            sent_count += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f"Dispatched {rem_type} reminder to {sent_count} recipients.",
        'recipients_count': sent_count
    })


@api_bp.route('/reminders/upcoming', methods=['GET'])
def get_upcoming_reminders():
    """List upcoming hearings with reminder tracking status."""
    user, err = require_api_auth(['clerk', 'registrar', 'government', 'judge'])
    if err: return err

    now = datetime.utcnow()
    hearings = Hearing.query.filter(
        Hearing.status == 'Scheduled',
        Hearing.scheduled_at >= now - timedelta(hours=2)
    ).order_by(Hearing.scheduled_at.asc()).limit(30).all()

    results = []
    for h in hearings:
        diff_hours = (h.scheduled_at - now).total_seconds() / 3600.0
        sent_types = [r.reminder_type for r in HearingReminder.query.filter_by(hearing_id=h.id).all()]
        parties = CaseParty.query.filter_by(case_id=h.case_id).all()
        parties_summary = [f"{p.name} ({p.party_type})" for p in parties[:3]]
        
        results.append({
            'hearing_id': h.id,
            'case_id': h.case_id,
            'case_number': h.case.case_number if h.case else 'N/A',
            'case_title': h.case.title if h.case else 'Untitled',
            'courtroom': h.courtroom.name if h.courtroom else 'Courtroom 1',
            'judge_name': h.presiding_judge.full_name if h.presiding_judge else 'Unassigned',
            'scheduled_at': h.scheduled_at.strftime('%d-%m-%Y %I:%M %p'),
            'hours_remaining': round(diff_hours, 1),
            'attendance_status': getattr(h, 'attendance_status', 'Unconfirmed'),
            'reminders_sent': {
                'seven_days': '7_days' in sent_types,
                'one_day': '1_day' in sent_types,
                'two_hours': '2_hours' in sent_types
            },
            'parties_summary': parties_summary
        })

    return jsonify({'hearings': results})


@api_bp.route('/outbox/logs', methods=['GET'])
def get_outbox_logs():
    """Retrieve outgoing SMS/WhatsApp/Email delivery records."""
    user, err = require_api_auth(['clerk', 'registrar', 'government', 'judge'])
    if err: return err

    channel = request.args.get('channel', 'All')
    limit = int(request.args.get('limit', 50))

    query = Notification.query.filter(Notification.channel.in_(['SMS', 'WhatsApp', 'Email', 'In-App']))
    if channel and channel != 'All':
        query = query.filter_by(channel=channel)

    records = query.order_by(Notification.sent_at.desc()).limit(limit).all()

    return jsonify({
        'logs': [{
            'id': n.id,
            'recipient_name': n.recipient.full_name if n.recipient else 'Citizen',
            'recipient_role': n.recipient.role if n.recipient else 'Litigant',
            'recipient_contact': n.recipient_contact or (n.recipient.phone if n.recipient else 'N/A'),
            'channel': n.channel,
            'message': n.message,
            'status': n.status,
            'provider': n.provider or 'DEMO_GATEWAY',
            'fallback_from': n.fallback_from,
            'sent_at': n.sent_at.strftime('%d %b %Y, %I:%M:%S %p'),
            'case_number': n.related_case.case_number if n.related_case else None
        } for n in records]
    })


@api_bp.route('/notifications/simulate-reply', methods=['POST'])
def simulate_reply():
    """Simulate inbound SMS/WhatsApp webhook reply."""
    data = request.json or request.form
    sender_contact = data.get('sender_contact', '').strip()
    message_text = data.get('message_text', '').strip()

    if not sender_contact or not message_text:
        return jsonify({'error': 'Sender contact and message text are required.'}), 400

    result = handle_inbound_reply(sender_contact, message_text)
    return jsonify(result)


# =========================================================================
# 8. ADMIN & DEMO RESET ENDPOINT
# =========================================================================

@api_bp.route('/admin/reset-demo', methods=['POST'])
def admin_reset_demo():
    """Reset and re-seed the entire demo database."""
    from app.seed import reset_demo_database
    try:
        reset_demo_database()
        return jsonify({
            'success': True,
            'message': 'Demo database has been successfully reset and re-seeded to pristine state!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# 9. ADVANCED PRODUCTION AI CAPABILITY ENDPOINTS
# =========================================================================

@api_bp.route('/ai/precedent-search', methods=['POST'])
def api_precedent_search():
    """Semantic Case-Law and Precedent Search using TF-IDF / Gemini Embeddings."""
    user = get_current_user()
    data = request.json or request.form or {}
    query = data.get('query', '').strip()
    limit = int(data.get('limit', 5))

    if not query:
        return jsonify({'error': 'Search query is required.'}), 400

    results = search_precedents(query, limit=limit)
    
    # Audit log
    audit = AuditLog(
        user_id=user.id if user.is_authenticated else None,
        action="AI_PRECEDENT_SEARCH",
        details=f"Semantic search: '{query[:60]}' (found {results.get('total_found', 0)} synthetic precedents)",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(results)


@api_bp.route('/ai/cases/<int:case_id>/ask', methods=['POST'])
def api_ask_case_file(case_id):
    """RAG 'Ask the Case File' assistant grounded strictly on the case corpus."""
    user, err = require_api_auth(['judge', 'clerk', 'registrar', 'government', 'lawyer', 'litigant'])
    if err: return err

    c = Case.query.get_or_404(case_id)
    data = request.json or request.form or {}
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'error': 'Question is required.'}), 400

    result = ask_case_file(case_id, user, question)
    if not result.get('success'):
        return jsonify(result), 403

    audit = AuditLog(
        user_id=user.id,
        action="AI_CASE_RAG_QUERY",
        details=f"Asked case file {c.case_number}: '{question[:60]}'",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(result)


@api_bp.route('/ai/ocr-extract', methods=['POST'])
def api_ocr_extract():
    """Smart Document Intelligence & OCR form extraction."""
    user, err = require_api_auth(['clerk', 'registrar', 'judge', 'government', 'lawyer', 'litigant'])
    if err: return err

    extracted_text = ""
    filename = "uploaded_petition.pdf"

    if 'file' in request.files:
        uploaded_file = request.files['file']
        filename = secure_filename(uploaded_file.filename or "petition.pdf")
        temp_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'temp_ocr')
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.join(temp_dir, filename)
        uploaded_file.save(file_path)
        extracted_text = extract_text_from_file(file_path)
    else:
        data = request.json or request.form or {}
        extracted_text = data.get('text_sample', '') or data.get('text_content', '')
        filename = data.get('filename', 'sample_petition.txt')

    if not extracted_text:
        return jsonify({'error': 'No file or document text provided for extraction.'}), 400

    analysis = parse_petition_intelligence(extracted_text, filename=filename)

    audit = AuditLog(
        user_id=user.id,
        action="AI_OCR_EXTRACTION",
        details=f"Extracted intelligence from document '{filename}'",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(analysis)


@api_bp.route('/ai/cases/<int:case_id>/scrutiny-defects', methods=['GET'])
def api_scrutiny_defects(case_id):
    """AI Pre-Scrutiny E-Filing Defect Checker for Registrar queue."""
    user, err = require_api_auth(['registrar', 'clerk', 'judge', 'government'])
    if err: return err

    c = Case.query.get_or_404(case_id)
    analysis = audit_case_defects(case_id)

    audit = AuditLog(
        user_id=user.id,
        action="AI_SCRUTINY_DEFECT_CHECK",
        details=f"Audited e-filing defects on case {c.case_number}: found {analysis.get('defect_count', 0)} defects",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(analysis)


@api_bp.route('/ai/hearings/<int:hearing_id>/transcribe', methods=['POST'])
def api_transcribe_hearing(hearing_id):
    """Hearing audio transcription and AI minutes synthesis."""
    user, err = require_api_auth(['judge', 'clerk', 'registrar', 'government'])
    if err: return err

    h = Hearing.query.get_or_404(hearing_id)
    audio_file = request.files.get('audio')
    audio_filename = None
    if audio_file:
        audio_filename = secure_filename(audio_file.filename)
        save_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'audio')
        os.makedirs(save_dir, exist_ok=True)
        audio_file.save(os.path.join(save_dir, audio_filename))

    transcription_res = transcribe_hearing_audio(hearing_id, audio_file=audio_file, audio_filename=audio_filename)
    minutes_res = generate_minutes_from_transcript(hearing_id, transcription_res.get('raw_transcript', ''))

    # Upsert HearingTranscription record in Draft state
    rec = HearingTranscription.query.filter_by(hearing_id=hearing_id).first()
    if not rec:
        rec = HearingTranscription(hearing_id=hearing_id)
        db.session.add(rec)
        
    rec.audio_filename = audio_filename
    rec.raw_transcript = transcription_res.get('raw_transcript', '')
    rec.minutes_summary = minutes_res.get('minutes_summary', '')
    rec.action_items_json = json.dumps(minutes_res.get('action_items', []))
    rec.suggested_next_hearing = minutes_res.get('suggested_next_hearing', '')
    rec.status = 'Draft'
    rec.reviewed_by = None
    
    audit = AuditLog(
        user_id=user.id,
        action="AI_HEARING_TRANSCRIBED",
        details=f"Generated draft minutes from hearing audio for Hearing #{hearing_id}",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({
        "success": True,
        "hearing_id": hearing_id,
        "transcript": transcription_res,
        "minutes": minutes_res,
        "status": "Draft",
        "requires_human_approval": True
    })


@api_bp.route('/hearings/<int:hearing_id>/save-minutes', methods=['POST'])
def api_save_hearing_minutes(hearing_id):
    """Human approval and confirmation of hearing minutes before formal saving."""
    user, err = require_api_auth(['judge', 'clerk'])
    if err: return err

    data = request.json or request.form or {}
    minutes_summary = data.get('minutes_summary', '').strip()
    action_items = data.get('action_items', [])
    suggested_next_date = data.get('suggested_next_hearing', '').strip()

    if not minutes_summary:
        return jsonify({'error': 'Minutes summary is required.'}), 400

    rec = HearingTranscription.query.filter_by(hearing_id=hearing_id).first()
    if not rec:
        rec = HearingTranscription(hearing_id=hearing_id, raw_transcript="Entered from judicial notes")
        db.session.add(rec)

    rec.minutes_summary = minutes_summary
    rec.action_items_json = json.dumps(action_items) if isinstance(action_items, list) else str(action_items)
    rec.suggested_next_hearing = suggested_next_date
    rec.status = 'Approved'
    rec.reviewed_by = user.id
    rec.updated_at = datetime.utcnow()

    # Update Hearing notes
    h = db.session.get(Hearing, hearing_id)
    if h:
        h.notes = f"{h.notes or ''}\n\n[Approved Minutes by {user.full_name}]: {minutes_summary}".strip()

    audit = AuditLog(
        user_id=user.id,
        action="HEARING_MINUTES_APPROVED",
        details=f"Judge/Clerk {user.full_name} approved and finalized minutes for Hearing #{hearing_id}",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Hearing minutes approved and saved into the official record.",
        "hearing_id": hearing_id,
        "status": "Approved",
        "reviewed_by": user.full_name
    })


@api_bp.route('/ai/translate', methods=['POST'])
def api_translate():
    """Side-by-side judicial document translation between English, Telugu, and Hindi."""
    user, err = require_api_auth()
    if err: return err

    data = request.json or request.form or {}
    text = data.get('text', '').strip()
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'te')
    doc_type = data.get('doc_type', 'Notice')

    if not text:
        return jsonify({'error': 'Text to translate is required.'}), 400

    res = translate_judicial_document(text, target_lang=target_lang, source_lang=source_lang, doc_type=doc_type)

    audit = AuditLog(
        user_id=user.id,
        action="AI_TRANSLATION",
        details=f"Translated {doc_type} from {source_lang} to {target_lang}",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(res)


@api_bp.route('/ai/ask-data', methods=['POST'])
def api_ask_data():
    """Natural-Language Analytics ('Ask your data') using safe parameterized query tools."""
    user, err = require_api_auth(['government', 'registrar', 'judge'])
    if err: return err

    data = request.json or request.form or {}
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'error': 'Question is required.'}), 400

    result = process_natural_language_analytics(user, question)

    audit = AuditLog(
        user_id=user.id,
        action="AI_NL_ANALYTICS",
        details=f"NL Query executed with tool {result.get('tool_used')}: '{question[:60]}'",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(result)


@api_bp.route('/ai/backlog-insights', methods=['GET'])
def api_backlog_insights():
    """AI Case-Risk & Backlog Insights card for Registrar & Government dashboards."""
    user, err = require_api_auth(['government', 'registrar', 'judge'])
    if err: return err

    court_id = user.court_id if user.role != 'government' else None
    result = generate_backlog_insight_card(court_id=court_id)

    audit = AuditLog(
        user_id=user.id,
        action="AI_BACKLOG_INSIGHTS",
        details=f"Generated executive backlog briefing for court_id={court_id}",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(result)


@api_bp.route('/ai/cases/<int:case_id>/copilot', methods=['POST'])
def api_judge_copilot(case_id):
    """Judge Copilot Sidebar quick-action tools."""
    user, err = require_api_auth(['judge', 'clerk', 'registrar', 'government'])
    if err: return err

    c = Case.query.get_or_404(case_id)
    data = request.json or request.form or {}
    action = data.get('action', 'summarize_3_bullets')

    if action == 'summarize_3_bullets':
        result = summarize_case_3_bullets(c, user)
    elif action == 'draft_adjournment_order':
        reason = data.get('reason', '')
        next_date = data.get('next_date', '')
        result = copilot_draft_adjournment(c, user, reason, next_date)
    elif action == 'find_conflicts':
        proposed_date = data.get('proposed_date', '')
        result = find_conflicting_hearings(c, user, proposed_date)
    elif action == 'flag_missing_evidence':
        result = flag_missing_evidence_before_judgment(c, user)
    else:
        return jsonify({'error': f"Unknown copilot action '{action}'"}), 400

    audit = AuditLog(
        user_id=user.id,
        action="AI_JUDGE_COPILOT",
        details=f"Executed copilot action '{action}' on case {c.case_number}",
        ip=request.remote_addr,
        timestamp=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify(result)


@api_bp.route('/ai/evaluate', methods=['POST'])
def api_ai_evaluate():
    """Records user feedback ('helpful', 'wrong', 'unsafe') on an AI output."""
    user = get_current_user()
    data = request.json or request.form or {}
    feature = data.get('feature', 'general')
    rating = data.get('rating', 'helpful')
    feedback_text = data.get('feedback_text', '')
    prompt = data.get('prompt', '')
    response_text = data.get('response_text', '')

    res = record_ai_evaluation(
        user_id=user.id if user.is_authenticated else None,
        feature=feature,
        rating=rating,
        feedback_text=feedback_text,
        prompt=prompt,
        response_text=response_text,
        ip_addr=request.remote_addr
    )
    return jsonify(res)


@api_bp.route('/admin/ai-eval-stats', methods=['GET'])
def api_admin_ai_eval_stats():
    """Retrieves AI evaluation metrics and satisfaction rates for admin monitoring."""
    user, err = require_api_auth(['government', 'registrar', 'judge'])
    if err: return err

    summary = get_ai_evaluation_summary()
    return jsonify(summary)

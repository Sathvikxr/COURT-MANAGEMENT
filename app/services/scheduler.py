"""
NyayaDesk - APScheduler Automated Judicial Services
Runs periodic background jobs and manages event-driven instant notifications:
1. Every minute hearing scanner: 7-day, 1-day, and 2-hour reminders.
2. Duplicate suppression tracking via HearingReminder table.
3. Instant notification triggers for rescheduling, orders, filings, fees, and approvals.
"""

import atexit
import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import db, User, Hearing, Case, CaseParty, Document, Order, HearingReminder, ApprovalRequest
from app.services.notifier import send_notification

scheduler = BackgroundScheduler(daemon=True)


def get_hearing_recipients(hearing):
    """
    Collect all unique User objects affiliated with a hearing:
    - Case parties with user accounts
    - Representing advocates
    - Presiding judge
    """
    recipients = set()

    # 1. Presiding judge
    if hearing.judge_id:
        judge = db.session.get(User, hearing.judge_id)
        if judge:
            recipients.add(judge)
    elif hearing.case and hearing.case.judge_id:
        judge = db.session.get(User, hearing.case.judge_id)
        if judge:
            recipients.add(judge)

    # 2. Case parties & advocates
    if hearing.case:
        parties = CaseParty.query.filter_by(case_id=hearing.case_id).all()
        for party in parties:
            if party.user_id:
                u = db.session.get(User, party.user_id)
                if u: recipients.add(u)
            elif party.email:
                u = User.query.filter_by(email=party.email).first()
                if u: recipients.add(u)

            if party.advocate_id:
                adv = db.session.get(User, party.advocate_id)
                if adv: recipients.add(adv)

    return list(recipients)


def scan_and_send_hearing_reminders(app=None):
    """
    Core routine: Scans all upcoming Scheduled hearings.
    Evaluates 7-day, 1-day, and 2-hour reminder windows.
    Suppresses duplicates by checking HearingReminder records.
    Returns audit statistics dict: {'scanned': int, 'reminders_sent': int, 'details': list}.
    """
    stats = {
        'timestamp': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        'hearings_scanned': 0,
        'reminders_sent': 0,
        'details': []
    }

    now = datetime.utcnow()
    # Search hearings in upcoming 8-day window
    window_end = now + timedelta(days=8)
    
    hearings = Hearing.query.filter(
        Hearing.status == 'Scheduled',
        Hearing.scheduled_at >= now - timedelta(minutes=15), # Include recently started / imminent
        Hearing.scheduled_at <= window_end
    ).order_by(Hearing.scheduled_at.asc()).all()

    stats['hearings_scanned'] = len(hearings)

    for hearing in hearings:
        diff_seconds = (hearing.scheduled_at - now).total_seconds()
        diff_hours = diff_seconds / 3600.0

        target_stages = []

        # 2 Hours Window: happening in <= 2.5 hours
        if diff_seconds >= 0 and diff_hours <= 2.5:
            target_stages.append(('2_hours', 'hearing_reminder_2h'))
        # 1 Day Window: happening between 2.5 hours and 28 hours
        elif 2.5 < diff_hours <= 28.0:
            target_stages.append(('1_day', 'hearing_reminder_1d'))
        # 7 Days Window: happening between 6 days (144 hrs) and 8 days (192 hrs)
        elif 144.0 <= diff_hours <= 192.0:
            target_stages.append(('7_days', 'hearing_reminder_7d'))

        if not target_stages:
            continue

        recipients = get_hearing_recipients(hearing)
        if not recipients:
            continue

        court_name = hearing.courtroom.court.name if hearing.courtroom and hearing.courtroom.court else (hearing.case.court.name if hearing.case and hearing.case.court else "Judicial Court")
        courtroom_name = hearing.courtroom.name if hearing.courtroom else "Courtroom 1"
        judge_name = hearing.presiding_judge.full_name if hearing.presiding_judge else "Hon'ble Presiding Judge"

        for rem_type, template_key in target_stages:
            for user in recipients:
                # 1. DUPLICATE CHECK
                existing = HearingReminder.query.filter_by(
                    hearing_id=hearing.id,
                    user_id=user.id,
                    reminder_type=rem_type
                ).first()

                if existing:
                    continue # Already dispatched to this user for this milestone

                # 2. Context payload
                context = {
                    'name': user.full_name,
                    'case_number': hearing.case.case_number if hearing.case else 'N/A',
                    'date': hearing.scheduled_at.strftime('%d-%m-%Y'),
                    'time': hearing.scheduled_at.strftime('%I:%M %p'),
                    'courtroom': courtroom_name,
                    'court_name': court_name,
                    'judge_name': judge_name
                }

                # 3. Dispatch Notification
                ok, notif_rec = send_notification(
                    user=user,
                    template_key=template_key,
                    context=context,
                    preferred_channel='SMS',
                    related_case_id=hearing.case_id,
                    hearing_id=hearing.id,
                    reminder_type=rem_type
                )

                if ok:
                    # 4. Record deduplication entry
                    rem_entry = HearingReminder(
                        hearing_id=hearing.id,
                        user_id=user.id,
                        reminder_type=rem_type,
                        channel=notif_rec.channel if notif_rec else 'SMS',
                        status='Delivered',
                        sent_at=datetime.utcnow()
                    )
                    db.session.add(rem_entry)
                    db.session.commit()

                    stats['reminders_sent'] += 1
                    stats['details'].append({
                        'hearing_id': hearing.id,
                        'case_number': hearing.case.case_number if hearing.case else 'N/A',
                        'user_name': user.full_name,
                        'role': user.role,
                        'reminder_type': rem_type,
                        'channel': notif_rec.channel if notif_rec else 'SMS'
                    })

    return stats


def scheduler_cron_worker(app):
    """Execution wrapper inside Flask application context."""
    with app.app_context():
        try:
            scan_and_send_hearing_reminders(app)
        except Exception as e:
            logging.getLogger('nyayadesk.scheduler').error(f"[Scheduler Error] Error in automated hearing reminder cycle: {e}")


# --------------------------------------------------------------------------
# Instant Event-Driven Notification Helpers
# --------------------------------------------------------------------------

def notify_hearing_rescheduled(hearing, reason, new_datetime):
    """Trigger instant notifications when a judge or clerk adjourns a hearing."""
    recipients = get_hearing_recipients(hearing)
    courtroom = hearing.courtroom.name if hearing.courtroom else "Courtroom 1"
    
    for user in recipients:
        context = {
            'name': user.full_name,
            'case_number': hearing.case.case_number if hearing.case else 'N/A',
            'date': new_datetime.strftime('%d-%m-%Y'),
            'time': new_datetime.strftime('%I:%M %p'),
            'courtroom': courtroom,
            'reason': reason or 'Administrative Bench Order'
        }
        send_notification(
            user=user,
            template_key='hearing_rescheduled',
            context=context,
            preferred_channel='SMS',
            related_case_id=hearing.case_id,
            hearing_id=hearing.id
        )


def notify_new_order(order):
    """Trigger instant notifications when a judge signs and issues a judicial order."""
    case = db.session.get(Case, order.case_id)
    if not case: return

    judge = db.session.get(User, order.judge_id)
    judge_name = judge.full_name if judge else "Presiding Judge"

    # Notify parties and advocates
    parties = CaseParty.query.filter_by(case_id=case.id).all()
    recipients = set()
    for p in parties:
        if p.user: recipients.add(p.user)
        if p.advocate: recipients.add(p.advocate)

    for user in recipients:
        context = {
            'name': user.full_name,
            'case_number': case.case_number,
            'order_type': order.order_type,
            'judge_name': judge_name,
            'verification_code': order.verification_code or 'VERIFIED'
        }
        send_notification(
            user=user,
            template_key='new_order',
            context=context,
            preferred_channel='WhatsApp',
            related_case_id=case.id
        )


def notify_new_document(document):
    """Trigger instant notifications when a new petition, evidence, or affidavit is filed."""
    case = db.session.get(Case, document.case_id)
    if not case: return

    filer = db.session.get(User, document.uploaded_by)
    filer_name = filer.full_name if filer else "Registry"

    # Notify judge and opposing counsel/parties
    recipients = set()
    if case.judge_id:
        judge = db.session.get(User, case.judge_id)
        if judge and judge.id != document.uploaded_by:
            recipients.add(judge)

    for p in CaseParty.query.filter_by(case_id=case.id).all():
        if p.user and p.user.id != document.uploaded_by:
            recipients.add(p.user)
        if p.advocate and p.advocate.id != document.uploaded_by:
            recipients.add(p.advocate)

    for user in recipients:
        context = {
            'name': user.full_name,
            'case_number': case.case_number,
            'doc_title': document.filename,
            'doc_type': document.doc_type,
            'filer_name': filer_name
        }
        send_notification(
            user=user,
            template_key='new_document',
            context=context,
            preferred_channel='Email',
            related_case_id=case.id
        )


def notify_fee_due(case, amount, purpose, user):
    """Trigger instant demand notice when court fees or compliance fines are assessed."""
    context = {
        'name': user.full_name,
        'case_number': case.case_number,
        'amount': f"{amount:,.2f}",
        'purpose': purpose
    }
    send_notification(
        user=user,
        template_key='fee_due',
        context=context,
        preferred_channel='SMS',
        related_case_id=case.id
    )


def notify_account_approval(user, status, remarks=None):
    """Trigger instant notification when Government or Registrar decides an onboarding request."""
    tmpl = 'account_approved' if status == 'Approved' else 'account_rejected'
    context = {
        'name': user.full_name,
        'role': user.role.capitalize(),
        'reason': remarks or 'Administrative verification complete.'
    }
    send_notification(
        user=user,
        template_key=tmpl,
        context=context,
        preferred_channel='SMS'
    )


# --------------------------------------------------------------------------
# Scheduler Lifecycle
# --------------------------------------------------------------------------

def init_scheduler(app):
    """Initialize APScheduler with duplicate-safe 1-minute hearing scan."""
    # Suppress in automated testing environments unless explicitly requested
    if app.config.get('TESTING') or app.config.get('SCHEDULER_DISABLED'):
        return

    # Guard against duplicate scheduler instances under the Flask/Werkzeug reloader
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    if not scheduler.running:
        scheduler.add_job(
            func=scheduler_cron_worker,
            trigger="interval",
            minutes=1,
            id="hearing_reminder_scanner",
            replace_existing=True,
            args=[app]
        )
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))

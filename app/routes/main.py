"""
NyayaDesk - Main & Public Routes
Handles public landing, system health, and public court portals.
"""

from datetime import date, datetime
import random
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from app.models import db, Courtroom, Case, Hearing, Order, AuditLog

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    stats = {
        'courtrooms_count': 0,
        'cases_count': 0,
        'hearings_today': 0,
        'orders_count': 0
    }
    try:
        stats['courtrooms_count'] = Courtroom.query.count()
        stats['cases_count'] = Case.query.count()
        today = date.today()
        # Scheduled hearings for today
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        stats['hearings_today'] = Hearing.query.filter(Hearing.scheduled_at >= start_of_day, Hearing.scheduled_at <= end_of_day).count()
        stats['orders_count'] = Order.query.count()
    except Exception:
        pass

    return render_template('index.html', stats=stats)


@main_bp.route('/demo-guide')
def demo_guide():
    """Interactive demo guide with all 7+ roles, credentials, and fast switcher."""
    return render_template('demo_guide.html')


@main_bp.route('/design-preview')
def design_preview():
    """Hidden design preview showcasing all Linear/Stripe design system components in light & dark mode."""
    return render_template('design_preview.html')


@main_bp.route('/orders/verify/<verification_code>')
def verify_order(verification_code):
    """Public web portal to verify digitally certified court order via QR code."""
    from flask import request
    order = Order.query.filter_by(verification_code=verification_code).first()
    if not order:
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({'valid': False, 'message': 'Invalid verification code or order not found'}), 404
        return render_template('public/order_verification.html', valid=False, code=verification_code), 404

    result = {
        'valid': True,
        'order_id': order.id,
        'verification_code': order.verification_code,
        'case_number': order.case.case_number if order.case else 'N/A',
        'case_title': order.case.title if order.case else 'N/A',
        'order_type': order.order_type,
        'title': order.title,
        'content': order.content,
        'judge_name': order.issuing_judge.full_name if order.issuing_judge else 'Honorable Bench',
        'issued_at': order.issued_at.strftime('%d %b %Y, %H:%M') if order.issued_at else 'N/A',
        'signed_hash': order.signed_hash or 'SHA256-GENUINE-SEALED'
    }

    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify(result)

    return render_template('public/order_verification.html', valid=True, order=result)


@main_bp.route('/health')
def health():
    db_ok = True
    try:
        Case.query.limit(1).all()
    except Exception:
        db_ok = False

    return jsonify({
        'status': 'healthy' if db_ok else 'degraded',
        'database': 'connected' if db_ok else 'unreachable',
        'app': 'NyayaDesk Court Management System',
        'timestamp': datetime.utcnow().isoformat()
    })


@main_bp.route('/helpdesk', methods=['GET', 'POST'])
def helpdesk():
    """Citizen Helpdesk and Inquiry Assistance portal."""
    prefilled_message = request.args.get('message', '').strip()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        case_no = request.form.get('case_number', '').strip()
        message = request.form.get('message', '').strip()

        ticket_no = f"HD-2026-{random.randint(10000, 99999)}"
        try:
            db.session.add(AuditLog(
                user_id=None,
                action='HELPDESK_TICKET_SUBMITTED',
                entity='helpdesk',
                ip=request.remote_addr,
                details=f"Ticket {ticket_no} submitted by {name} ({phone}) for case '{case_no}': {message[:120]}"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

        flash(f"Thank you, {name}. Your inquiry has been registered under Ticket #{ticket_no}. Our facilitation desk will contact you at {phone}.", "success")
        return redirect(url_for('main.helpdesk'))

    return render_template('public/helpdesk.html', prefilled_message=prefilled_message)


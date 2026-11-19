"""
NyayaDesk - Court Management System Application Factory
Configures SQLite database, session authentication, blueprints, and APScheduler.
"""

import os
import secrets
import hmac
from datetime import timedelta
from flask import Flask, request, session, jsonify, abort, render_template, send_from_directory
from app.models import db
from app.auth import auth_bp, get_current_user
from app.routes.main import main_bp
from app.routes.dashboards import dashboards_bp
from app.routes.api import api_bp
from app.services.scheduler import init_scheduler

# Ensure pure-Python SQLAlchemy compatibility in Windows AppLocker environments
os.environ['DISABLE_SQLALCHEMY_CEXT'] = '1'

def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates')),
        static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
    )

    # Database configuration
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, 'court.db').replace('\\', '/')

    # Secure uploads directory stored outside public static tree
    upload_dir = os.path.abspath(os.path.join(data_dir, 'uploads'))
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(os.path.join(upload_dir, 'id_proofs'), exist_ok=True)
    os.makedirs(os.path.join(upload_dir, 'cases'), exist_ok=True)

    is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('ENV') == 'production'

    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'nyayadesk-judicial-session-secret-2026'),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=32 * 1024 * 1024, # 32 MB max file upload
        UPLOAD_FOLDER=upload_dir,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=is_production,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60)
    )

    if test_config:
        app.config.update(test_config)

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(api_bp)

    # Favicon serving route
    @app.route('/favicon.ico')
    def favicon():
        img_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'img'))
        return send_from_directory(img_dir, 'favicon.svg', mimetype='image/svg+xml')

    # Security & CSRF Interceptor
    @app.before_request
    def enforce_security_and_csrf():
        # Block unauthorized direct browsing of static uploads if requested
        if request.path.startswith('/static/uploads'):
            abort(403)

        # Ensure session has CSRF token
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(16)

        # Validate CSRF on all state-changing methods
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Allow tests to disable CSRF if explicitly configured
            if app.config.get('WTF_CSRF_ENABLED') is False or app.config.get('TESTING_CSRF_DISABLED') is True:
                return

            token = (
                request.headers.get('X-CSRFToken') or
                request.headers.get('X-CSRF-Token') or
                request.form.get('csrf_token') or
                request.form.get('_csrf_token')
            )
            if not token and request.is_json and isinstance(request.json, dict):
                token = request.json.get('csrf_token')

            expected = session.get('_csrf_token')
            if not token or not expected or not hmac.compare_digest(str(token), str(expected)):
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'CSRF token missing or invalid'}), 403
                return render_template('errors/403.html'), 403

    # Security Response Headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        return response

    # Custom Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def access_forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    # Context processors for global template helpers
    @app.context_processor
    def inject_global_template_vars():
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(16)
        return {
            'current_user': get_current_user(),
            'app_name': 'NyayaDesk',
            'csrf_token': lambda: session.get('_csrf_token', '')
        }

    # Initialize scheduler
    with app.app_context():
        init_scheduler(app)

    return app

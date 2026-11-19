"""
NyayaDesk - Main Application Entrypoint
Serves the Court Management System at http://localhost:8000
Auto-creates database tables and seeds demo data on first startup.
"""

import os
import sys

# Ensure project root is in Python module search path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ['DISABLE_SQLALCHEMY_CEXT'] = '1'

from app import create_app
from app.models import db, User, apply_schema_migrations
from app.seed import seed_demo_data, ensure_reminder_demo_hearings

app = create_app()

def initialize_database():
    """Verify database existence, create tables, apply migrations, and seed demo records."""
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    with app.app_context():
        db.create_all()
        apply_schema_migrations(db.engine)
        # Check if database is populated
        if not User.query.first():
            print(">>> First-time initialization: creating schema and seeding demo data...")
            seed_demo_data()
        else:
            print(">>> Court database verified. Existing records loaded.")
            ensure_reminder_demo_hearings()

if __name__ == '__main__':
    initialize_database()
    print("=" * 70)
    print("  NYAYADESK - COURT MANAGEMENT SYSTEM")
    print("  Serving at: http://localhost:8000")
    print("  Database:   C:\\CourtMS\\data\\court.db")
    print("  Demo Roles: Government, Registrar, Judge, Clerk, Lawyer, Litigant, Police")
    print("=" * 70)
    app.run(host='0.0.0.0', port=8000, debug=False)

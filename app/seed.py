"""
NyayaDesk - Comprehensive Demo Database Seeder
Populates courts, courtrooms, users across all 7 roles,
pending approval requests, and 25 realistic legal cases across all statuses.
"""

import json
from datetime import date, datetime, timedelta
from app.models import (
    db, User, Court, Courtroom, Case, CaseParty, Hearing,
    Document, Order, Payment, Notification, AuditLog, ApprovalRequest
)

def seed_demo_data(force=False):
    """Populate database with complete initial demo dataset."""
    if not force and User.query.first():
        return

    print(">>> Seeding NyayaDesk Judicial Database...")

    # =========================================================================
    # 1. COURTS (3 Courts)
    # =========================================================================
    c1 = Court(
        name="High Court of Delhi",
        type="High",
        city="New Delhi",
        state="Delhi",
        address="Sher Shah Road, Near India Gate, New Delhi - 110003",
        code="DLHC01"
    )
    c2 = Court(
        name="Patiala House District Courts Complex",
        type="District",
        city="New Delhi",
        state="Delhi",
        address="India Gate Circle, New Delhi - 110001",
        code="PHDC01"
    )
    c3 = Court(
        name="Saket District & Family Court Complex",
        type="Family",
        city="South Delhi",
        state="Delhi",
        address="Press Enclave Marg, Saket, New Delhi - 110017",
        code="SKFC01"
    )
    db.session.add_all([c1, c2, c3])
    db.session.flush()

    # =========================================================================
    # 2. COURTROOMS (5 Courtrooms)
    # =========================================================================
    cr1 = Courtroom(court_id=c1.id, name="Courtroom 1 (Chief Justice Division Bench)", capacity=85)
    cr2 = Courtroom(court_id=c1.id, name="Courtroom 4 (Commercial Appellate Division)", capacity=60)
    cr3 = Courtroom(court_id=c2.id, name="Courtroom 101 (Special Sessions Court - CBI/NIA)", capacity=50)
    cr4 = Courtroom(court_id=c2.id, name="Courtroom 105 (Chief Metropolitan Magistrate)", capacity=45)
    cr5 = Courtroom(court_id=c3.id, name="Family Courtroom 2 (Mediation & Matrimonial)", capacity=40)
    db.session.add_all([cr1, cr2, cr3, cr4, cr5])
    db.session.flush()

    # =========================================================================
    # 3. USERS (Roles: government, registrar, judge, clerk, lawyer, litigant, police)
    # =========================================================================

    # 3.1 Government Admin
    gov_user = User(
        full_name="Shri Alok Vardhan (Joint Secretary, Ministry of Law & Justice)",
        email="gov@nyaya.in",
        phone="9810011001",
        role="government",
        status="active",
        designation="Joint Secretary (Judicial Administration)",
        id_proof_no="GOV-IND-2024-001"
    )
    gov_user.set_password("Gov@12345")

    # 3.2 Approved Registrar
    reg_user = User(
        full_name="Shri V. K. Malhotra (Registrar General)",
        email="registrar@nyaya.in",
        phone="9810011002",
        role="registrar",
        status="active",
        court_id=c1.id,
        designation="Registrar General",
        id_proof_no="REG-HC-0042",
        approved_by=1, # self-referenced or gov
        approved_at=datetime.utcnow() - timedelta(days=90)
    )
    reg_user.set_password("Reg@12345")

    # 3.3 Approved Judges (2)
    judge1 = User(
        full_name="Hon'ble Justice Rajesh Sharma",
        email="judge1@nyaya.in",
        phone="9810011003",
        role="judge",
        status="active",
        court_id=c1.id,
        designation="High Court Judge (Division Bench)",
        id_proof_no="JUD-DEL-0104",
        approved_at=datetime.utcnow() - timedelta(days=120)
    )
    judge1.set_password("Judge@12345")

    judge2 = User(
        full_name="Hon'ble Justice Meenakshi Iyer",
        email="judge2@nyaya.in",
        phone="9810011004",
        role="judge",
        status="active",
        court_id=c2.id,
        designation="District & Sessions Judge",
        id_proof_no="JUD-DEL-0208",
        approved_at=datetime.utcnow() - timedelta(days=100)
    )
    judge2.set_password("Judge@12345")

    # 3.4 Approved Clerk (1)
    clerk = User(
        full_name="Sunil Gupta (Court Master / Bench Clerk)",
        email="clerk@nyaya.in",
        phone="9810011005",
        role="clerk",
        status="active",
        court_id=c1.id,
        designation="Court Master Room 1",
        id_proof_no="CLK-EMP-8831",
        approved_at=datetime.utcnow() - timedelta(days=60)
    )
    clerk.set_password("Clerk@12345")

    # 3.5 Approved Lawyers (2)
    lawyer1 = User(
        full_name="Adv. Amit Verma",
        email="lawyer1@nyaya.in",
        phone="9810011006",
        role="lawyer",
        status="active",
        designation="Senior Advocate",
        id_proof_no="D/1482/2012"
    )
    lawyer1.set_password("Lawyer@12345")

    lawyer2 = User(
        full_name="Adv. Sunita Kapoor",
        email="lawyer2@nyaya.in",
        phone="9810011007",
        role="lawyer",
        status="active",
        designation="Advocate on Record",
        id_proof_no="D/983/2015"
    )
    lawyer2.set_password("Lawyer@12345")

    # 3.6 Approved Litigants (3)
    lit1 = User(
        full_name="Ramesh Chandra Gupta",
        email="litigant1@nyaya.in",
        phone="9810011008",
        role="litigant",
        status="active",
        designation="Citizen / Petitioner",
        id_proof_no="XXXX-XXXX-4819"
    )
    lit1.set_password("Litigant@12345")

    lit2 = User(
        full_name="Priya Sundaram",
        email="litigant2@nyaya.in",
        phone="9810011009",
        role="litigant",
        status="active",
        designation="Citizen / Complainant",
        id_proof_no="XXXX-XXXX-9120"
    )
    lit2.set_password("Litigant@12345")

    lit3 = User(
        full_name="Vikramaditya Oberoi",
        email="litigant3@nyaya.in",
        phone="9810011010",
        role="litigant",
        status="active",
        designation="Managing Director, Apex Corp",
        id_proof_no="XXXX-XXXX-3341"
    )
    lit3.set_password("Litigant@12345")

    # 3.7 Approved Police Officer (1)
    police = User(
        full_name="Inspector Devinder Negi (SHO Tilak Marg)",
        email="police@nyaya.in",
        phone="9810011011",
        role="police",
        status="active",
        designation="Station House Officer",
        id_proof_no="DL-POL-7729"
    )
    police.set_password("Police@12345")

    # =========================================================================
    # 3.8 PENDING USERS (2 Judges + 1 Registrar waiting for Government Review)
    # =========================================================================
    pending_judge1 = User(
        full_name="Hon'ble Justice Rameshwar Rao",
        email="judge_pending1@nyaya.in",
        phone="9810011012",
        role="judge",
        status="pending_gov",
        court_id=c1.id,
        designation="Additional Sessions Judge",
        id_proof_no="JUD-APPL-9901"
    )
    pending_judge1.set_password("Judge@12345")

    pending_judge2 = User(
        full_name="Hon'ble Justice Ananya Sen",
        email="judge_pending2@nyaya.in",
        phone="9810011013",
        role="judge",
        status="pending_gov",
        court_id=c2.id,
        designation="Metropolitan Magistrate (Fast Track)",
        id_proof_no="JUD-APPL-9902"
    )
    pending_judge2.set_password("Judge@12345")

    pending_reg = User(
        full_name="Shri K. S. Raman",
        email="reg_pending@nyaya.in",
        phone="9810011014",
        role="registrar",
        status="pending_gov",
        court_id=c2.id,
        designation="Registrar (Judicial Scrutiny)",
        id_proof_no="REG-APPL-7714"
    )
    pending_reg.set_password("Reg@12345")

    db.session.add_all([
        gov_user, reg_user, judge1, judge2, clerk,
        lawyer1, lawyer2, lit1, lit2, lit3, police,
        pending_judge1, pending_judge2, pending_reg
    ])
    db.session.flush()

    # Link approver ID
    reg_user.approved_by = gov_user.id
    judge1.approved_by = gov_user.id
    judge2.approved_by = gov_user.id
    clerk.approved_by = reg_user.id

    # =========================================================================
    # 4. APPROVAL REQUESTS (Pending in Government Dashboard)
    # =========================================================================
    app_req1 = ApprovalRequest(
        applicant_user_id=pending_judge1.id,
        requested_role="judge",
        court_name=c1.name,
        details_json=json.dumps({
            "employee_id": "JUD-APPL-9901",
            "designation": "Additional Sessions Judge",
            "years_service": "14 Years Higher Judicial Service",
            "cadre": "Delhi Higher Judicial Service (DHJS)",
            "submitted_docs": "Service_Appointment_Gazette.pdf"
        }),
        status="Pending",
        created_at=datetime.utcnow() - timedelta(hours=36)
    )

    app_req2 = ApprovalRequest(
        applicant_user_id=pending_judge2.id,
        requested_role="judge",
        court_name=c2.name,
        details_json=json.dumps({
            "employee_id": "JUD-APPL-9902",
            "designation": "Metropolitan Magistrate (Fast Track)",
            "years_service": "8 Years Judicial Service",
            "cadre": "Delhi Judicial Service (DJS)",
            "submitted_docs": "Oath_Commission_Certificate.pdf"
        }),
        status="Pending",
        created_at=datetime.utcnow() - timedelta(hours=18)
    )

    app_req3 = ApprovalRequest(
        applicant_user_id=pending_reg.id,
        requested_role="registrar",
        court_name=c2.name,
        details_json=json.dumps({
            "employee_id": "REG-APPL-7714",
            "designation": "Registrar (Judicial Scrutiny)",
            "years_service": "21 Years Court Administration",
            "submitted_docs": "Deputation_Order_LawMinistry.pdf"
        }),
        status="Pending",
        created_at=datetime.utcnow() - timedelta(hours=12)
    )

    db.session.add_all([app_req1, app_req2, app_req3])
    db.session.flush()

    # =========================================================================
    # 5. CASES (25 Cases Across All Statuses)
    # Statuses: Filed, Scrutiny, Registered, Hearing, Reserved, Judgment, Disposed, Appealed
    # Types: Civil, Criminal, Family, Property, Cheque Bounce, Bail, Writ, Consumer
    # =========================================================================
    today = date.today()

    cases_data = [
        # FILED (3)
        ("CIV/2026/00010", "Surya Enterprises vs. Global Tech Logistics", "Civil", "Filed", "Normal", c1.id, judge1.id, lit3.id, today - timedelta(days=2), "Commercial dispute for non-delivery of industrial hardware supplies.", today + timedelta(days=12)),
        ("BAIL/2026/00011", "Harmanpreet Singh vs. State (NCT of Delhi)", "Bail", "Filed", "Urgent", c2.id, judge2.id, lit1.id, today - timedelta(days=1), "Urgent regular bail application in FIR 412/2025 PS Tilak Marg.", today + timedelta(days=1)),
        ("PROP/2026/00012", "Mohan Lal Sharma vs. Delhi Development Authority", "Property", "Filed", "Normal", c1.id, judge1.id, lit1.id, today - timedelta(days=3), "Suit for permanent injunction restraining unauthorized encroachment.", today + timedelta(days=15)),

        # SCRUTINY (3)
        ("WRIT/2026/00020", "Ramesh Chandra Gupta vs. Municipal Corporation of Delhi", "Writ", "Scrutiny", "High", c1.id, judge1.id, lit1.id, today - timedelta(days=6), "Writ petition under Article 226 challenging arbitrary sealing notice.", today + timedelta(days=8)),
        ("CHK/2026/00021", "Apex Logistics Ltd. vs. Om Trading Co.", "Cheque Bounce", "Scrutiny", "Normal", c2.id, judge2.id, lit3.id, today - timedelta(days=7), "Complaint under Section 138 Negotiable Instruments Act for cheque dishonor.", today + timedelta(days=14)),
        ("FAM/2026/00022", "Priya Sundaram vs. Karthik Sundaram", "Family", "Scrutiny", "Normal", c3.id, judge2.id, lit2.id, today - timedelta(days=8), "Petition under Section 13(1)(ia) of Hindu Marriage Act for dissolution of marriage.", today + timedelta(days=10)),

        # REGISTERED (3)
        ("CIV/2026/00030", "Bharat Petroleum Workers Union vs. Union of India", "Civil", "Registered", "Normal", c1.id, judge1.id, lit1.id, today - timedelta(days=14), "Service dispute regarding revision of retirement pension benefits.", today + timedelta(days=18)),
        ("CRIM/2026/00031", "State vs. Gurpreet & Ors.", "Criminal", "Registered", "High", c2.id, judge2.id, lit1.id, today - timedelta(days=15), "Sessions trial under Section 307/34 Indian Penal Code.", today + timedelta(days=5)),
        ("CONS/2026/00032", "Deepak Verma vs. Skylark Realtors Pvt Ltd", "Consumer", "Registered", "Normal", c2.id, judge2.id, lit2.id, today - timedelta(days=16), "Consumer grievance claiming refund and interest on delayed flat possession.", today + timedelta(days=20)),

        # HEARING (6)
        ("WRIT/2026/00040", "Citizens Coalition for Clean Air vs. Environment Pollution Board", "Writ", "Hearing", "Urgent", c1.id, judge1.id, lit1.id, today - timedelta(days=25), "Public Interest Litigation demanding strict emergency air quality monitoring.", today),
        ("CRIM/2026/00041", "State (NCT of Delhi) vs. Virender Tyagi", "Criminal", "Hearing", "High", c2.id, judge2.id, lit1.id, today - timedelta(days=30), "Prosecution evidence and cross-examination of Investigating Officer.", today),
        ("CIV/2026/00042", "Northern Power Grid Ltd vs. Apex Infrastructure Pvt Ltd", "Civil", "Hearing", "Normal", c1.id, judge1.id, lit3.id, today - timedelta(days=45), "Contractual dispute over transmission corridor expansion delays.", today + timedelta(days=2)),
        ("FAM/2026/00043", "Sunita Rao vs. Anand Rao", "Family", "Hearing", "Normal", c3.id, judge2.id, lit2.id, today - timedelta(days=40), "Application for interim maintenance under Section 125 CrPC.", today + timedelta(days=4)),
        ("PROP/2026/00044", "Estate of Late Justice Mukherjee vs. Heritage Builders", "Property", "Hearing", "Normal", c1.id, judge1.id, lit2.id, today - timedelta(days=50), "Dispute over title deed partition and boundary demarcation.", today + timedelta(days=7)),
        ("CHK/2026/00045", "Evergreen Seeds Corp vs. Kisan Mandi Syndicate", "Cheque Bounce", "Hearing", "Normal", c2.id, judge2.id, lit3.id, today - timedelta(days=28), "Cross-examination of complainant under Section 145(2) NI Act.", today + timedelta(days=3)),

        # RESERVED (3)
        ("CIV/2026/00050", "National Highway Authority vs. Larsen Builders Consortium", "Civil", "Reserved", "High", c1.id, judge1.id, lit3.id, today - timedelta(days=70), "Final arguments concluded; judgment reserved on arbitration challenge under Section 34.", today + timedelta(days=5)),
        ("BAIL/2026/00051", "Dr. Subhash Chandra vs. Directorate of Enforcement", "Bail", "Reserved", "Urgent", c2.id, judge2.id, lit1.id, today - timedelta(days=20), "Order reserved on regular bail application under Prevention of Money Laundering Act.", today + timedelta(days=2)),
        ("CONS/2026/00052", "Aakash Educational Foundation vs. National Cyber Insurance", "Consumer", "Reserved", "Normal", c2.id, judge2.id, lit3.id, today - timedelta(days=60), "Arguments concluded on insurance claim repudiation due to cyber extortion.", today + timedelta(days=6)),

        # JUDGMENT (3)
        ("WRIT/2026/00060", "Federation of Retailers vs. Department of Revenue", "Writ", "Judgment", "High", c1.id, judge1.id, lit3.id, today - timedelta(days=90), "Pronouncement of judgment on constitutional validity of municipal turnover cess.", today),
        ("CRIM/2026/00061", "State vs. Munna Lal & Anr.", "Criminal", "Judgment", "High", c2.id, judge2.id, lit1.id, today - timedelta(days=110), "Verdict on prosecution charge of criminal conspiracy and forgery.", today),
        ("FAM/2026/00062", "Kavita Mehra vs. Rohit Mehra", "Family", "Judgment", "Normal", c3.id, judge2.id, lit2.id, today - timedelta(days=80), "Final decree of mutual consent divorce and permanent alimony settlement.", today + timedelta(days=1)),

        # DISPOSED (3)
        ("CIV/2026/00070", "Tata Power Delhi Distribution vs. Delhi Jal Board", "Civil", "Disposed", "Normal", c1.id, judge1.id, lit3.id, today - timedelta(days=140), "Decreed: Amicable settlement recorded before High Court Mediation Centre.", None),
        ("CHK/2026/00071", "Sanjay Aggarwal vs. M/s Star Metals", "Cheque Bounce", "Disposed", "Normal", c2.id, judge2.id, lit1.id, today - timedelta(days=100), "Dismissed as withdrawn upon receipt of total compromise payment of INR 8.5 Lakhs.", None),
        ("PROP/2026/00072", "Anand Swaroop vs. Municipal Council", "Property", "Disposed", "Normal", c2.id, judge2.id, lit1.id, today - timedelta(days=130), "Disposed: Demolition notice set aside with directions to conduct fresh inspection.", None),

        # APPEALED (2)
        ("CRIM/2026/00080", "Ravindra Kumar vs. State (CBI)", "Criminal", "Appealed", "Urgent", c1.id, judge1.id, lit1.id, today - timedelta(days=160), "Criminal Appeal against conviction in Special CBI Court ACB 04/2022.", today + timedelta(days=9)),
        ("CIV/2026/00081", "Delhi Metro Rail Corp vs. Pioneer Engineering Ltd", "Civil", "Appealed", "High", c1.id, judge1.id, lit3.id, today - timedelta(days=180), "Special Commercial Appeal impugning Division Bench single-judge arbitral award setting aside.", today + timedelta(days=11))
    ]

    created_cases = []
    for c_data in cases_data:
        case_obj = Case(
            case_number=c_data[0],
            title=c_data[1],
            case_type=c_data[2],
            status=c_data[3],
            priority=c_data[4],
            court_id=c_data[5],
            judge_id=c_data[6],
            filed_by=c_data[7],
            filed_on=c_data[8],
            description=c_data[9],
            next_hearing_date=c_data[10]
        )
        db.session.add(case_obj)
        created_cases.append(case_obj)

    db.session.flush()

    # =========================================================================
    # 6. CASE PARTIES, HEARINGS, DOCUMENTS, ORDERS, PAYMENTS
    # =========================================================================
    for idx, cs in enumerate(created_cases):
        # Parties
        p1 = CaseParty(
            case_id=cs.id,
            user_id=lit1.id if idx % 3 == 0 else (lit2.id if idx % 3 == 1 else lit3.id),
            name="Petitioner Party",
            party_type="Petitioner" if cs.case_type != 'Criminal' else "Complainant",
            advocate_id=lawyer1.id,
            phone="9811122233",
            email="petitioner@demo.in"
        )
        p2 = CaseParty(
            case_id=cs.id,
            user_id=None,
            name="Respondent Party",
            party_type="Respondent" if cs.case_type != 'Criminal' else "Accused",
            advocate_id=lawyer2.id,
            phone="9822233344",
            email="respondent@demo.in"
        )
        db.session.add_all([p1, p2])

        # Hearings
        h_status = "Scheduled"
        if cs.status in ['Disposed', 'Judgment']:
            h_status = "Completed"
        elif cs.status == 'Hearing':
            h_status = "Scheduled"

        hearing_obj = Hearing(
            case_id=cs.id,
            courtroom_id=cr1.id if cs.court_id == c1.id else (cr3.id if cs.court_id == c2.id else cr5.id),
            judge_id=cs.judge_id,
            scheduled_at=datetime.combine(cs.next_hearing_date or today, datetime.min.time()) + timedelta(hours=10, minutes=30),
            purpose=f"Hearing & Arguments on {cs.case_type}",
            status=h_status,
            notes=f"Court proceedings on matter {cs.case_number}."
        )
        db.session.add(hearing_obj)

        # Document
        doc = Document(
            case_id=cs.id,
            uploaded_by=lawyer1.id,
            filename=f"Main_Petition_{cs.case_number.replace('/', '_')}.pdf",
            stored_path=f"uploads/cases/petition_{cs.id}.pdf",
            doc_type="Petition",
            version=1,
            visibility="Public"
        )
        db.session.add(doc)

        # Order (for hearings, judgments, or disposed matters)
        if cs.status in ['Hearing', 'Reserved', 'Judgment', 'Disposed', 'Appealed']:
            order_type = "Judgment" if cs.status in ['Judgment', 'Disposed'] else "Interim"
            ord_obj = Order(
                case_id=cs.id,
                judge_id=cs.judge_id or judge1.id,
                title=f"Court Order on {cs.case_number}",
                content=f"IN THE COURT OF {cs.court.name}\nCase No: {cs.case_number}\n\nHaving perused the record and after hearing arguments of counsel for the parties, the court hereby directs status quo and lists the matter for compliance.",
                order_type=order_type,
                signed_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                verification_code=f"NYAYA-ORD-{cs.id:04d}-2026",
                issued_at=datetime.utcnow() - timedelta(days=idx + 1)
            )
            db.session.add(ord_obj)

        # Payment
        pay = Payment(
            case_id=cs.id,
            user_id=cs.filed_by or lit1.id,
            amount=500.0 if cs.case_type in ['Writ', 'Civil'] else 250.0,
            purpose="Court E-Filing & Registry Scrutiny Fee",
            status="Completed",
            reference=f"PAY-NYAYA-{cs.id:05d}-2026",
            paid_at=datetime.utcnow() - timedelta(days=idx + 3)
        )
        db.session.add(pay)

    # Initial System Audit Log
    db.session.add(AuditLog(
        user_id=gov_user.id,
        action="SYSTEM_INIT_SEED",
        entity="system",
        entity_id=1,
        ip="127.0.0.1",
        details="Seeded complete judicial environment with 3 courts, 5 courtrooms, 14 users (including 3 pending approvals) and 25 active cases."
    ))

    db.session.commit()
    print(">>> Seed completed successfully: 3 Courts, 5 Courtrooms, 14 Users, 25 Cases, 3 Pending Approvals created.")
    ensure_reminder_demo_hearings()

    # Seed synthetic judicial precedents library
    try:
        from app.services.ai.precedents import seed_precedents_if_needed
        seed_precedents_if_needed()
        print(">>> Seeded 30 synthetic judicial precedents.")
    except Exception as e:
        print(">>> Precedent seed skipped or failed:", e)


def ensure_reminder_demo_hearings():
    """Ensure hearings exist within the next 2 hours, tomorrow, and in 7 days for live reminder demo."""
    now = datetime.utcnow()
    
    # 1. Urgent Hearing (within 1 hr 15 mins)
    urgent = Hearing.query.filter(
        Hearing.status == 'Scheduled',
        Hearing.scheduled_at >= now,
        Hearing.scheduled_at <= now + timedelta(hours=2, minutes=15)
    ).first()

    cases = Case.query.filter_by(status='Hearing').all()
    if not cases:
        cases = Case.query.all()

    if not cases:
        return

    if not urgent:
        c1 = cases[0]
        h1 = Hearing(
            case_id=c1.id,
            courtroom_id=c1.court.courtrooms.first().id if c1.court and c1.court.courtrooms.count() else 1,
            judge_id=c1.judge_id or 3,
            scheduled_at=now + timedelta(hours=1, minutes=15),
            purpose="Urgent Interim Injunction & Stay Petition",
            status="Scheduled",
            notes="Matter listed for urgent hearing in 2-hour window."
        )
        db.session.add(h1)

    # 2. Tomorrow Hearing (within 23.5 hours)
    tomorrow_h = Hearing.query.filter(
        Hearing.status == 'Scheduled',
        Hearing.scheduled_at >= now + timedelta(hours=18),
        Hearing.scheduled_at <= now + timedelta(hours=26)
    ).first()

    if not tomorrow_h:
        c2 = cases[1 % len(cases)]
        h2 = Hearing(
            case_id=c2.id,
            courtroom_id=c2.court.courtrooms.first().id if c2.court and c2.court.courtrooms.count() else 1,
            judge_id=c2.judge_id or 4,
            scheduled_at=now + timedelta(hours=23, minutes=30),
            purpose="Daily Cause List Witness Examination & Arguments",
            status="Scheduled",
            notes="Matter listed on tomorrow's daily cause list."
        )
        db.session.add(h2)

    # 3. 7 Days Hearing (within 7 days)
    advance_h = Hearing.query.filter(
        Hearing.status == 'Scheduled',
        Hearing.scheduled_at >= now + timedelta(days=6, hours=12),
        Hearing.scheduled_at <= now + timedelta(days=7, hours=12)
    ).first()

    if not advance_h:
        c3 = cases[2 % len(cases)]
        h3 = Hearing(
            case_id=c3.id,
            courtroom_id=c3.court.courtrooms.first().id if c3.court and c3.court.courtrooms.count() else 1,
            judge_id=c3.judge_id or 3,
            scheduled_at=now + timedelta(days=7),
            purpose="Framing of Issues & Preliminary Directions",
            status="Scheduled",
            notes="Advance 7-day listing."
        )
        db.session.add(h3)

    db.session.commit()
    print(">>> Verified reminder demo hearings: active listings present in 2-hour, 1-day, and 7-day windows.")


def reset_demo_database():
    """Wipe database, apply schema migrations, and re-seed all tables."""
    from app.models import apply_schema_migrations
    db.session.remove()
    db.engine.dispose() # Cleanly release SQLite file locks on Windows
    db.drop_all()
    db.create_all()
    apply_schema_migrations(db.engine)
    seed_demo_data(force=True)
    ensure_reminder_demo_hearings()
    print(">>> Complete demo database reset finished successfully.")
    return True

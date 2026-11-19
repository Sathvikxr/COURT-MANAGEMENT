# NyayaDesk Database Schema Specification

This document details the complete relational database architecture for **NyayaDesk**, stored in SQLite at `C:\CourtMS\data\court.db`. The system comprises 13 interconnected tables designed for judicial administration, electronic filing, courtroom scheduling, cryptographic verification, automated multi-channel notifications, and immutable audit trails.

---

## Entity-Relationship Diagram (Conceptual)

```
       +------------------+         +------------------+
       |      courts      |<--------|    courtrooms    |
       +------------------+         +------------------+
            ^         ^                      ^
            |         |                      |
            |   +---------------+            |
            |   |     users     |            |
            |   +---------------+            |
            |     ^    ^   ^   ^             |
            |     |    |   |   |             |
            |     |    |   |   +------+      |
            |     |    |   |          |      |
       +------------------+           |      |
       |      cases       |           |      |
       +------------------+           |      |
         |     |    |     |           |      |
         v     v    v     v           v      |
    +-------+ +----+ +-----+     +--------+  |
    |parties| |docs| |order|     |approval|  |
    +-------+ +----+ +-----+     +--------+  |
         |             |                     |
         v             v                     v
   +-----------+ +-----------+         +-----------+
   | payments  | |notifications|<------| hearings  |
   +-----------+ +-----------+         +-----------+
                       ^                     ^
                       |                     |
                       +--[hearing_reminders]+
```

---

## Table Definitions

### 1. `users`
Stores user authentication credentials, judicial roles, status, and metadata.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique auto-incrementing user ID.
- **`full_name`** (`VARCHAR(150)`, NOT NULL) — Official full name.
- **`email`** (`VARCHAR(120)`, UNIQUE, NOT NULL, INDEX) — Login email address.
- **`phone`** (`VARCHAR(30)`, NOT NULL) — Primary contact phone number.
- **`password_hash`** (`VARCHAR(256)`, NOT NULL) — Salted PBKDF2/scrypt password hash.
- **`role`** (`VARCHAR(32)`, NOT NULL) — One of: `government`, `registrar`, `judge`, `clerk`, `lawyer`, `litigant`, `police`.
- **`status`** (`VARCHAR(32)`, NOT NULL, DEFAULT `'active'`) — State: `active`, `pending_gov`, `pending_registrar`, `rejected`, `suspended`.
- **`court_id`** (`INTEGER`, FOREIGN KEY -> `courts.id`, NULLABLE) — Affiliated judicial court.
- **`id_proof_no`** (`VARCHAR(100)`, NULLABLE) — Bar council no., judicial employee ID, or last 4 digits of Aadhaar.
- **`designation`** (`VARCHAR(100)`, NULLABLE) — Official designation (e.g., Presiding Judge, Senior Advocate).
- **`avatar_color`** (`VARCHAR(20)`, DEFAULT `'#15284F'`) — Generated avatar color hex code.
- **`language_pref`** (`VARCHAR(10)`, DEFAULT `'en'`) — Communication preference (`en`, `te`, `hi`).
- **`notification_prefs`** (`TEXT`, NULLABLE) — JSON object holding channel opt-ins and quiet hours.
- **`created_at`** (`DATETIME`, DEFAULT `utcnow`) — Registration timestamp.
- **`approved_by`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Reviewing authority ID.
- **`approved_at`** (`DATETIME`, NULLABLE) — Timestamp of approval clearance.
- **`rejection_reason`** (`TEXT`, NULLABLE) — Official rejection remarks if application declined.

### 2. `courts`
Courthouse facilities, complexes, and judicial tiers.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique court ID.
- **`name`** (`VARCHAR(200)`, NOT NULL) — Official name of the court complex.
- **`type`** (`VARCHAR(50)`, NOT NULL) — Tier: `District`, `High`, `Supreme`, `Family`, `Magistrate`.
- **`city`** (`VARCHAR(100)`, NOT NULL) — City.
- **`state`** (`VARCHAR(100)`, NOT NULL) — State / Union Territory.
- **`address`** (`TEXT`, NULLABLE) — Physical courthouse address.
- **`code`** (`VARCHAR(20)`, UNIQUE, NOT NULL) — Registry jurisdiction code (e.g., `DLHC01`).

### 3. `courtrooms`
Individual physical courtrooms / benches within a court facility.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique courtroom ID.
- **`court_id`** (`INTEGER`, FOREIGN KEY -> `courts.id`, NOT NULL) — Parent court ID.
- **`name`** (`VARCHAR(100)`, NOT NULL) — Room name / designation (e.g. `Courtroom 1 (Chief Justice Bench)`).
- **`capacity`** (`INTEGER`, DEFAULT `50`) — Maximum gallery and bar seating capacity.

### 4. `cases`
Central docket master record for judicial petitions and disputes.
- **`id`** (`INTEGER`, PRIMARY KEY) — Auto-incrementing primary key.
- **`case_number`** (`VARCHAR(64)`, UNIQUE, NOT NULL, INDEX) — Formatted Case Number (e.g. `CIV/2026/00010`).
- **`title`** (`VARCHAR(255)`, NOT NULL) — Cause title (e.g. *Surya Enterprises vs. Global Tech Logistics*).
- **`case_type`** (`VARCHAR(64)`, NOT NULL) — `Civil`, `Criminal`, `Family`, `Property`, `Cheque Bounce`, `Bail`, `Writ`, `Consumer`.
- **`status`** (`VARCHAR(32)`, NOT NULL, DEFAULT `'Filed'`) — Lifecycle stage: `Filed`, `Scrutiny`, `Registered`, `Hearing`, `Reserved`, `Judgment`, `Disposed`, `Appealed`.
- **`priority`** (`VARCHAR(20)`, NOT NULL, DEFAULT `'Normal'`) — `Low`, `Normal`, `High`, `Urgent`.
- **`court_id`** (`INTEGER`, FOREIGN KEY -> `courts.id`, NOT NULL) — Jurisdiction court complex.
- **`judge_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Assigned presiding judicial bench.
- **`filed_by`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Advocate or citizen who initiated petition.
- **`filed_on`** (`DATE`, NOT NULL, DEFAULT `date.today`) — Date of formal e-filing.
- **`description`** (`TEXT`, NULLABLE) — Summary of claims, prayer, and facts.
- **`next_hearing_date`** (`DATE`, NULLABLE) — Current cause list date.

### 5. `case_parties`
Litigants, respondents, advocates, and witnesses tied to a case.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique party ID.
- **`case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NOT NULL) — Case foreign key.
- **`user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Associated user account.
- **`name`** (`VARCHAR(150)`, NOT NULL) — Legal name of individual or entity.
- **`party_type`** (`VARCHAR(50)`, NOT NULL) — `Petitioner`, `Respondent`, `Witness`, `Accused`, `Complainant`.
- **`advocate_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Retained advocate user ID.
- **`phone`** (`VARCHAR(30)`, NULLABLE) — Contact telephone number.
- **`email`** (`VARCHAR(120)`, NULLABLE) — Contact email.

### 6. `hearings`
Scheduled courtroom proceedings and bench listings.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique hearing ID.
- **`case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NOT NULL) — Case reference.
- **`courtroom_id`** (`INTEGER`, FOREIGN KEY -> `courtrooms.id`, NULLABLE) — Scheduled room.
- **`judge_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Presiding judge.
- **`scheduled_at`** (`DATETIME`, NOT NULL) — Date and time of listing.
- **`purpose`** (`VARCHAR(150)`, NOT NULL) — Hearing purpose (e.g. *Arguments on Admission*).
- **`status`** (`VARCHAR(32)`, NOT NULL, DEFAULT `'Scheduled'`) — `Scheduled`, `Completed`, `Adjourned`, `Cancelled`.
- **`adjournment_reason`** (`TEXT`, NULLABLE) — Justification for adjournment.
- **`attendance_status`** (`VARCHAR(32)`, DEFAULT `'Unconfirmed'`) — Attendance acknowledgment (`Confirmed`, `Unconfirmed`, `Excused`).
- **`notes`** (`TEXT`, NULLABLE) — Bench dictation notes.

### 7. `hearing_reminders`
Deduplication ledger for automated milestone reminders.
- **`id`** (`INTEGER`, PRIMARY KEY) — Auto-incrementing ID.
- **`hearing_id`** (`INTEGER`, FOREIGN KEY -> `hearings.id`, NOT NULL) — Hearing reference.
- **`user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Recipient user ID.
- **`reminder_type`** (`VARCHAR(32)`, NOT NULL) — Milestone: `7_days`, `1_day`, `2_hours`, `manual_2_hours`.
- **`channel`** (`VARCHAR(32)`, NOT NULL) — Dispatched channel (`SMS`, `WhatsApp`, `Email`, `In-App`).
- **`status`** (`VARCHAR(32)`, DEFAULT `'Delivered'`) — Delivery status.
- **`sent_at`** (`DATETIME`, DEFAULT `utcnow`) — Dispatch timestamp.
- **`UNIQUE CONSTRAINT`** (`hearing_id`, `user_id`, `reminder_type`) — Guarantees zero duplicate alerts.

### 8. `documents`
Uploaded petition records, affidavits, evidence exhibits, and certified orders.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique document ID.
- **`case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NOT NULL) — Case reference.
- **`uploaded_by`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Uploader user ID.
- **`filename`** (`VARCHAR(255)`, NOT NULL) — Original filename.
- **`stored_path`** (`VARCHAR(255)`, NOT NULL) — Secure local storage path relative to workspace.
- **`doc_type`** (`VARCHAR(64)`, NOT NULL) — `Petition`, `Affidavit`, `Evidence`, `Vakalatnama`, `Order`, `Notice`.
- **`version`** (`INTEGER`, DEFAULT `1`) — Document revision number.
- **`visibility`** (`VARCHAR(32)`, DEFAULT `'Public'`) — `Public`, `Confidential`, `Bench Only`.
- **`uploaded_at`** (`DATETIME`, DEFAULT `utcnow`) — Filing timestamp.

### 9. `orders`
Judicial orders, interim injunctions, decrees, and final judgments.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique order ID.
- **`case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NOT NULL) — Case reference.
- **`judge_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Presiding coram judge.
- **`title`** (`VARCHAR(255)`, NOT NULL) — Order title.
- **`content`** (`TEXT`, NOT NULL) — Legal decree and operative directions.
- **`order_type`** (`VARCHAR(50)`, NOT NULL) — `Interim`, `Final`, `Judgment`, `Notice`.
- **`signed_hash`** (`VARCHAR(128)`, NULLABLE) — Computed SHA-256 digital cryptographic signature hash.
- **`verification_code`** (`VARCHAR(32)`, NULLABLE, INDEX) — Public verification code (e.g. `NYAYA-0001-4921-2026`).
- **`issued_at`** (`DATETIME`, DEFAULT `utcnow`) — Pronouncement timestamp.

### 10. `payments`
Statutory court fees, e-filing stamps, and certified copy disbursements.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique payment ID.
- **`case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NULLABLE) — Associated case.
- **`user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Payer user ID.
- **`amount`** (`FLOAT`, NOT NULL) — Monetary amount in INR (₹).
- **`purpose`** (`VARCHAR(150)`, NOT NULL) — `E-Filing Fee`, `Court Fee`, `Certified Copy Fee`, `Bail Bond Deposit`.
- **`status`** (`VARCHAR(32)`, NOT NULL, DEFAULT `'Completed'`) — `Pending`, `Completed`, `Failed`.
- **`reference`** (`VARCHAR(64)`, UNIQUE, NOT NULL) — Treasury transaction reference (e.g. `TREASURY-2026-XXXXX`).
- **`paid_at`** (`DATETIME`, DEFAULT `utcnow`) — Payment settlement timestamp.

### 11. `notifications`
Multi-channel notification ledger for all citizen and judicial alerts.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique notification ID.
- **`user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Recipient user ID.
- **`channel`** (`VARCHAR(32)`, NOT NULL) — `SMS`, `WhatsApp`, `Email`, `In-App`.
- **`message`** (`TEXT`, NOT NULL) — Alert body content.
- **`status`** (`VARCHAR(32)`, DEFAULT `'Sent'`) — `Queued`, `Sent`, `Delivered`, `Failed`.
- **`related_case_id`** (`INTEGER`, FOREIGN KEY -> `cases.id`, NULLABLE) — Linked case docket.
- **`recipient_contact`** (`VARCHAR(120)`, NULLABLE) — Target phone number or email address.
- **`provider`** (`VARCHAR(50)`, DEFAULT `'DEMO_GATEWAY'`) — `TWILIO`, `DEMO_GATEWAY`.
- **`fallback_from`** (`VARCHAR(32)`, NULLABLE) — Prior channel if cascaded.
- **`reminder_type`** (`VARCHAR(32)`, NULLABLE) — Milestone type.
- **`hearing_id`** (`INTEGER`, FOREIGN KEY -> `hearings.id`, NULLABLE) — Linked hearing.
- **`scheduled_for`** (`DATETIME`, NULLABLE) — Scheduled dispatch time.
- **`sent_at`** (`DATETIME`, DEFAULT `utcnow`) — Dispatch timestamp.

### 12. `audit_logs`
Immutable forensic audit trail recording all user, judicial, and automated transactions.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique audit log ID.
- **`user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Actor user ID (or null for guest/system).
- **`action`** (`VARCHAR(64)`, NOT NULL, INDEX) — e.g. `LOGIN_SUCCESS`, `RATE_LIMIT_LOCKOUT`, `AI_CASE_SUMMARY`, `GOV_APPROVAL_APPROVE`.
- **`entity`** (`VARCHAR(64)`, NULLABLE) — Affected entity table name (`users`, `cases`, `orders`, `approval_requests`).
- **`entity_id`** (`INTEGER`, NULLABLE) — Primary key ID of affected record.
- **`ip`** (`VARCHAR(45)`, NULLABLE) — Client IP address.
- **`timestamp`** (`DATETIME`, DEFAULT `utcnow`) — Exact transaction timestamp.
- **`details`** (`TEXT`, NULLABLE) — Descriptive audit metadata.

### 13. `approval_requests`
Official clearance queue for Judicial and Registrar appointment verification.
- **`id`** (`INTEGER`, PRIMARY KEY) — Unique request ID.
- **`applicant_user_id`** (`INTEGER`, FOREIGN KEY -> `users.id`, NOT NULL) — Candidate user ID.
- **`requested_role`** (`VARCHAR(32)`, NOT NULL) — `judge`, `registrar`, `clerk`.
- **`court_name`** (`VARCHAR(200)`, NOT NULL) — Target court complex.
- **`details_json`** (`TEXT`, NULLABLE) — Serialized JSON with employee ID, designation, service years, ID proof path.
- **`status`** (`VARCHAR(32)`, DEFAULT `'Pending'`, INDEX) — `Pending`, `Approved`, `Rejected`.
- **`reviewed_by`** (`INTEGER`, FOREIGN KEY -> `users.id`, NULLABLE) — Government or Registrar reviewer.
- **`remarks`** (`TEXT`, NULLABLE) — Official vetting remarks or rejection reason.
- **`created_at`** (`DATETIME`, DEFAULT `utcnow`) — Submission timestamp.
- **`reviewed_at`** (`DATETIME`, NULLABLE) — Review clearance timestamp.

# NyayaDesk Manual QA & UAT Testing Checklist

This checklist provides an exhaustive, step-by-step manual test script for human quality assurance testers, court administrators, and stakeholders evaluating **NyayaDesk**.

---

## 1. Public & Citizen Pre-Login Verification

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 1.1 | Landing Page | Open browser and navigate to `http://127.0.0.1:5000/`. | Clean glassmorphic portal loads with hero counters (Courts, Judges, Active Cases, Clearance Rate). | [ ] |
| 1.2 | Cause List Board | Scroll down to the Live Daily Cause List. Toggle between courts using the dropdown. | Active hearings for today are displayed with case number, parties, courtroom, and bench name. | [ ] |
| 1.3 | Public Case Search | Enter a known case number (e.g. `CIV/2026/00001` or `State Bank`) into the search bar. Click **Search**. | Case detail card displays status, court, presiding judge, and upcoming hearing countdown. | [ ] |
| 1.4 | Global Search (Ctrl+K) | Press `Ctrl+K` (or `Cmd+K` on macOS) on any page. Type `Union` or `Sharma`. | Floating modal opens immediately, renders debounced instant search results, and enables keyboard navigation. | [ ] |
| 1.5 | Dark / Light Theme Toggle | Click the Theme Toggle button (Moon / Sun icon) in the top-right navigation bar. | Smooth transition between light and dark themes. Contrast remains crisp and legible across all text and cards. | [ ] |
| 1.6 | NyayaMitra Floating AI Assistant | Click the floating sparkles trigger in the bottom-right corner. | NyayaMitra assistant opens. Shows welcome message with legal disclaimer and mode pill (DEMO MODE or LIVE GEMINI). | [ ] |
| 1.7 | Chatbot Procedural Queries | Type `How do I file a bail application?` and press Enter. | Chatbot displays shimmer loading animation and responds with structured procedural steps and statutory references. | [ ] |
| 1.8 | Chatbot Multilingual Switching | Change language dropdown to **తెలుగు (Telugu)** or **हिन्दी (Hindi)**. Click a quick suggestion chip. | Suggestion chips and assistant responses render in the selected regional language. | [ ] |
| 1.9 | Order QR Verification | Navigate to `/orders/verify/NYA-ORD-00001` (or scan QR code from any generated order). | Cryptographic verification banner renders with Green Seal, SHA-256 hash, and issuing judge credentials. | [ ] |
| 1.10 | Mobile Viewport (375px) | Press F12 -> Toggle Device Toolbar -> Select iPhone SE (375px width). | Layout reflows gracefully: nav links collapse into drawer, cause list tables scroll horizontally without clipping. | [ ] |

---

## 2. Multi-Role Signup & Approval Workflows

| # | Role Tested | Steps to Execute | Expected Result | Pass / Fail |
|---|-------------|------------------|-----------------|-------------|
| 2.1 | Judge Signup | Navigate to `/auth/register`. Select role **Judge**. Fill valid details and upload ID proof. Submit. | Account created with status `pending_gov`. User is redirected to `/auth/pending-approval`. Direct login is blocked. | [ ] |
| 2.2 | Registrar Signup | Register with role **Registrar General**. Submit. | Account created with status `pending_gov`. Placed in government oversight queue. | [ ] |
| 2.3 | Clerk Signup | Register with role **Court Master / Clerk**. Submit. | Account created with status `pending_registrar`. Placed in registrar review queue. | [ ] |
| 2.4 | Litigant / Lawyer / Police | Register as **Citizen Litigant**, **Advocate**, or **Police Officer**. Submit. | Instant activation (`status: active`). Immediate redirection to respective workspace. | [ ] |
| 2.5 | Invalid Signup Validation | Attempt registration with empty email, weak password (<6 chars), or invalid phone format. | Client and server validation halts submission, highlighting exact invalid fields with helpful errors. | [ ] |
| 2.6 | Government Approval | Login as `gov@nyaya.in` (`Gov@12345`). Navigate to **Pending Approvals** tab. Click **Approve**. | Applicant status changes to `active`. Welcome SMS and email notifications are dispatched. | [ ] |
| 2.7 | Government Rejection | On a pending judicial credential, click **Reject**. Enter remarks: `Invalid Bar Council enrollment ID`. | Application marked `rejected` with remarks preserved. User notification sent explaining defect. | [ ] |
| 2.8 | Re-apply After Rejection | Login as the rejected user. Click **Update Credentials & Re-Apply**. Update ID and submit. | Status transitions from `rejected` back to `pending_gov` for renewed evaluation. | [ ] |
| 2.9 | Bulk Approval | As Government Administrator, click **Bulk Approve All Pending**. | All pending applications in queue are atomically approved in a single transaction. Counter updates to 0. | [ ] |
| 2.10 | Suspended Account Login | In database or admin desk, mark an account `suspended`. Attempt login. | Login blocked with HTTP 403 error message: `Account suspended. Contact administration.` | [ ] |

---

## 3. Registrar Scrutiny & Bench Allocation

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 3.1 | Registrar Scrutiny Queue | Login as `registrar@nyaya.in` (`Registrar@12345`). View **Scrutiny Queue**. | Displays all newly filed petitions in `Filed` / `Scrutiny` state with party names, case type, and filing date. | [ ] |
| 3.2 | Defect Notice Issuance | Open a petition with missing annexures. Click **Mark Defective**. Select defect categories and enter remarks. | Case status updates to `Defective`. Case number retains defect flag; petitioner/counsel notified via SMS/Email. | [ ] |
| 3.3 | Scrutiny Clearance | Review a complete petition. Click **Pass Scrutiny**. | Case status advances to `Registered` or `Scrutiny Passed`. Becomes available for judicial allocation. | [ ] |
| 3.4 | Judicial Bench Allocation | Select an unassigned case. Open **Allocate Bench** modal. Select Courtroom and Judge. Submit. | Case `judge_id` and `court_id` are saved. Case appears in the assigned judge's docket and cause list. | [ ] |
| 3.5 | Caseload Analytics | Review the Registrar Caseload Distribution chart. | Visual breakdown shows balanced distribution of pending and active matters across sitting judges. | [ ] |

---

## 4. Court Master / Clerk Desk & Hearing Scheduling

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 4.1 | Case Registration | Login as `clerk@nyaya.in` (`Clerk@12345`). Click **New Case Filing Wizard**. Fill metadata and parties. | Generates collision-free case number (`CASE/YYYY/XXXXX`). Case persists cleanly in registry. | [ ] |
| 4.2 | Hearing Scheduling | Click **Schedule Hearing**. Select case, courtroom, judge, date/time, and purpose (`Final Arguments`). | Hearing is scheduled. Confirmation toast displays and case calendar reflects the booking. | [ ] |
| 4.3 | Judge Conflict Detection | Attempt scheduling another hearing for the **same Judge** within 30 minutes of an existing listing. | Scheduling is blocked with collision warning: `Judge has another hearing scheduled within 30 minutes.` | [ ] |
| 4.4 | Courtroom Conflict Detection | Attempt scheduling another hearing in the **same Courtroom** at the exact same time slot. | Scheduling is blocked with collision warning: `Courtroom is already booked for this slot.` | [ ] |
| 4.5 | Weekend / Holiday Guard | Attempt scheduling a hearing on a **Sunday**. | Validation alert blocks submission: `Court is closed on Sundays / scheduled judicial holidays.` | [ ] |
| 4.6 | Document Upload & Versioning | Navigate to a case docket. Click **Upload Document**. Choose PDF, select type `Affidavit`. | File is securely stored in `data/uploads/`. Direct static URL browsing is blocked; download works via API. | [ ] |
| 4.7 | Document Re-Upload (v2) | Upload a modified document with the same title for the same case. | Document version increments from `v1` to `v2`. Prior version remains archived and accessible. | [ ] |
| 4.8 | Formal Notice Generation | Click **Generate Summons Notice**. Enter respondent details and hearing date. Click **Print / Export**. | Generates standardized court summons with official judicial header, legal seals, and print-ready CSS. | [ ] |

---

## 5. Judicial Bench Desk & Order Issuance

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 5.1 | Judge Daily Cause List | Login as `judge1@nyaya.in` (`Judge@12345`). View today's docket. | Lists scheduled matters in order of listing (Urgent, Regular, Motion). Shows parties and counsel names. | [ ] |
| 5.2 | AI Case Briefing | Click **Generate AI Summary** on an assigned case. | Structured legal summary renders (Case Facts, Issues for Determination, Procedural Milestones, Precedents). | [ ] |
| 5.3 | Delay Risk & Adjournment Predictor | View the case's **AI Delay Risk Indicator**. | Computes adjournment probability percentage based on past adjournment count, matter type, and complexity. | [ ] |
| 5.4 | Hearing Adjournment | Click **Adjourn Hearing**. Select reason (`Counsel Unwell`) and specify next date. | Hearing status updates to `Adjourned`. Case `next_hearing_date` updates. Notifications queued for all parties. | [ ] |
| 5.5 | Interim Order Issuance | Click **Issue Order**. Select type `Interim`. Enter order operative text. Click **Sign & Seal**. | Order is saved with unique verification code (`NYA-ORD-XXXX`) and immutable SHA-256 signature hash. | [ ] |
| 5.6 | Final Judgment & Case Disposal | Issue an order with type `Judgment`. Select outcome `Dismissed` or `Allowed`. | Case status transitions to `Disposed`. Case is removed from active pending lists and added to disposal stats. | [ ] |
| 5.7 | AI Assisted Order Drafting | In the order editor, click **Draft with AI**. Provide brief dictation notes. | AI drafts standard formal judicial order format with title, appearance lines, reasoning, and operative decree. | [ ] |

---

## 6. Advocate / Bar Desk & E-Filing

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 6.1 | Advocate Case Portfolio | Login as `lawyer@nyaya.in` (`Lawyer@12345`). View active briefs. | Displays all matters where the advocate is enrolled counsel. Shows next dates and outstanding compliance. | [ ] |
| 6.2 | Electronic Petition Filing | Click **E-Filing Portal**. Fill petition details, select court, attach memorandum of writ/plaint. | Petition enters registry scrutiny queue with status `Filed`. Filing receipt issued with timestamp. | [ ] |
| 6.3 | Document Access & Download | Open a client case. Click **Download Pleadings / Orders**. | Authorized files download cleanly. Attempting to download files of an unrelated case returns HTTP 403. | [ ] |
| 6.4 | Hearing Calendar | View the Advocate Personal Cause List. | Aggregates hearings across multiple courtrooms into a single chronological itinerary. | [ ] |

---

## 7. Citizen Litigant Portal & Payments

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 7.1 | Citizen Case Tracking | Login as `litigant@nyaya.in` (`Litigant@12345`). | Displays citizen's case card with visual progress stepper (`Filed -> Scrutiny -> Hearing -> Judgment`). | [ ] |
| 7.2 | Electronic Fee Payment | Click **Pay Court Fees**. Enter amount `Rs. 500` for application fee. Confirm payment. | Generates official transaction reference (`TXN-NYA-XXXX`). Payment status marks `Success`. | [ ] |
| 7.3 | Receipt Download | Click **Download Payment Receipt**. | Produces official e-receipt with GRN reference, case number, payer name, and barcode. | [ ] |
| 7.4 | Notification Preferences | Navigate to **Settings -> Notifications**. Change language to Telugu (`te`). Set quiet hours (22:00 - 07:00). | Settings persist. Subsequent reminders are rendered in Telugu and queued outside quiet hours. | [ ] |

---

## 8. Police Portal & Criminal Docket

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 8.1 | Police Criminal Docket | Login as `police@nyaya.in` (`Police@12345`). View Station Dockets. | Lists active criminal matters, remand listings, and pending charge-sheet submissions. | [ ] |
| 8.2 | Charge-Sheet Submission | Click **File Charge-Sheet / Final Report**. Enter FIR No, Accused Name, and IPC/BNS sections. | Charge-sheet is registered in the court system and linked to police station records. | [ ] |
| 8.3 | Witness Summons Tracking | Check status of summons issued for police witnesses. | Displays whether summons was served, delivered, or unserved with delivery timestamps. | [ ] |

---

## 9. Multichannel Reminders & Attendance Acknowledgment

| # | Feature / Area | Steps to Execute | Expected Result | Pass / Fail |
|---|----------------|------------------|-----------------|-------------|
| 9.1 | Automated 3-Tier Scan | Trigger scheduler reminder dispatch (`POST /api/reminders/trigger`). | System scans active hearings at 7-day, 1-day, and 2-hour milestones and creates notification records. | [ ] |
| 9.2 | Channel Fallback Sequence | Disconnect or simulate SMS gateway failure. | System falls back automatically to WhatsApp -> Email -> In-App notification bell. | [ ] |
| 9.3 | Inbound SMS Reply Simulation | Send simulated reply: `POST /api/reminders/simulate-reply` with `message: CONFIRM`. | Hearing attendance updates from `Unconfirmed` to `Confirmed`. Acknowledgment timestamp logged. | [ ] |
| 9.4 | Notification Bell Counter | Click the bell icon in the top navigation bar. | Unread count badge updates. Dropdown displays recent alerts with clickable links to relevant dockets. | [ ] |
| 9.5 | Mark All as Read | In notification dropdown, click **Mark All as Read**. | Unread count badge clears to 0. All items transition to read state. | [ ] |

---

## 10. Security & Edge Case Resilience

| # | Security Test | Action | Expected Defense | Pass / Fail |
|---|---------------|--------|------------------|-------------|
| 10.1 | CSRF Token Enforcement | Submit a POST request (e.g. login or schedule) without `X-CSRFToken` header. | Request rejected with HTTP 403 (`CSRF token missing or invalid`). | [ ] |
| 10.2 | IDOR Case Isolation | As Litigant A, try accessing `/dashboards/cases/<Litigant_B_Case_ID>`. | Access denied with HTTP 403 Forbidden. User cannot view other citizens' cases. | [ ] |
| 10.3 | XSS Script Escaping | Enter `<script>alert('xss')</script>` into a case title, description, or chat message. | Script tags are sanitized and rendered as harmless text (`&lt;script&gt;`) everywhere. | [ ] |
| 10.4 | SQL Injection Immunity | Enter `' OR 1=1 --` into case search, cause list filter, or login fields. | System treats payload as literal search string. Zero syntax errors or data leaks. | [ ] |
| 10.5 | Malicious File Upload | Attempt uploading `.exe`, `.pdf.exe`, or files with `../../` path traversal names. | Upload is immediately rejected with HTTP 400. File is not written to storage. | [ ] |
| 10.6 | Brute-Force Rate Limiting | Enter 5 consecutive incorrect passwords for any account. | 5th failed attempt locks out user for 60 seconds with HTTP 429 Too Many Requests. | [ ] |
| 10.7 | Security Headers | Inspect network response headers in browser dev tools. | `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` present. | [ ] |
| 10.8 | Demo Reset Utility | Click **Reset Demo Database** in Demo Guide or call `POST /api/admin/reset-demo`. | Database resets to pristine seeded state with 3 courts, 14 users, 25 cases, and zero orphan records. | [ ] |

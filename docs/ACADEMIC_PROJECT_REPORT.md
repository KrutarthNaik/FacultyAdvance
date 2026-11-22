# FacultyAdvance
## Automated System for Career Advancement of Higher-Education Faculty

**Academic project report**

| Submission detail | Information |
|---|---|
| Student name | [Enter student name] |
| Roll / registration number | [Enter roll number] |
| Programme / department | [Enter programme and department] |
| Institution | [Enter institution name] |
| Project guide | [Enter guide name and designation] |
| Academic year | [Enter academic year] |
| Report date | November 2026 |

> Before submission, replace the bracketed fields, apply the institution's required formatting, and attach any required approval, declaration, certificate, or signed pages. This report describes the supplied FacultyAdvance MVP; it does not claim institutional deployment or adoption.

## Abstract

FacultyAdvance is a web-based prototype for organizing faculty achievements and supporting an academic appraisal workflow. It combines a React single-page application with a Django REST Framework API. SQLite is retained for local development; production configuration requires PostgreSQL with verified TLS. Faculty can maintain teaching, research, service, and professional-development activity records, attach evidence, discover publication metadata through Crossref, preview a score calculated under an approved period policy, and submit an appraisal. Department reviewers can verify activities and record appraisal decisions.

The application uses role-aware API access, JSON Web Token (JWT) authentication, email verification, password reset, request throttling, configurable versioned policies, append-only audit events, private evidence download routes, stored notifications, and downloadable PDF appraisal reports. Users can export their own profile and records. Production HTTPS controls and optional S3-compatible evidence storage are configurable, but no production service has been provisioned.

The delivered system is an academic demonstration and not a certified promotion decision tool. Demo scoring values are illustrative. Institutional single sign-on, PostgreSQL cutover, storage/email provider setup, policy approval, privacy/retention sign-off, and production deployment remain institution/operator tasks.

**Keywords:** faculty appraisal, higher education, Django REST Framework, React, evidence management, workflow automation, Crossref.

## 1. Introduction

Faculty appraisal processes commonly collect evidence from multiple sources and require coordination between faculty members, reviewers, and institutional administrators. Manual or disconnected records can make it difficult to maintain a consistent activity history, verify supporting evidence, communicate review outcomes, and prepare reports.

FacultyAdvance addresses this problem with a role-based web application. It gives each faculty member a digital record for academic contributions and provides a workflow for submitting, reviewing, and reporting appraisal information. It is designed as a starter project that can be configured and extended for a specific institution.

## 2. Problem statement

The project problem is to provide a centralized prototype that can:

1. Capture structured faculty achievements and supporting documents.
2. Organize appraisal submissions by an institution-defined period.
3. Allow reviewers to verify evidence and communicate decisions.
4. Calculate an explainable, configurable score from verified activities.
5. Provide research-publication metadata discovery without relying on unsupported website scraping.
6. Make submission status and appraisal reports accessible to authorized users.

## 3. Aim and objectives

### Aim

To design and implement a full-stack faculty appraisal prototype that consolidates academic records and supports a traceable submission and review process.

### Objectives

- Provide registration, login, and role-aware access for faculty, HOD/reviewers, and administrators.
- Maintain activity records across research, teaching, projects, professional development, service, awards, patents, and other contributions.
- Accept supporting evidence files subject to file type and size checks.
- Integrate Crossref search and DOI import as a metadata-assistance feature.
- Calculate a score from verified records and configurable category criteria.
- Support appraisal submission, review decisions, status notifications, and PDF output.
- Provide administrator-managed appraisal periods and scoring criteria.
- Enable users to update personal contact details while keeping institutional attributes read-only through the self-service profile API.
- Verify email addresses and allow time-limited password recovery with rate limits.
- Require a complete approved policy for score calculation and bind each submission to its policy version.
- Record important changes in an append-only audit log.
- Use authenticated evidence downloads and support an optional private S3-compatible object store.
- Export a user's own records and provide an explicit, dry-run-first notification retention command.

## 4. Scope and assumptions

### Included in the prototype

- Single-institution demonstration with department-scoped HOD/reviewer access.
- Faculty self-registration with the Faculty role.
- JWT-protected REST API and a browser-based React interface.
- Local SQLite database and local media storage for development; production requires PostgreSQL and can enable private S3-compatible storage.
- Activity evidence records and reviewer verification.
- Appraisal periods, versioned policy drafts/approvals, score previews, and submission history.
- Crossref metadata discovery and pending publication imports.
- In-app notifications, role-specific dashboards, and PDF appraisal reports.
- Django Admin for controlled administration of users, periods, and criteria.

### Assumptions

- The institution provisions HOD and administrator accounts using a controlled process.
- Administrators configure formally approved appraisal criteria before operational use.
- Faculty and reviewers confirm the accuracy and ownership of externally sourced publication metadata.
- A score is informational; an authorized human review and institutional rules govern any actual decision.

## 5. System users and functional modules

| User / module | Main responsibilities |
|---|---|
| Faculty workspace | Register and sign in; maintain profile contact details; add activities and evidence; search Crossref; inspect scores; submit appraisals; review notifications and submission history. |
| HOD / reviewer workspace | View department-scoped activities and submissions; verify or reject evidence; request revisions; record review decisions and comments; download appraisal reports. |
| University administration | Provision accounts and roles; manage appraisal periods and policy versions; view institution-wide appraisal information; download reports. |
| Activity and evidence | Store categorized academic activity, dates, publication metadata, reviewer status, notes, and evidence references. |
| Appraisal and scoring | Apply explicit per-category points and optional caps from the approved immutable policy version for the selected period. |
| Research discovery | Query Crossref and import DOI metadata as a pending activity requiring confirmation. |
| Notification center | Deliver appraisal-submission and activity-verification messages; list user-owned messages; mark messages read individually or in bulk. |
| Profile | Edit name, email, and phone; show employee code, department, and designation as institution-managed information. |
| Identity and account recovery | Verify account email and reset passwords using single-use time-limited tokens. |
| Audit and privacy | Verify audit-chain integrity, download authenticated evidence, and export the signed-in user's data. |
| Data retention | Dry-run-first cleanup for read notifications only, enabled after an approved retention period is configured. |
| Reporting | Generate a PDF with faculty details, period, score, included activities, statement, and review history. |

## 6. Requirements

### Functional requirements

1. The system shall authenticate users and distinguish Faculty, HOD/Reviewer, and University Administrator roles.
2. A faculty user shall be able to create and view their activity records.
3. An activity may have one or more evidence documents; supported types are PDF, PNG, JPG, and JPEG, with a 10 MB per-file limit.
4. A reviewer shall only verify activities and review submissions within the permitted department scope; an administrator may access institution-wide records.
5. Only verified activities within an appraisal period shall contribute to the indicative score.
6. A faculty member shall submit one appraisal per period, with revision resubmission supported.
7. Submission and activity-verification events shall notify the relevant parties.
8. A user shall only read and update their own notifications.
9. Self-service profile updates shall not alter role, employee code, department, or designation.
10. Authorized users shall be able to retrieve an appraisal PDF.
11. Password login shall require verified email; password reset shall use a single-use token and passwords shall meet the configured strength policy.
12. Appraisal submission shall require an approved policy and store the policy version used.
13. Evidence download shall require authentication and owner/department authorization.
14. Significant account, activity, evidence, submission, review, policy, and export events shall be auditable.

### Non-functional requirements

- **Usability:** Provide clear feedback for loading, successful actions, and failed API requests.
- **Maintainability:** Separate the frontend, API, data models, permissions, and scoring service.
- **Security:** Authenticate protected API requests, rate limit sensitive endpoints, and apply role and department checks to reviewer operations.
- **Portability:** Support local development on Windows with Python and Node.js.
- **Transparency:** Show score components, use approved versioned rules, and disclose that demo values are illustrative.
- **Extensibility:** Keep criteria configurable and organize REST resources around domain concepts.

## 7. Architecture and technology

### Technology stack

| Layer | Technology |
|---|---|
| User interface | React 18, Vite, React Router, Axios, Lucide icons, CSS |
| Application/API | Python, Django, Django REST Framework |
| Authentication | Simple JWT access and refresh tokens; time-limited email verification/password reset |
| Persistence | SQLite for local development; PostgreSQL required in production |
| Evidence storage | Local development media or optional private S3-compatible object storage |
| Publication metadata | Crossref public REST API |
| Document output | ReportLab PDF generation |
| Administration | Django Admin |

### Logical architecture

```text
Faculty / Reviewer / Administrator
                 |
                 v
       React browser application
       (routes, forms, dashboards)
                 |
       HTTPS enforced in production / HTTP locally
                 |
                 v
     Django REST Framework API
  authentication | permissions | services
      |            |             |
      v            v             v
SQLite/PostgreSQL  Authenticated evidence  Crossref API
                   API -> private S3*       (metadata search)
      |
      +---- Versioned policy engine and append-only audit log
      +---- ReportLab appraisal PDF
```

In the local setup, evidence files are stored under Django's media directory and the database is SQLite. Production requires PostgreSQL over verified TLS and HTTPS. If configured, S3-compatible evidence storage must use a bucket with public access blocked. Neither cloud infrastructure nor an institutional identity provider is provisioned by this project.

## 8. Data model

| Entity | Purpose and principal relationships |
|---|---|
| User | Extends Django's user model with role, employee code, department, designation, and phone. |
| AppraisalPeriod | Defines a named date range and active-period flag. |
| Activity | Belongs to a faculty user; stores category, title, dates, publication or organizer metadata, verification status, and reviewer note. |
| EvidenceDocument | Belongs to an activity and stores an uploaded file reference and upload metadata. |
| AppraisalCriterion | Stores per-category points, description, and enabled state. |
| AppraisalPolicy | Stores the period-specific policy version, category rules/caps, approval state, approver, and approval time. Approved versions are immutable. |
| AppraisalSubmission | Belongs to a faculty member and appraisal period; stores status, score, statement, policy reference, and timestamps. A faculty-period pair is unique. |
| Review | Records a review decision, reviewer, comments, and timestamp for a submission. |
| Notification | Belongs to one user and stores a message, read state, and creation time. |
| AuditEvent | Append-only actor/action/object/metadata event with a previous-entry hash and entry hash. |

## 9. Main workflows

### 9.1 Faculty activity and evidence

1. The faculty member authenticates and creates an activity with a category and activity date.
2. Optional publication details and a supporting document are submitted.
3. The activity is stored with `PENDING` verification status.
4. A department reviewer or administrator reviews the activity and changes its verification state.
5. The faculty member receives an in-app notification containing the result and any reviewer note.
6. The appraisal score is recalculated from verified activities associated with the relevant period.

### 9.2 Appraisal submission and review

1. Faculty checks the current score breakdown and active appraisal period.
2. Faculty submits a statement and the system records the current calculated score.
3. The faculty member receives a confirmation notification; the department HODs and administrator accounts receive a submission notification.
4. A reviewer may mark the submission under review, request revision, approve, or reject it, with comments.
5. The faculty member receives the updated status; revision requests can be resubmitted.
6. An authorized user downloads a PDF report containing the appraisal record and review history.

### 9.3 Notification management

- Notifications are scoped to the authenticated user.
- Individual items can be marked as read.
- A bulk action marks all of the current user's unread notifications as read.
- API failures are surfaced in the interface rather than silently ignored.

### 9.4 Profile management

- Users may update their name, email, and phone number.
- The self-service API treats role, employee code, department, and designation as read-only.
- HOD department scoping therefore cannot be changed through the profile endpoint.

## 10. Appraisal scoring method

For each activity category \(c\), the scoring service counts verified activities for the selected faculty member and appraisal period, then applies the explicitly configured point value and optional maximum for that category:

\[
\text{Category score}_c =
\begin{cases}
\text{verified count}_c \times \text{points per item}_c, & \text{if no cap is defined} \\
\min(\text{verified count}_c \times \text{points per item}_c,\ \text{max points}_c), & \text{otherwise}
\end{cases}
\]

\[
\text{Total score} = \sum_{c \in \text{categories}} \text{Category score}_c
\]

An administrator drafts a policy version for an appraisal period. The policy must define every activity category, with non-negative `points_per_item` and an optional non-negative `max_points`. Approval records an administrator and timestamp; approved versions cannot be edited or deleted. The score endpoint selects the latest approved version for the active period, and submission is rejected if no approved policy exists. Each submission stores the policy reference used at submission, and its PDF identifies that version.

The demo seed creates illustrative values solely for local demonstration. The model does not yet include authorship weighting, evidence-specific scoring, effective-date sub-periods, multi-approver policy signing, appeals, or an institution-validated rules engine. These require the institution's approved policy and testing before any official use.

## 11. API and frontend integration

Protected API endpoints use a bearer JWT in the `Authorization` header. The frontend Axios client attaches the access token and attempts to refresh it after an unauthorized response.

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/register/` | Register a Faculty account |
| `POST /api/auth/token/` | Obtain JWT access and refresh tokens |
| `POST /api/auth/verify-email/` | Verify an email using a time-limited signed token |
| `POST /api/auth/password-reset/` and `/confirm/` | Request and apply a single-use password reset |
| `GET/PATCH /api/auth/me/` | Read a profile or update editable personal details |
| `GET /api/auth/me/export/` | Export the authenticated user's profile and records |
| `GET /api/dashboard/` | Return role-specific dashboard metrics |
| `GET/POST /api/activities/` | List or create activities |
| `POST /api/activities/{id}/evidence/` | Upload an activity evidence file |
| `GET /api/evidence/{id}/download/` | Download evidence after owner/department authorization |
| `POST /api/activities/{id}/verify/` | Verify, reject, or reset activity verification |
| `GET /api/research/crossref/?q=...` | Search Crossref metadata |
| `POST /api/research/crossref/import/` | Import a DOI as a pending publication |
| `GET /api/score/` | Return active-period score and category breakdown |
| `GET /api/periods/` | List appraisal periods |
| `GET /api/submissions/` | List submissions visible to the authenticated user |
| `POST /api/submissions/submit/` | Submit an appraisal for the active period |
| `POST /api/submissions/{id}/review/` | Record a review decision |
| `GET /api/submissions/{id}/pdf/` | Download an appraisal PDF |
| `GET /api/notifications/` | List current-user notifications |
| `POST /api/notifications/{id}/mark_read/` | Mark one owned notification as read |
| `POST /api/notifications/mark_all_read/` | Mark all current-user notifications as read |
| `GET/POST/PATCH /api/policies/` | Administrator manages policy drafts |
| `POST /api/policies/{id}/approve/` | Approve and lock a complete period policy version |
| `GET /api/audit/integrity/` | Administrator verifies the audit hash chain |

The frontend maps user roles to routes and calls the REST API for activity, score, submission, review, notification, and profile operations. Crossref is an external dependency and may be unavailable; users can enter publication records manually.

## 12. Validation and testing

The repository includes Django tests for:

- Notifying faculty after an activity verification decision, including the reviewer note.
- Notifying department HODs and administrators after an appraisal is submitted.
- Marking only the authenticated user's notifications as read.
- Preventing profile updates from changing a user's role or department while allowing contact changes.
- Password strength, email verification, password reset and one-time token behavior.
- PostgreSQL/production configuration validation, HTTPS/HSTS controls and migration verification.
- Policy approval, policy immutability, category caps and absence of scoring without an approved policy.
- Audit hash-chain validation and database-trigger rejection of audit mutation.
- Dry-run-first notification retention and authenticated personal-data export.

Run the backend checks and tests from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test core
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Build the frontend from the `frontend` directory:

```powershell
npm run build
```

**Execution record (9 November 2026):** The checks below were run in the supplied development workspace. A successful frontend build or Django unit test run does not replace end-to-end testing against a running application.

| Check | Result | Evidence / notes |
|---|---|---|
| Django system check | Pass | `manage.py check` reported no issues. |
| Migration consistency | Pass | `manage.py makemigrations --check --dry-run` reported no model changes. |
| Core API tests | Pass | `manage.py test core` ran 29 tests; all passed. |
| Vite production build | Pass | `npm run build` completed successfully. |
| Python dependency consistency | Pass | `pip check` reported no broken requirements. |
| Manual role-based workflow | Not run | Run with faculty, HOD, and administrator accounts before demonstrating or deploying. |

## 13. Local setup

The repository README contains full Windows setup steps. The core sequence is:

1. Create and activate a Python virtual environment in `backend`.
2. Install `backend/requirements.txt`, configure `backend/.env`, run migrations, and optionally seed demo data.
3. Start Django on `http://127.0.0.1:8000`.
4. Install frontend packages in `frontend` and start Vite on `http://localhost:5173`.
5. Use the documented demo credentials only for local demonstration, and change them before any shared deployment.

See the project [README](../README.md) for environment variables, API details, demo accounts, and complete commands.

## 14. Privacy, security, and operational considerations

- Production configuration enables HTTPS redirects, secure cookies, HSTS, verified PostgreSQL TLS, and explicit production hosts/origins. Configure TLS termination/proxy trust and certificates in the hosting environment.
- Password validation, email verification, single-use password recovery, and rate limits protect credential workflows. Public registration defaults off in production; administrator provisioning is available.
- Evidence downloads require authentication and owner/department authorization. Optional S3-compatible storage must use a private bucket with public access blocked; local filesystem storage is development-only.
- Extension/size checks do not replace malware scanning or content validation. No scanning service is integrated.
- Important account, policy, activity, evidence, submission, review, and export events are written to an append-only table with database update/delete triggers and a hash chain. Database owners can still bypass application-level controls; use independent monitoring and protected backups.
- Authenticated users can export their own profile and appraisal records. A notification retention command deletes only read notifications, is disabled by default, records a dry-run, and requires explicit `--apply`.
- See [PRIVACY_RETENTION_REVIEW.md](./PRIVACY_RETENTION_REVIEW.md) for the data inventory, retention guardrails, and institutional checklist. No legal jurisdiction or retention schedule has been assumed.
- Review department membership and every object-level access path before deployment.
- Institutional SSO is not connected. An approved provider, issuer/metadata, client registration, claim validation, account-linking and provisioning/role-mapping rules are required before implementation.
- PostgreSQL, email, object storage, malware scanning, TLS termination, secrets management, monitoring, backups and recovery are configuration/operations work; no production resource is provisioned.
- Do not use the demo account credentials or illustrative score values for real institutional decisions.

## 15. Limitations and future work

### Current limitations

- The project is an MVP for a single institution and uses a simple department string rather than an organizational hierarchy.
- Local evidence storage is not production-grade private object storage; no cloud bucket, KMS key, or malware scanner is provisioned.
- Institutional single sign-on and a production account-provisioning integration are not connected; provision accounts through controlled Django Admin access for the prototype.
- PostgreSQL is configured as the required production backend but has not been installed or rehearsed against a live PostgreSQL server.
- Email is console-based for local development; production mail provider and sending domain require configuration.
- Privacy review, jurisdiction, legal holds, and retention periods for activities, evidence, submissions and audit records require institutional approval. Only read-notification cleanup is implemented.
- Audit database triggers are not protection against a privileged database owner, offline edits, trigger removal, or replaced backups.
- The system has no official identity integration with Google Scholar; Crossref metadata is not proof of authorship.
- Activity records do not yet have a complete version history or a submission-time lock.
- Automated tests cover key backend workflows but do not establish full access-control, browser, performance, external-provider, or security assurance.

### Recommended future work

1. Obtain the institution's approved appraisal policy, enter category points/caps into a versioned draft, approve it through a governed process, and validate results with domain stakeholders.
2. Select and configure the institutional identity provider and provision/link existing accounts only under approved claim and role mappings.
3. Rehearse PostgreSQL migration, private object storage, backup/restore and TLS configuration in an isolated environment before cutover.
4. Approve privacy jurisdiction, notices, legal holds, data-subject workflows, retention periods, and deletion/anonymization procedures.
5. Add malware scanning, frontend end-to-end/accessibility tests, PostgreSQL integration tests, and operational monitoring.
6. Integrate ORCID through its supported authorization flow and provide duplicate/ownership reconciliation for scholarly records.
7. Conduct security, privacy, load, and usability reviews before any real-data pilot.

## 16. Conclusion

FacultyAdvance demonstrates how a full-stack application can centralize faculty contribution records and connect evidence submission, reviewer decisions, policy-based scoring, notifications, privacy export, and reporting. The React frontend communicates with a role-aware Django REST API. Approved, period-specific score policies and audit records improve traceability while preserving the distinction between an indicative calculation and a formal promotion decision.

Email verification, password reset, rate limiting, production HTTPS settings, private-download controls, policy approval, audit triggers, and targeted automated tests provide a stronger prototype baseline. The project remains a learning and demonstration foundation: actual PostgreSQL/SSO/storage deployment, institutional scoring approval, privacy/retention sign-off, and operations review are still required.

## References

1. Django Software Foundation, *Django documentation*. https://docs.djangoproject.com/
2. Encode OSS Ltd., *Django REST framework documentation*. https://www.django-rest-framework.org/
3. React, *React documentation*. https://react.dev/
4. Crossref, *REST API documentation*. https://www.crossref.org/documentation/retrieve-metadata/rest-api/
5. ReportLab, *ReportLab PDF Library User Guide*. https://www.reportlab.com/docs/reportlab-userguide.pdf
6. RFC 7519, *JSON Web Token (JWT)*. https://www.rfc-editor.org/rfc/rfc7519

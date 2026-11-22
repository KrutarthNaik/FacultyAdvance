# FacultyAdvance — Faculty Appraisal & Career Advancement Platform

A full-stack starter application for the problem statement **“Automated System for Career Advancements of the Faculties of Higher Education.”** It provides a faculty portal, HOD/reviewer workflow, university administration APIs, research publication discovery, configurable appraisal criteria, and PDF reports.

> **Project status:** This is a functional MVP/starter repository intended for local development, learning, demonstrations, and further customization. It is not a certified university appraisal system. Configure the institution's officially approved appraisal policy before using scores for real promotion or career decisions.

## Technology stack

- **Frontend:** React 18, Vite, React Router, Axios, Lucide icons, responsive CSS
- **Backend:** Python, Django, Django REST Framework, Simple JWT
- **Database:** SQLite for local development; PostgreSQL is required when `DEBUG=False` and selected with `DATABASE_URL`
- **Research metadata:** Crossref public REST API and ORCID public profile lookup; authenticated ORCID OAuth and Google Scholar scraping are not included
- **PDF reports:** ReportLab
- **Evidence uploads:** Authenticated API download; optional private S3-compatible storage through Django Storages

## Features included

### Faculty
- Faculty registration and JWT login
- Optional Google Workspace sign-in for existing accounts; account roles and departments remain admin-managed
- Email verification and one-time password reset links
- Strong password validation and throttled authentication/email actions
- Profile details: employee code, department and designation
- Update personal name, email and phone from the profile page; institutional role and department fields remain read-only
- Create and view research, teaching, project, FDP, seminar, patent, award and service activities
- Upload supporting PDF/JPG/PNG evidence (10 MB maximum per file)
- Crossref publication search and DOI-based import
- ORCID public researcher search, profile lookup and account identifier linking; works are not automatically imported from ORCID
- Optional Google Scholar profile URL saved for manual reconciliation; no scraping or work import
- Appraisal score preview based on verified activities
- Submit appraisal for the active appraisal period
- View submission status and download PDF report

### HOD / reviewer
- Department-scoped dashboard and submission list
- Search and sort submissions
- View faculty activity records
- Verify or reject evidence/activities
- Receive in-app notifications when faculty activity evidence is reviewed
- Request appraisal revisions, approve, reject or mark under review
- Add review comments
- Download appraisal PDFs

### University administrator
- Access across departments
- Submission sorting by faculty name, employee code, date, score and status
- Configure appraisal criteria through Django Admin/API
- Provision accounts and roles through Django Admin; public registration is disabled by default in production
- Draft and approve period-specific scoring policies; approved policy versions are immutable and stored with appraisal submissions
- Inspect append-only audit events and verify the audit hash chain
- Manage appraisal periods and faculty accounts through Django Admin
- Download individual appraisal PDF reports
- Receive in-app notifications when an appraisal is submitted by faculty

### Automation included
- Crossref discovery by title, author or keyword
- DOI metadata import as a *pending verification* activity
- DOI-based duplicate checks for publication imports
- ORCID public API researcher lookup and profile linking (not OAuth authorization)
- Appraisal points calculated only under an approved period policy with optional category caps; no policy means no score and no submission
- In-app notifications for activity verification and appraisal submission/review events, with individual and bulk read actions
- Production settings require PostgreSQL TLS, HTTPS origins, secure cookies, a production secret and real email delivery
- Optional S3-compatible private evidence storage; otherwise local filesystem storage is for development only
- Authenticated personal-data export and a dry-run-first notification retention command
- Vercel deployment configuration and a two-project hosting guide

## Repository structure

```text
FacultyAdvance/
├── README.md
├── .gitignore
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/
│   │   ├── settings.py
│   │   ├── database.py
│   │   ├── deployment.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── core/
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── services.py
│       ├── account_services.py
│       ├── validators.py
│       ├── permissions.py
│       ├── urls.py
│       ├── admin.py
│       ├── tests.py
│       ├── migrations/
│       └── management/commands/
│           ├── seed_demo.py
│           └── apply_data_retention.py
├── docs/
│   ├── ACADEMIC_PROJECT_REPORT.md
│   ├── PRIVACY_RETENTION_REVIEW.md
│   ├── postgresql-migration.md
│   └── vercel-deployment.md
└── frontend/
    ├── package.json
    ├── vercel.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── api.js
        ├── main.jsx
        ├── App.jsx
        └── styles.css
```

## Requirements

- Python 3.10 or newer (Python 3.11/3.12 recommended)
- Node.js 18 or newer and npm
- Internet connection for Crossref publication search

## Run locally on Windows

Open **two terminals** in the project folder.

### 1. Start the backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py makemigrations core
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Backend URLs:
- API root: `http://127.0.0.1:8000/api/`
- Django admin: `http://127.0.0.1:8000/django-admin/`

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again.

### 2. Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### PostgreSQL migration and production configuration

Local development continues to use `backend/db.sqlite3` and console email.
For production, `DEBUG=False` requires PostgreSQL, a 50-character random
`SECRET_KEY`, verified PostgreSQL TLS (`sslmode=verify-full`), HTTPS frontend
and CSRF origins, allowed hosts, production email delivery and secure cookies.
Set the environment out-of-band; never put live credentials in `.env` committed
to source control. The migration rehearsal and rollback steps are in
[docs/postgresql-migration.md](docs/postgresql-migration.md).

Production evidence storage can be configured with `USE_S3_STORAGE=True` and
the `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, and provider credentials
or workload identity. Configure the bucket with public access blocked and
approved encryption, backups, and access logging. Evidence is delivered through
an authenticated API endpoint; local media is only for development.

Public registration defaults off in production. Provision faculty, HOD, and
administrator accounts through Django Admin using an authorized provisioning
process. Registration in local debug mode requires email verification. The
included demo accounts are strictly for local demonstration.

### Demo logins

| Role | Username | Password |
|---|---|---|
| Faculty | `faculty` | `Faculty@12345` |
| HOD / Reviewer | `hod` | `Hod@12345` |
| University administrator | `universityadmin` | `Admin@12345` |

The `seed_demo` command creates sample accounts, an active appraisal period for 2026–27, illustrative score criteria and a small amount of sample activity. Change these passwords immediately outside a local demo.

## API reference

All endpoints below are relative to `/api/`. Except registration and token endpoints, requests require:

```http
Authorization: Bearer <access_token>
```

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `auth/register/` | Register a faculty account when public registration is enabled |
| POST | `auth/token/` | Obtain access and refresh JWT tokens |
| POST | `auth/token/refresh/` | Refresh an access token |
| GET | `auth/google/start/` | Begin Google Workspace OpenID Connect sign-in (when configured) |
| GET | `auth/google/callback/` | Complete Google sign-in and issue a short-lived one-time SPA ticket |
| POST | `auth/google/complete/` | Exchange a one-time SSO ticket for JWTs |
| POST | `auth/verify-email/` | Verify a time-limited email token |
| POST | `auth/resend-verification/` | Resend an email verification link |
| POST | `auth/password-reset/` | Request a one-time password-reset link |
| POST | `auth/password-reset/confirm/` | Set a new password with reset token |
| GET/PATCH | `auth/me/` | View/update the signed-in user's profile |
| GET | `auth/me/export/` | Export the authenticated user's profile and records |
| GET | `dashboard/` | Role-specific dashboard metrics |
| GET/POST | `activities/` | List or create activity records |
| GET/PATCH/DELETE | `activities/{id}/` | View activity; owner faculty or administrator may update/delete |
| POST | `activities/{id}/evidence/` | Upload evidence (`multipart/form-data`, field `file`) |
| GET | `evidence/{id}/download/` | Download evidence after owner/department authorization |
| POST | `activities/{id}/verify/` | Reviewer verifies/rejects activity evidence |
| GET | `research/crossref/?q=...` | Search Crossref metadata |
| POST | `research/crossref/import/` | Import a selected DOI as a pending publication |
| GET | `research/orcid/search/?q=...` | Search public ORCID researcher records |
| GET | `research/orcid/profile/?orcid_id=...` | Look up public profile name for an ORCID iD |
| GET | `score/` | Get active-period score breakdown |
| GET | `periods/` | List appraisal periods |
| GET | `submissions/` | List submissions visible to the user |
| POST | `submissions/submit/` | Submit faculty appraisal for active period |
| POST | `submissions/{id}/review/` | HOD/admin records a review decision |
| GET | `submissions/{id}/pdf/` | Download appraisal PDF |
| GET | `notifications/` | List current user's notifications |
| POST | `notifications/{id}/mark_read/` | Mark one of the current user's notifications as read |
| POST | `notifications/mark_all_read/` | Mark all current-user notifications as read |
| GET | `criteria/` | Read legacy illustrative criteria (not used by the policy scoring engine) |
| GET/POST/PATCH | `policies/` | Administrator manages policy drafts |
| POST | `policies/{id}/approve/` | Approve and lock a complete period policy version |
| GET | `audit/integrity/` | Administrator checks the append-only audit hash chain |

Self-service profile updates support personal name, email, phone and an optional Google Scholar profile URL. Role, employee code, department and designation are read-only and must be managed through an authorized administrative process.

### Example: faculty registration

```json
{
  "username": "faculty.jane",
  "email": "jane@example.edu",
  "first_name": "Jane",
  "last_name": "Doe",
  "password": "Use-A-Unique-Strong-Password!",
  "employee_code": "FAC102",
  "department": "Computer Engineering",
  "designation": "Assistant Professor"
}
```

Public registration always creates the `FACULTY` role and requires email verification. Passwords must be at least 12 characters and use at least three character classes. In production, public registration is off; provision accounts and assign roles through Django Admin. Google Workspace SSO is opt-in and supports existing active accounts with matching verified Workspace email addresses; it does not create accounts or map roles/departments.

### Example: verify an activity

```json
{
  "verification_status": "VERIFIED",
  "reviewer_note": "DOI and supporting document checked."
}
```

### Example: review a submission

```json
{
  "decision": "REVISION",
  "comments": "Please upload the completion certificate for the project."
}
```

Allowed decisions: `UNDER_REVIEW`, `REVISION`, `APPROVED`, `REJECTED`.

## Appraisal scoring logic

- An administrator creates a policy draft for an appraisal period using the app's **Appraisal policies** page or the `policies/` API. Each category must specify `points_per_item`; `max_points` is optional.
- A policy must explicitly include every activity category and be approved by an administrator before it affects scoring.
- Approved policies are immutable. Create a new policy version for future changes; submissions retain the policy version used when submitted.
- Only activities with `verification_status = VERIFIED` are counted.
- The score preview and submitted score use activities within the active appraisal period and approved policy version.
- The demo seed creates illustrative values for local demonstration, **not official UGC/university/CAS norms**. Replace them with the institution's formally approved rules and add co-author weighting, evidence requirements, exclusions, and effective dates as applicable.
- An appraisal score is an aid to evaluation. A human review and the institution's formal rules must govern promotion decisions.

## Research publication integration

The current implementation calls the public Crossref REST API and ORCID public API:
- Search: `GET /api/research/crossref/?q=machine+learning+education`
- Import: `POST /api/research/crossref/import/` with `{ "doi": "10.xxxx/example" }`

An imported publication is created with `source = CROSSREF` and `verification_status = PENDING`. Faculty/reviewers should confirm authorship, title, venue, publication date and attach evidence. Crossref is not a complete index of all scholarly work.

Faculty can search public ORCID records and link a selected ORCID iD to their profile. The app does not use ORCID OAuth, access private ORCID data, or automatically import a researcher's works; confirm records and add them through Crossref or the activity form.

The problem statement mentions Google Scholar. This starter does **not** scrape Google Scholar pages and does not claim to have an official Google Scholar API integration. Faculty can save a public profile URL in their profile and use it as a manual reconciliation reference; publications still need to be added through Crossref or the activity form and supported with evidence.

## Production readiness and decisions still required

The application now includes PostgreSQL production configuration, HTTPS/security
settings, password validation and throttling, email verification and reset,
administrator-managed account provisioning, immutable application audit events,
approved versioned appraisal policies, authenticated evidence downloads, a
self-service data export, and a dry-run-first notification retention command.
These controls have backend tests, but are not a substitute for deployment and
institutional acceptance testing.

Before using real faculty data:

1. Provision PostgreSQL, email delivery, private object storage, TLS termination,
   secrets management, monitoring, backups and recovery; rehearse migration and
   restore using disposable infrastructure.
2. Select and integrate the institution's identity provider only after approving
   its protocol, issuer, claims, account linking and role/department mapping.
3. Replace illustrative policy values with formally approved appraisal rules,
   effective dates, evidence requirements and governance.
4. Approve privacy jurisdiction, notices, legal holds, record-class retention,
   deletion/anonymization, and data-subject handling.
5. Provision and enable malware scanning; add live PostgreSQL/provider integration,
   frontend end-to-end and accessibility, load and security testing.
6. Review object-level access for the institution's organization structure.

The local demo database contains three verified demo accounts. A fresh database
does not automatically verify existing users: account owners must complete
email verification, or an authorized administrator must verify them through the
approved provisioning process. Do not treat demo verification as proof of
ownership of a real institutional email address.

## Tests and academic report

Run the backend system check and API tests from `backend`:

```powershell
$env:DEBUG = "True"
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test core
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Build the frontend from `frontend`:

```powershell
npm run build
```

See [docs/ACADEMIC_PROJECT_REPORT.md](docs/ACADEMIC_PROJECT_REPORT.md) for the academic report, system design, functional modules, scoring method, validation plan, limitations and future work.

See [docs/PRIVACY_RETENTION_REVIEW.md](docs/PRIVACY_RETENTION_REVIEW.md) for the data inventory, implemented retention guardrails, and institution-specific privacy review checklist. Notification cleanup is a dry run unless explicitly invoked with `--apply`; set an institution-approved `NOTIFICATION_RETENTION_DAYS` first:

```powershell
python manage.py apply_data_retention
python manage.py apply_data_retention --apply
```

See [docs/vercel-deployment.md](docs/vercel-deployment.md) for deploying the
frontend and Django API as separate Vercel projects, including required managed
PostgreSQL, Redis, email, and private object-storage settings.

Vercel deployment has not been run from this workspace. The deployment guide
prepares the Vite SPA rewrites, Django production defaults, shared rate-limit
cache configuration, persistent storage requirements, and serverless upload
limit; it does not provision external services or migrate production records.

## Notes / known MVP limitations

- This starter is intended for a single institution and uses a simple department field rather than a full organizational hierarchy.
- Faculty can update their own activity records; a production workflow should lock submitted records or maintain version history.
- The evidence upload is stored locally in `backend/media/`; use private storage in production.
- The reviewer submission list is pageable, and PDF activity tables flow across pages. Institution-specific report layouts and very large report workloads still need operational sizing and acceptance.
- In-app notifications have read/mark-all-read actions. Configured event email alerts cover activity review and appraisal submission; appraisal decision emails are not sent.
- Google Workspace OpenID Connect is implemented for existing accounts. Configure the client ID/secret, Workspace domain, backend callback URI and SPA callback URI before enabling it. Other identity providers are not integrated.
- Evidence in local development is not private object storage; use the authenticated download endpoint and configure a private bucket for production.
- Audit events are protected from application-level updates/deletions and chained; database owners/administrators remain privileged and must be separated, audited, and backed up operationally.
- No Google Scholar scraping or official Google Scholar API integration is included. The saved profile URL is only a manual reconciliation reference.

## License

Use and adapt this starter for your academic project. Add a license file if you publish or distribute it publicly.

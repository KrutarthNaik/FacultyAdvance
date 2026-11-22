# FacultyAdvance privacy and retention review

**Status:** Technical controls and a review checklist are provided. This is not a legal opinion, privacy notice, data-protection impact assessment, or institutional approval. The institution must identify the applicable jurisdiction and appoint the responsible reviewer before using real faculty data.

## Data inventory

| Data | Current purpose | Application access | Current technical lifecycle |
|---|---|---|---|
| Account name, email, phone, role, employee code, department, designation | Authentication, identity, authorization, appraisal reports | Account owner; authorized administrators; role-scoped reviewers where relevant | No automatic account deletion. Existing accounts are retained until an approved process addresses records and audit references. |
| Password hash and JWTs | Authentication | Password hash is not serialized through the API; JWT is held by the frontend client | Django password hashers protect passwords; access and refresh token lifetimes are environment-sensitive. |
| Activities, research metadata, dates, reviewer notes | Appraisal evidence and reporting | Faculty owner; department-scoped HOD; administrators | No automatic activity deletion. Retain according to the institution's approved appraisal and records schedule. |
| Evidence documents | Substantiation of activity claims | Owner, department-scoped reviewer, administrator via authenticated download | Local media in development; optional S3-compatible storage in production. No automatic deletion. Optional ClamAV scanning is available but disabled unless configured and provisioned by the operator. |
| Appraisal submissions, score, faculty statement, policy reference | Submission, review, report generation | Faculty owner; department-scoped HOD; administrators | No automatic deletion. Submitted score stores the approved policy version used. |
| Reviews and comments | Review decision history | Faculty owner and authorized reviewers/administrators for the submission | No automatic deletion. Review retention and legal-hold policy are institution decisions. |
| Notifications | Workflow communication | Notification owner | Optional command deletes only read notifications older than a configured period, after an explicit `--apply`. Default period is disabled (`0`). |
| Audit events | Trace security- and appraisal-relevant changes and exports | Administrators can inspect; application users cannot modify audit records | Append-only database triggers and a SHA-256 hash chain. No automatic purge is implemented. |
| Operational logs, database backups, object-store logs | Troubleshooting, recovery, security monitoring | Infrastructure operators under the deployment's controls | Not managed by the application; retention, encryption, access and deletion must be configured by the institution/operator. |

## Implemented safeguards

- API permission checks scope faculty records to their owner and HOD records to their department.
- Registration is Faculty-only, email verification is required before password login, and production public registration is disabled by default.
- Password reset uses Django's single-use reset token mechanism; reset and verification actions are rate-throttled.
- Password validation requires at least 12 characters and three character classes, in addition to Django similarity/common/numeric checks.
- Profile export is authenticated and includes only the signed-in user's records. Export access itself is audited.
- Evidence downloads use an authenticated endpoint that checks faculty ownership or reviewer department scope. Files are not served directly from media URLs by the API.
- Evidence uploads can be scanned with ClamAV (`MALWARE_SCANNER=clamd` or `clamscan`). Scanning is disabled by default; production operators must provision and monitor the scanner and keep definitions current.
- Optional S3 storage is not enabled by default. When enabled, the application avoids public ACLs and requires an administrator-configured bucket, region, credentials/workload identity and HTTPS endpoint in production.
- Appraisal policy drafts require explicit category rules; score calculations use only an approved policy. Approved versions are immutable and linked to submissions.
- Audited events include authentication/account provisioning, policy decisions, activity changes, evidence access, appraisal events, and personal-data exports. Database triggers reject audit-row update/delete operations.
- Production mode requires a non-development secret, PostgreSQL with verified TLS, HTTPS origins, secure cookies/HSTS, explicit allowed hosts, and a production email backend.

## Retention and deletion controls

### Notifications

`NOTIFICATION_RETENTION_DAYS` defaults to `0`, which disables cleanup. Set it only after an institution approves a retention schedule. From `backend`, the command first reports eligible records without deleting:

```powershell
python manage.py apply_data_retention
```

Only read notifications are eligible. To apply the deletion, an operator must explicitly run:

```powershell
python manage.py apply_data_retention --apply
```

The command records a non-user-attributed audit event for each purged notification. Test the command in a non-production environment and include the approved period, change approver, execution account, and results in the institution's protected change record.

### Activities, evidence, submissions, reviews, accounts, and audit events

No automatic purge is configured for these records. This is intentional: appraisal records may be subject to institutional records schedules, employment obligations, appeals, litigation holds, or privacy rights. Do not infer their retention duration from the notification setting. Before implementing automated purging or account erasure, the institution must decide:

1. Retention period by record class, event, and appraisal status.
2. How legal holds, appeals, investigations, and open submissions suspend deletion.
3. Whether personal identifiers can be pseudonymized while retaining required audit evidence.
4. How evidence objects, database rows, backups, replicas, search indexes, and logs are deleted consistently.
5. Who authorizes a deletion and how to record its scope and completion without retaining unnecessary personal data.
6. How long audit events and security logs are retained, and whether a separately controlled archive is required.

Audit events have a protective foreign-key relationship to actors; this prevents deleting accounts that are referenced by audit records. An approved erasure/anonymization workflow is therefore required before individual account deletion is offered. Database superusers can bypass application controls and must be separated from application operators, least-privileged, monitored, and covered by backup/restore controls.

## Institution-specific privacy review checklist

- [ ] Name the data controller/owner, privacy contact, system owner, and operational processors.
- [ ] Identify the applicable jurisdiction, employment and higher-education rules, records obligations, and required notice/consent basis.
- [ ] Confirm purpose limitation and minimize fields collected for registration and every activity category.
- [ ] Approve the role/department access matrix and review logs for cross-department exposure.
- [ ] Approve a retention schedule, legal-hold process, data export/rectification/deletion response, and backup expiry treatment.
- [ ] Review email, database, object storage, hosting, support, analytics, backup, and identity-provider subprocessors and data residency.
- [ ] Approve TLS termination, secrets and key management, at-rest encryption, storage bucket public-access blocks, malware scanning, and incident response.
- [ ] Define audit-event access, retention, integrity verification, off-host protected archival, and alerting. A local hash chain is not a substitute for independent log custody.
- [ ] Test data-subject export and approved correction/anonymization/deletion procedures on non-production data.
- [ ] Record the privacy review date, approvers, unresolved risks, and re-review triggers in a protected institutional record.

## Known gaps

- Google Workspace OpenID Connect is implemented for existing accounts, with verified-domain checks and one-time login tickets. It remains disabled until credentials, the approved Workspace domain, and callback URLs are configured. Other SSO providers and institutional account-linking approvals remain outstanding.
- No email delivery vendor or sending domain is selected. Production SMTP/API credentials must be provisioned out-of-band and verified.
- No S3-compatible provider, private bucket policy, KMS key, or production malware scanner has been provisioned. Malware scanning is optional and disabled by default.
- The database audit trigger prevents ordinary row update/delete, but a database owner can alter triggers, truncate tables, replace backups, or modify the database offline. Use least privilege, independent audit export/monitoring, and protected backups.
- Privacy, retention, and deletion policy are not approved by an institution or legal reviewer. The code does not claim legal compliance.
- No production HTTPS endpoint, reverse proxy, certificate, hosting environment, monitoring, or backup schedule is provisioned.

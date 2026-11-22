# PostgreSQL configuration and SQLite migration rehearsal

The application keeps SQLite and Django's console email backend for local
development. Email is written to the developer's console rather than sent
externally. Production requires an explicitly configured non-console
`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, and a non-development `SECRET_KEY` of
at least 50 characters.
SMTP host, port, credentials, and
transport security can be supplied through `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `EMAIL_USE_SSL`.
Use an approved secret mechanism for credentials; do not put them in committed
files.

The application selects PostgreSQL only when `DATABASE_URL` is explicitly
supplied. The URL must use the `postgres` or `postgresql` scheme and contain a
host and database name. Supported URL options are `sslmode`, `sslrootcert`,
`sslcert`, `sslkey`, `connect_timeout`, and `application_name`. Production
(`DEBUG=False`) requires `sslmode=verify-full`; configure an approved
CA/certificate path where needed. Use an institution-approved secret mechanism
to provide database credentials; do not put real URLs in source control,
fixtures, logs, screenshots, or shell history.
`DATABASE_CONN_MAX_AGE` defaults to `0` and can be set to a non-negative integer
after connection-pooling behavior is reviewed.

The migration procedure below is for a controlled rehearsal with an isolated,
disposable PostgreSQL database. Do not point it at production until the
institution has approved the database, secret handling, backup/restore
procedure, privacy controls, and deployment change window.

## Rehearsal

1. Stop application writes. Keep the original `backend/db.sqlite3` and media
   directory intact. Make a consistent SQLite backup using SQLite's online
   backup API and copy media to a restricted backup location. Treat both the
   backup and any fixture as sensitive personal data.

   From `backend`, one way to create a database backup is:

   ```powershell
   python -c "import sqlite3; source=sqlite3.connect('db.sqlite3'); target=sqlite3.connect('db-rehearsal-backup.sqlite3'); source.backup(target); target.close(); source.close()"
   ```

   Do not commit the backup, fixture, or copied evidence files. Confirm the
   SQLite and media backups can be restored before proceeding.

2. Before switching databases, export a Django fixture from the backed-up
   SQLite database. Preserve primary keys and use natural foreign keys for
   generated content-type and permission relationships:

   ```powershell
   $env:DATABASE_URL = ""
   python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission --output migration-fixture.json
   ```

   `dumpdata` includes user data and password hashes. Keep the fixture in a
   restricted location and remove it according to the institution's approved
   secure-handling procedure after validation. For large production datasets,
   use a separately reviewed database transfer method rather than relying on
   JSON fixtures.

3. Configure `DATABASE_URL` out-of-band to an empty, disposable PostgreSQL
   database and install the pinned project requirements, including the
   PostgreSQL driver. Run and review the target migration plan, then migrate:

   ```powershell
   python manage.py migrate --plan
   python manage.py migrate
   ```

   Do not supply a production URL for this rehearsal. Keep URL values out of
   command output and captured logs.

4. Load the fixture into the target. Fixture loading preserves model primary
   keys and foreign-key references. If loading fails or any counts differ,
   discard only the disposable target, retain the source backup, correct the
   rehearsal, and retry:

   ```powershell
   python manage.py loaddata migration-fixture.json
   ```

5. Set `SQLITE_MIGRATION_SOURCE` out-of-band to the existing SQLite source
   database file. The setting is read-only; it does not create, migrate, or
   modify the source file. Run the verifier:

   ```powershell
   python manage.py verify_database_migration --source-alias migration_source --target-alias default
   ```

   The command compares row counts, primary keys, and foreign-key relationships
   for managed application models (including many-to-many join tables), and
   runs database constraint checks on both aliases. It excludes generated
   `ContentType`/`Permission` rows and ephemeral session/admin-log rows. It
   reports counts and model labels only, not record contents. It is a read-only
   verification step, not a transfer command; a successful comparison does not
   replace application-level review or media-file validation.

6. Run the Django tests and application smoke checks against the disposable
   target, and compare expected media-file counts/checksums using a separately
   approved procedure. Record the source/target row-count results, migration
   revision, backup location, reviewer, and rollback decision in the protected
   change record, not in this repository.

## Cutover and rollback

Only cut over after an approved rehearsal, restore test, application test,
media validation, and operational sign-off. Preserve the SQLite source and its
backup unchanged during the observation period. To roll back, stop writes,
restore the prior application configuration/release and the verified SQLite
backup, then resume service only after the rollback is validated. Any writes
accepted by PostgreSQL after cutover need an institution-approved reconciliation
plan; switching the URL alone cannot merge those writes into SQLite.

The repository has no PostgreSQL service or credentials configured, so no
live PostgreSQL migration has been run here. `core/0002_user_email_verified_appraisalpolicy_and_more`
adds email-verification state, period/versioned appraisal policies, a submission
policy reference, and append-only audit events with SQLite/PostgreSQL mutation
triggers. Existing accounts are not automatically marked as email-verified.
Before the new login check is enabled for an upgraded database, plan a
controlled verification process for existing users (resend verified-address
links or manually verify through an authorized provisioning workflow). Do not
silently assume an existing email address is current or controlled by its
account holder.

The migration has been exercised against the local SQLite database. PostgreSQL
schema migration, trigger behavior, TLS, and the SQLite-to-PostgreSQL transfer
still require a disposable PostgreSQL rehearsal.

## Decisions required before production

The institution/operator must approve the PostgreSQL host/version, TLS mode and
certificate policy, credentials/secret delivery, connection lifetime/pooling,
backup encryption and retention, restore objectives, migration-window and
write-freeze process, fixture/data-transfer handling, and deployment/rollback
owners. No cloud provider, database resource, or production identifier is
selected by this change.

This implementation provides email verification and reset flows, development
and production security settings, optional S3-compatible storage, an
administrator policy workflow, application provisioning through Django Admin,
and append-only application audit events. It does not select or connect an
institutional identity protocol/provider, issuer, claim mapping, account-linking
policy, provisioning approver, or department/role mapping. Public registration
must not grant privileged roles.

The institution must still select an email vendor/sender, object-storage
provider or malware scanner, approved scoring rules/version authority, privacy
jurisdiction, retention periods/legal-hold policy, hosting platform/domain/
proxy, secrets manager, monitoring product, and backup/recovery objectives.
These require institutional and operator approval before production.

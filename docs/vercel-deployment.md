# Deploy FacultyAdvance on Vercel

FacultyAdvance can use Vercel for both the Vite frontend and Django API by
creating **two Vercel projects from the same Git repository**. This repository
does not contain service credentials or an institutional domain; those must be
created and configured in the provider dashboards.

Vercel runs Django as a Python Function. Its filesystem is ephemeral, so the
production configuration below requires managed PostgreSQL, Redis and private
S3-compatible storage. The Django app must not use local SQLite or local media
for deployed data. The backend pins Python 3.12 and uses Vercel's native Django
WSGI detection; the Dockerfile is for container hosting and is not used by the
Vercel Function runtime.

## 1. Provision persistent services

Create:

- A managed PostgreSQL database with TLS and a connection string that uses
  `sslmode=verify-full`. Prefer the database provider's serverless/pooler URL
  for function deployments. The project validates this TLS mode.
- A managed Redis-compatible cache. Django REST Framework throttling uses this
  shared cache; use its TLS `rediss://` connection URL. Per-process memory
  caches are not reliable across serverless instances.
- A private S3-compatible bucket with public access blocked, encryption, and
  lifecycle/backups approved by the institution.
- An approved production email service and sender domain.

Never put credentials in the repository or the frontend `VITE_*` variables.
Add backend secrets through the Vercel backend project's Environment Variables.

## 2. Create the Django backend project

Import the repository into Vercel and set **Root Directory** to `backend`.
Vercel detects `manage.py` and the configured WSGI application. The backend's
`requirements.txt` contains the Python dependencies. Add the environment
variables below to the appropriate Vercel environments:

| Variable | Value |
|---|---|
| `DEBUG` | `False` |
| `VERCEL` | Set automatically by Vercel; do not set manually |
| `SECRET_KEY` | At least 50 random characters, stored as a secret |
| `DATABASE_URL` | Managed PostgreSQL URL with `sslmode=verify-full` |
| `DATABASE_CONN_MAX_AGE` | `0` unless the selected managed pooler recommends otherwise |
| `REDIS_URL` | TLS Redis URL using `rediss://` |
| `ALLOWED_HOSTS` | Comma-separated backend custom domain and deployed Vercel host(s) |
| `FRONTEND_ORIGINS` | Comma-separated exact HTTPS frontend production/preview origins |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated exact HTTPS frontend origins |
| `TRUST_PROXY_SSL_HEADER` | `True` |
| `USE_S3_STORAGE` | `True` |
| `AWS_STORAGE_BUCKET_NAME` | Private bucket name |
| `AWS_S3_REGION_NAME` | Bucket region |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Storage credentials, or the provider's supported identity mechanism |
| `EMAIL_BACKEND` | Approved Django email backend |
| `DEFAULT_FROM_EMAIL` | Verified sender address |
| `EMAIL_HOST` / `EMAIL_PORT` | SMTP host and port when using Django's SMTP backend |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP credentials when required by the provider |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | Enable the provider's required transport security (never both) |
| `PASSWORD_RESET_FRONTEND_URL` | `https://<frontend-domain>/reset-password` |
| `EMAIL_VERIFICATION_FRONTEND_URL` | `https://<frontend-domain>/verify-email` |
| `PUBLIC_REGISTRATION_ENABLED` | `False` unless institution explicitly approves it |

Configure the backend's `ALLOWED_HOSTS` with the exact deployed API host. The
runtime also adds Vercel's `VERCEL_URL` for the current deployment. For previews,
either explicitly add each preview host or use the narrowest approved host
pattern compatible with the institution's policy. The backend refuses to start
on Vercel with `DEBUG=True`, without `TRUST_PROXY_SSL_HEADER=True`, or without
a TLS Redis URL. `DEBUG=False` also requires production PostgreSQL, an explicit
email backend/sender and private S3 storage, so configure these before the
first deployment build. Select a Function region close to the PostgreSQL
provider to reduce database latency.

Vercel Functions default to 4.5 MB request and response bodies. A 20 MiB request
limit is available in public beta for Python functions with Fluid Compute and
Performance 4 GB memory enabled. This app keeps the safer default: evidence
uploads are limited to 4 MiB with multipart overhead margin. Keep
`EVIDENCE_UPLOAD_MAX_BYTES` at or below `4194304`; larger uploads require the
beta configuration or a direct-to-object-storage upload flow.

## 3. Migrate schema and provision users

Do not run schema migrations from each serverless request. Before sending
traffic to a deployment, execute migrations once against the configured
database using a trusted operator environment with the backend's production
environment variables:

```powershell
python manage.py migrate --noinput
python manage.py check --deploy
```

Run these commands once from a trusted operator machine or CI job configured
with the exact backend environment variables and the production database URL.
Do not run them during every Function invocation. Use the same `requirements`
environment and Python 3.12 runtime as the deployed backend.

The current deployment policy deliberately leaves HSTS subdomain inclusion and
browser preload disabled because it cannot assert that every subdomain is
HTTPS-only. Django may report `security.W005` and `security.W021`; review them
against the institution's domain policy rather than enabling preload blindly.

Use the approved, rehearsed SQLite-to-PostgreSQL process if transferring real
records; `migrate` only creates the schema and does not copy local data.
Provision an administrator securely, then create approved policy versions.
Do not run `seed_demo` in production.

## 4. Create the Vite frontend project

Create a second Vercel project using the same repository with **Root Directory**
set to `frontend`. Use the default Vite install/build settings (`npm ci` and
`npm run build`). The included `vercel.json` rewrites SPA routes such as
`/criteria` to `index.html`.

Set these frontend **build-time** variables:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://<backend-domain>/api/` |
| `VITE_EVIDENCE_UPLOAD_MAX_MB` | `4` |

### Optional Google Workspace sign-in

Google SSO supports existing accounts only. In Google Cloud, create a Web
OAuth client and register `https://<backend-domain>/api/auth/google/callback/`
as an authorized redirect URI. Set `GOOGLE_SSO_CLIENT_ID`,
`GOOGLE_SSO_CLIENT_SECRET`, `GOOGLE_SSO_WORKSPACE_DOMAIN`,
`GOOGLE_SSO_REDIRECT_URI`, and `GOOGLE_SSO_FRONTEND_CALLBACK` on the backend.
The frontend callback must be `https://<frontend-domain>/sso/callback` and the
backend redirect URI must exactly match the Google Cloud registration. Keep the
client secret in the backend environment only. SSO matches a verified Google
Workspace email to exactly one active existing account; it does not provision
accounts or assign institutional roles/departments.

The Vite configuration fails the Vercel build if `VITE_API_URL` is missing.
After setting it, redeploy the frontend because Vite embeds this value into the
static build.

## 5. Verify deployment

After deploy:

1. Visit `https://<backend-domain>/api/health/`; expect `200` and `{"status":"ok"}`.
2. Check the frontend login screen and API sign-in request in browser developer
   tools; verify there are no CORS, CSRF, or mixed-content errors.
3. Test email verification and reset delivery, account provisioning, policy
   creation/approval, a small evidence upload/download, and a PDF report.
4. Confirm uploaded objects remain available after a new deployment, and verify
   that bucket objects are not publicly readable.
5. Test the production domain with `python manage.py check --deploy`.
6. Configure database backup/restore, Redis availability, storage lifecycle,
   monitoring, and an incident/rollback procedure.

Vercel can host the frontend and Django Function, but this guide does not
provision external services, transfer production data, select institutional
SSO/scoring/retention policies, or constitute production acceptance testing.

## References

- [Vercel Django deployment](https://vercel.com/docs/frameworks/full-stack/django)
- [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite)
- [Vercel Function limits](https://vercel.com/docs/functions/limitations)

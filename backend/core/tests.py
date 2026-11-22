from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.core.cache import cache
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import SimpleTestCase, TestCase, override_settings
from django.core import mail
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.core.management.base import CommandError
from rest_framework.test import APITestCase

from config.database import build_database_config
from config.deployment import build_deployment_security, validate_vercel_runtime
from config.email import CONSOLE_EMAIL_BACKEND, build_email_config
from config.security import DEVELOPMENT_SECRET_KEY, validate_secret_key
from .models import Activity, AppraisalPeriod, Notification, AppraisalPolicy, AuditEvent, GoogleSSOLoginTicket
from .services import calculate_appraisal, record_audit_event, verify_audit_chain, scan_uploaded_file
from .validators import StrongPasswordValidator


User = get_user_model()


class DatabaseConfigurationTests(SimpleTestCase):
    def test_local_configuration_keeps_sqlite_as_the_default(self):
        database_config = build_database_config(
            database_url="",
            sqlite_path="local.sqlite3",
            debug=True,
        )

        self.assertEqual(database_config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(str(database_config["NAME"]), "local.sqlite3")

    def test_production_configuration_requires_postgresql(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DATABASE_URL must configure"):
            build_database_config(
                database_url="",
                sqlite_path="local.sqlite3",
                debug=False,
            )

    def test_postgresql_url_maps_connection_and_safe_options(self):
        database_config = build_database_config(
            database_url=(
                "postgresql://faculty-app@db.example.invalid:5432/faculty"
                "?sslmode=verify-full&connect_timeout=5"
            ),
            sqlite_path="local.sqlite3",
            debug=True,
            conn_max_age=30,
        )

        self.assertEqual(database_config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database_config["NAME"], "faculty")
        self.assertEqual(database_config["USER"], "faculty-app")
        self.assertEqual(database_config["HOST"], "db.example.invalid")
        self.assertEqual(database_config["PORT"], "5432")
        self.assertEqual(database_config["CONN_MAX_AGE"], 30)
        self.assertEqual(
            database_config["OPTIONS"],
            {"sslmode": "verify-full", "connect_timeout": 5},
        )

    def test_production_postgresql_requires_verified_tls(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "sslmode=verify-full"):
            build_database_config(
                database_url="postgresql://faculty-app@db.example.invalid/faculty",
                sqlite_path="local.sqlite3",
                debug=False,
            )

        database_config = build_database_config(
            database_url=(
                "postgresql://faculty-app@db.example.invalid/faculty"
                "?sslmode=verify-full"
            ),
            sqlite_path="local.sqlite3",
            debug=False,
        )
        self.assertEqual(database_config["OPTIONS"]["sslmode"], "verify-full")

    def test_invalid_urls_fail_without_echoing_url_contents(self):
        marker = "sensitive-marker"
        with self.assertRaises(ImproperlyConfigured) as error:
            build_database_config(
                database_url=f"sqlite:///{marker}",
                sqlite_path="local.sqlite3",
                debug=True,
            )

        self.assertNotIn(marker, str(error.exception))

    def test_negative_connection_lifetime_is_rejected(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured, "DATABASE_CONN_MAX_AGE cannot be negative"
        ):
            build_database_config(
                database_url="",
                sqlite_path="local.sqlite3",
                debug=True,
                conn_max_age=-1,
            )


class EmailConfigurationTests(SimpleTestCase):
    def test_local_email_defaults_to_console_delivery(self):
        email_config = build_email_config(debug=True)

        self.assertEqual(email_config["EMAIL_BACKEND"], CONSOLE_EMAIL_BACKEND)
        self.assertEqual(email_config["DEFAULT_FROM_EMAIL"], "webmaster@localhost")

    def test_production_requires_explicit_non_console_delivery(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_BACKEND"):
            build_email_config(debug=False)
        with self.assertRaisesMessage(ImproperlyConfigured, "console email backend"):
            build_email_config(
                debug=False,
                backend=CONSOLE_EMAIL_BACKEND,
                default_from_email="faculty@example.invalid",
            )

    def test_production_email_requires_sender_and_exclusive_transport_security(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DEFAULT_FROM_EMAIL"):
            build_email_config(debug=False, backend="custom.EmailBackend")
        with self.assertRaisesMessage(ImproperlyConfigured, "cannot both be enabled"):
            build_email_config(debug=True, use_tls=True, use_ssl=True)

    def test_smtp_backend_requires_a_host_and_complete_credentials(self):
        smtp = "django.core.mail.backends.smtp.EmailBackend"
        with self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_HOST is required"):
            build_email_config(debug=False, backend=smtp, default_from_email="noreply@example.edu")
        with self.assertRaisesMessage(ImproperlyConfigured, "must be set together"):
            build_email_config(
                debug=False,
                backend=smtp,
                host="smtp.example.edu",
                username="mailer",
                default_from_email="noreply@example.edu",
            )


class ProductionSecretConfigurationTests(SimpleTestCase):
    def test_development_secret_is_rejected_when_debug_is_disabled(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SECRET_KEY"):
            validate_secret_key(DEVELOPMENT_SECRET_KEY, debug=False)

    def test_development_secret_remains_usable_locally(self):
        self.assertEqual(
            validate_secret_key(DEVELOPMENT_SECRET_KEY, debug=True),
            DEVELOPMENT_SECRET_KEY,
        )

class DeploymentSecurityTests(SimpleTestCase):
    def test_production_requires_https_origins(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "must use HTTPS"):
            build_deployment_security(
                debug=False,
                allowed_hosts=["app.example.edu"],
                cors_origins=["http://app.example.edu"],
            )

    def test_production_enables_https_cookie_and_hsts_controls(self):
        config = build_deployment_security(
            debug=False,
            allowed_hosts=["app.example.edu"],
            cors_origins=["https://app.example.edu"],
            trust_proxy=True,
        )
        self.assertTrue(config["SECURE_SSL_REDIRECT"])
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["CSRF_COOKIE_SECURE"])
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 31_536_000)
        self.assertEqual(config["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_production_accepts_multiple_https_frontend_origins(self):
        config = build_deployment_security(
            debug=False,
            allowed_hosts=["api.example.edu"],
            cors_origins=[
                "https://faculty.example.edu",
                "https://faculty-preview.vercel.app",
            ],
        )

        self.assertTrue(config["SECURE_SSL_REDIRECT"])

    def test_vercel_requires_production_mode_proxy_https_and_tls_redis(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DEBUG=True"):
            validate_vercel_runtime(debug=True, trust_proxy=True, redis_url="rediss://cache")
        with self.assertRaisesMessage(ImproperlyConfigured, "TRUST_PROXY_SSL_HEADER=True"):
            validate_vercel_runtime(debug=False, trust_proxy=False, redis_url="rediss://cache")
        with self.assertRaisesMessage(ImproperlyConfigured, "rediss://"):
            validate_vercel_runtime(debug=False, trust_proxy=True, redis_url="redis://cache")
        validate_vercel_runtime(debug=False, trust_proxy=True, redis_url="rediss://cache")

    def test_password_policy_enforces_length_and_character_variety(self):
        validator = StrongPasswordValidator()
        with self.assertRaises(ValidationError):
            validator.validate("Short123!")
        with self.assertRaises(ValidationError):
            validator.validate("abcdefghijkl")
        validator.validate("GoodPassword123!")

    def test_production_accepts_an_explicit_secret(self):
        explicit_secret = "a" * 50
        self.assertEqual(
            validate_secret_key(explicit_secret, debug=False),
            explicit_secret,
        )


class DatabaseMigrationTests(TestCase):
    def test_core_initial_migration_is_applied(self):
        self.assertIn(
            ("core", "0001_initial"),
            MigrationRecorder(connection).applied_migrations(),
        )

    def test_read_only_migration_verifier_accepts_same_database(self):
        output = StringIO()

        call_command(
            "verify_database_migration",
            source_alias="default",
            target_alias="default",
            stdout=output,
        )

        self.assertIn("Matched row counts", output.getvalue())


class NotificationWorkflowTests(APITestCase):
    def setUp(self):
        self.faculty = User.objects.create_user(
            username="faculty_member",
            password="test-password",
            role=User.Role.FACULTY,
            department="Physics",
        )
        self.hod = User.objects.create_user(
            username="department_hod",
            password="test-password",
            role=User.Role.HOD,
            department="Physics",
        )
        self.admin = User.objects.create_user(
            username="university_admin",
            password="test-password",
            role=User.Role.ADMIN,
        )
        self.period = AppraisalPeriod.objects.create(
            name="Test appraisal period",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.policy = AppraisalPolicy.objects.create(
            period=self.period,
            version=1,
            rules={
                category: {"points_per_item": 2, "max_points": 5}
                for category, _ in Activity.Category.choices
            },
            status=AppraisalPolicy.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )

    def test_health_endpoint_is_public_and_confirms_database_readiness(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"status": "ok"})

    def test_activity_verification_notifies_faculty(self):
        activity = Activity.objects.create(
            faculty=self.faculty,
            category=Activity.Category.PUBLICATION,
            title="Verified publication",
        )
        self.client.force_authenticate(self.hod)

        response = self.client.post(
            f"/api/activities/{activity.id}/verify/",
            {"verification_status": "VERIFIED", "reviewer_note": "Evidence checked."},
        )

        self.assertEqual(response.status_code, 200)
        notification = Notification.objects.get(user=self.faculty)
        self.assertIn("marked verified", notification.message)
        self.assertIn("Evidence checked.", notification.message)

    @override_settings(EVIDENCE_UPLOAD_MAX_BYTES=1024 * 1024)
    def test_evidence_upload_uses_configured_size_limit(self):
        activity = Activity.objects.create(
            faculty=self.faculty,
            category=Activity.Category.TEACHING,
            title="Upload limit test",
        )
        self.client.force_authenticate(self.faculty)

        response = self.client.post(
            f"/api/activities/{activity.pk}/evidence/",
            {
                "file": SimpleUploadedFile(
                    "evidence.pdf",
                    b"x" * (1024 * 1024 + 1),
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "File must be 1 MB or smaller.")

    def test_submission_notifies_department_reviewers(self):
        self.client.force_authenticate(self.faculty)

        response = self.client.post(
            "/api/submissions/submit/",
            {"faculty_statement": "Annual academic summary"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Notification.objects.filter(user=self.hod, message__contains="submitted an appraisal").exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, message__contains="submitted an appraisal").exists())
        self.assertTrue(Notification.objects.filter(user=self.faculty, message__contains="was submitted").exists())

    def test_mark_all_read_only_updates_current_users_notifications(self):
        own_notifications = [
            Notification.objects.create(user=self.faculty, message="First update"),
            Notification.objects.create(user=self.faculty, message="Second update"),
        ]
        other_notification = Notification.objects.create(user=self.hod, message="Private update")
        self.client.force_authenticate(self.faculty)

        response = self.client.post("/api/notifications/mark_all_read/")

        self.assertEqual(response.status_code, 200)
        for notification in own_notifications:
            notification.refresh_from_db()
            self.assertTrue(notification.is_read)
        other_notification.refresh_from_db()
        self.assertFalse(other_notification.is_read)

    def test_profile_update_cannot_change_department_or_role(self):
        self.client.force_authenticate(self.hod)

        response = self.client.patch(
            "/api/auth/me/",
            {"department": "Another department", "role": User.Role.ADMIN, "phone": "1234567890"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.hod.refresh_from_db()
        self.assertEqual(self.hod.department, "Physics")
        self.assertEqual(self.hod.role, User.Role.HOD)
        self.assertEqual(self.hod.phone, "1234567890")

    def test_google_scholar_profile_only_accepts_public_citation_urls(self):
        self.client.force_authenticate(self.faculty)
        valid = self.client.patch(
            "/api/auth/me/",
            {"google_scholar_url": "https://scholar.google.com/citations?user=abc123"},
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.google_scholar_url, "https://scholar.google.com/citations?user=abc123")

        invalid = self.client.patch(
            "/api/auth/me/",
            {"google_scholar_url": "https://example.com/citations?user=abc123"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_privacy_export_contains_only_authenticated_faculty_records(self):
        Activity.objects.create(
            faculty=self.faculty,
            category=Activity.Category.TEACHING,
            title="Faculty private activity",
        )
        other = User.objects.create_user(
            username="other_faculty",
            password="SecurePassword123!",
            role=User.Role.FACULTY,
        )
        Activity.objects.create(
            faculty=other,
            category=Activity.Category.TEACHING,
            title="Other private activity",
        )
        self.client.force_authenticate(self.faculty)

        response = self.client.get("/api/auth/me/export/")

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["activities"]]
        self.assertEqual(titles, ["Faculty private activity"])


class PolicyAndAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="policy_admin",
            password="SecurePassword123!",
            role=User.Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            username="policy_faculty",
            password="SecurePassword123!",
            role=User.Role.FACULTY,
        )
        self.period = AppraisalPeriod.objects.create(
            name="Policy scoring period",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.rules = {
            category: {"points_per_item": 3, "max_points": 5}
            for category, _ in Activity.Category.choices
        }

    def test_scoring_requires_an_approved_policy_and_applies_caps(self):
        Activity.objects.create(
            faculty=self.faculty,
            category=Activity.Category.PUBLICATION,
            title="First publication",
            activity_date=date(2026, 3, 1),
            verification_status=Activity.Verification.VERIFIED,
        )
        Activity.objects.create(
            faculty=self.faculty,
            category=Activity.Category.PUBLICATION,
            title="Second publication",
            activity_date=date(2026, 4, 1),
            verification_status=Activity.Verification.VERIFIED,
        )
        unconfigured = calculate_appraisal(self.faculty, self.period)
        self.assertFalse(unconfigured["policy"]["configured"])
        policy = AppraisalPolicy.objects.create(
            period=self.period,
            version=1,
            rules=self.rules,
            status=AppraisalPolicy.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )

        score = calculate_appraisal(self.faculty, self.period, policy)

        publication = next(row for row in score["breakdown"] if row["category"] == "PUBLICATION")
        self.assertEqual(publication["subtotal"], "5")
        self.assertEqual(score["policy"]["version"], 1)

    def test_approved_policy_cannot_be_changed_or_deleted(self):
        policy = AppraisalPolicy.objects.create(
            period=self.period,
            version=1,
            rules=self.rules,
            status=AppraisalPolicy.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )
        policy.rules["PUBLICATION"]["points_per_item"] = 100
        with self.assertRaisesMessage(ValidationError, "immutable"):
            policy.save()
        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            policy.delete()

    def test_audit_chain_is_verifiable_and_database_rejects_mutation(self):
        event = record_audit_event(
            actor=self.admin,
            event_type="test_event",
            instance=self.faculty,
            details={"role": self.faculty.role},
        )
        self.assertTrue(verify_audit_chain())
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(event_type="changed")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).delete()
        self.assertTrue(verify_audit_chain())


class PolicyApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="policy_api_admin",
            password="Admin-password-123!",
            role=User.Role.ADMIN,
        )
        self.period = AppraisalPeriod.objects.create(
            name="Policy API period",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.client.force_authenticate(self.admin)

    def test_admin_can_create_an_empty_policy_draft(self):
        response = self.client.post(
            "/api/policies/",
            {"period": self.period.pk, "version": 1, "rules": {}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rules"], {})
        self.assertEqual(response.data["status"], AppraisalPolicy.Status.DRAFT)
        self.assertTrue(
            AppraisalPolicy.objects.filter(period=self.period, version=1).exists()
        )

    def test_invalid_policy_rules_return_a_validation_response(self):
        response = self.client.post(
            "/api/policies/",
            {
                "period": self.period.pk,
                "version": 1,
                "rules": {"NOT_A_CATEGORY": {"points_per_item": 3}},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rules", response.data)
        self.assertFalse(AppraisalPolicy.objects.exists())

class DataRetentionTests(TestCase):
    @override_settings(NOTIFICATION_RETENTION_DAYS=30)
    def test_retention_command_is_dry_run_unless_explicitly_applied(self):
        old_read = Notification.objects.create(user=User.objects.create_user(username="old_notice"), message="Read", is_read=True)
        Notification.objects.filter(pk=old_read.pk).update(created_at=timezone.now() - timedelta(days=45))
        unread = Notification.objects.create(user=old_read.user, message="Unread", is_read=False)
        output = StringIO()
        call_command("apply_data_retention", stdout=output)
        self.assertIn("Dry run", output.getvalue())
        self.assertTrue(Notification.objects.filter(pk=old_read.pk).exists())
        call_command("apply_data_retention", "--apply", stdout=StringIO())
        self.assertFalse(Notification.objects.filter(pk=old_read.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=unread.pk).exists())

    @override_settings(NOTIFICATION_RETENTION_DAYS=0)
    def test_retention_command_requires_explicit_period(self):
        with self.assertRaises(CommandError):
            call_command("apply_data_retention")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_FRONTEND_URL="https://app.example.edu/reset-password",
    EMAIL_VERIFICATION_FRONTEND_URL="https://app.example.edu/verify-email",
    PUBLIC_REGISTRATION_ENABLED=True,
)
class AccountSecurityWorkflowTests(APITestCase):
    def setUp(self):
        mail.outbox.clear()

    def test_registration_requires_email_verification_before_token_login(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new_faculty",
                "email": "new_faculty@example.edu",
                "first_name": "New",
                "last_name": "Faculty",
                "password": "SecurePassword123!",
                "employee_code": "NEW001",
                "department": "Physics",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="new_faculty")
        self.assertFalse(user.email_verified)
        login = self.client.post(
            "/api/auth/token/",
            {"username": "new_faculty", "password": "SecurePassword123!"},
        )
        self.assertEqual(login.status_code, 400)
        token = signing.dumps(
            {"user_id": user.pk, "email": user.email},
            salt="facultyadvance.email-verification",
        )
        verified = self.client.post("/api/auth/verify-email/", {"token": token})
        self.assertEqual(verified.status_code, 200)
        login = self.client.post(
            "/api/auth/token/",
            {"username": "new_faculty", "password": "SecurePassword123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_password_reset_mail_issues_one_time_token(self):
        user = User.objects.create_user(
            username="reset_user",
            email="reset@example.edu",
            password="OldSecurePassword123!",
            email_verified=True,
        )
        response = self.client.post(
            "/api/auth/password-reset/", {"email": user.email}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        link = mail.outbox[0].body.splitlines()[-1]
        query = parse_qs(urlsplit(link).query)
        reset = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": query["uid"][0],
                "token": query["token"][0],
                "new_password": "NewSecurePassword456!",
            },
            format="json",
        )
        self.assertEqual(reset.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewSecurePassword456!"))
        reused = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": query["uid"][0],
                "token": query["token"][0],
                "new_password": "AnotherSecurePassword789!",
            },
            format="json",
        )
        self.assertEqual(reused.status_code, 400)


class GoogleSSOWorkflowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="google_faculty",
            email="faculty@university.example",
            password="ExistingSecurePassword123!",
            role="FACULTY",
        )

    @override_settings(
        GOOGLE_SSO_CLIENT_ID="",
        GOOGLE_SSO_CLIENT_SECRET="",
        GOOGLE_SSO_WORKSPACE_DOMAIN="",
        GOOGLE_SSO_REDIRECT_URI="",
    )
    def test_sso_start_fails_closed_until_configured(self):
        response = self.client.get("/api/auth/google/start/")
        self.assertEqual(response.status_code, 503)

    def test_login_ticket_is_single_use_and_returns_tokens(self):
        raw_ticket = "one-time-ticket-value"
        import hashlib

        ticket = GoogleSSOLoginTicket.objects.create(
            user=self.user,
            token_hash=hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
            expires_at=timezone.now() + timedelta(seconds=90),
        )
        response = self.client.post(
            "/api/auth/google/complete/", {"ticket": raw_ticket}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.consumed_at)

        replay = self.client.post(
            "/api/auth/google/complete/", {"ticket": raw_ticket}, format="json"
        )
        self.assertEqual(replay.status_code, 400)

    def test_expired_login_ticket_is_rejected(self):
        raw_ticket = "expired-one-time-ticket"
        import hashlib

        GoogleSSOLoginTicket.objects.create(
            user=self.user,
            token_hash=hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.post(
            "/api/auth/google/complete/", {"ticket": raw_ticket}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class MalwareScannerIntegrationTests(SimpleTestCase):
    class FakeClamdSocket:
        def __init__(self, scan_reply=b"stream: OK\0"):
            self.scan_reply = scan_reply
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, timeout):
            pass

        def sendall(self, payload):
            pass

        def recv(self, size):
            self.calls += 1
            if self.calls == 1:
                return b"PONG\0"
            return self.scan_reply if self.calls == 2 else b""

    @override_settings(MALWARE_SCANNER="clamd", CLAMD_HOST="scanner", CLAMD_PORT=3310, CLAMD_TIMEOUT=1)
    def test_clamd_clean_result_is_accepted(self):
        upload = SimpleUploadedFile("evidence.pdf", b"safe file")
        fake_socket = self.FakeClamdSocket()
        with patch("core.services.socket.create_connection", return_value=fake_socket):
            self.assertTrue(scan_uploaded_file(upload))

    @override_settings(MALWARE_SCANNER="clamd", CLAMD_HOST="scanner", CLAMD_PORT=3310, CLAMD_TIMEOUT=1)
    def test_clamd_infected_result_is_rejected(self):
        upload = SimpleUploadedFile("evidence.pdf", b"infected test payload")
        fake_socket = self.FakeClamdSocket(b"stream: Eicar-Test-Signature FOUND\0")
        with patch("core.services.socket.create_connection", return_value=fake_socket):
            self.assertFalse(scan_uploaded_file(upload))

    @override_settings(MALWARE_SCANNER="clamd", CLAMD_HOST="scanner", CLAMD_PORT=3310, CLAMD_TIMEOUT=1)
    def test_clamd_outage_fails_closed(self):
        upload = SimpleUploadedFile("evidence.pdf", b"safe file")
        with patch("core.services.socket.create_connection", side_effect=OSError("offline")):
            with self.assertRaises(RuntimeError):
                scan_uploaded_file(upload)

    @override_settings(MALWARE_SCANNER="clamd", CLAMD_HOST="scanner", CLAMD_PORT=3310, CLAMD_TIMEOUT=1)
    def test_clamd_unrecognized_reply_fails_closed(self):
        upload = SimpleUploadedFile("evidence.pdf", b"safe file")
        fake_socket = self.FakeClamdSocket(b"unrecognized response\0")
        with patch("core.services.socket.create_connection", return_value=fake_socket):
            with self.assertRaises(RuntimeError):
                scan_uploaded_file(upload)

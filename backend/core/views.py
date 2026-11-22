import logging
import hashlib
import secrets
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape
import requests
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db import DatabaseError, connection
from rest_framework import generics, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.viewsets import ModelViewSet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, TableStyle
from .models import Activity, EvidenceDocument, AppraisalPeriod, AppraisalSubmission, Review, Notification, AppraisalCriterion, AppraisalPolicy, GoogleSSOLoginTicket
from .serializers import RegisterSerializer, UserSerializer, ActivitySerializer, EvidenceSerializer, PeriodSerializer, SubmissionSerializer, ReviewSerializer, NotificationSerializer, CriterionSerializer, AppraisalPolicySerializer, StrongTokenObtainPairSerializer
from .permissions import IsReviewerOrAdmin, IsAdminRole, IsActivityOwnerOrAdmin
from .services import calculate_appraisal, record_audit_event, scan_uploaded_file
from .account_services import (
    reset_user_password,
    send_alert_email,
    send_email_verification,
    send_password_reset,
    verify_email_token,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def create_workflow_notification(user, *, message, email_subject=None, email_message=None):
    notification = Notification.objects.create(user=user, message=(message or "")[:300])
    if user.email and getattr(__import__("django.conf"), "settings").EMAIL_ALERTS_ENABLED:
        send_alert_email(
            user,
            subject=email_subject or "FacultyAdvance workflow update",
            message=email_message or message,
        )
    return notification


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        try:
            connection.ensure_connection()
        except DatabaseError:
            return Response(
                {"status": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok"})


class GoogleSSOStartView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def get(self, request):
        from django.conf import settings
        if not all((settings.GOOGLE_SSO_CLIENT_ID, settings.GOOGLE_SSO_CLIENT_SECRET,
                    settings.GOOGLE_SSO_WORKSPACE_DOMAIN, settings.GOOGLE_SSO_REDIRECT_URI)):
            return Response({"detail": "Google Workspace sign-in is not configured."}, status=503)
        from authlib.integrations.django_client import OAuth
        oauth = OAuth()
        google = oauth.register(
            name="google",
            client_id=settings.GOOGLE_SSO_CLIENT_ID,
            client_secret=settings.GOOGLE_SSO_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        return google.authorize_redirect(
            request,
            settings.GOOGLE_SSO_REDIRECT_URI,
            hd=settings.GOOGLE_SSO_WORKSPACE_DOMAIN,
        )


class GoogleSSOCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def get(self, request):
        from django.conf import settings
        if not settings.GOOGLE_SSO_CLIENT_ID:
            return Response({"detail": "Google Workspace sign-in is not configured."}, status=503)
        from authlib.integrations.django_client import OAuth
        oauth = OAuth()
        google = oauth.register(
            name="google",
            client_id=settings.GOOGLE_SSO_CLIENT_ID,
            client_secret=settings.GOOGLE_SSO_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        try:
            token = google.authorize_access_token(request)
            identity = token.get("userinfo") or google.userinfo(token=token)
            email = str(identity.get("email", "")).strip().lower()
            hosted_domain = str(identity.get("hd", "")).strip().lower()
            email_verified = identity.get("email_verified") is True or identity.get("email_verified") == "true"
            if (not email_verified or not email or hosted_domain != settings.GOOGLE_SSO_WORKSPACE_DOMAIN
                    or email.rsplit("@", 1)[-1] != settings.GOOGLE_SSO_WORKSPACE_DOMAIN):
                return Response({"detail": "Use a verified account from your configured Google Workspace domain."}, status=403)
            matches = User.objects.filter(email__iexact=email, is_active=True)
            if matches.count() != 1:
                return Response({"detail": "This Google account is not linked to one active institutional account. Contact your administrator."}, status=403)
            user = matches.get()
            raw_ticket = secrets.token_urlsafe(32)
            GoogleSSOLoginTicket.objects.create(
                user=user,
                token_hash=hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest(),
                expires_at=timezone.now() + timedelta(seconds=90),
            )
            record_audit_event(actor=user, event_type="google_sso_login", instance=user)
            from django.shortcuts import redirect
            from urllib.parse import urlencode
            return redirect(f"{settings.GOOGLE_SSO_FRONTEND_CALLBACK}?{urlencode({'ticket': raw_ticket})}")
        except Exception:
            logger.exception("Google Workspace OAuth callback failed.")
            return Response({"detail": "Google sign-in failed. Try again or contact your administrator."}, status=400)


class GoogleSSOCompleteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        raw_ticket = str(request.data.get("ticket", ""))
        if not raw_ticket or len(raw_ticket) > 128:
            return Response({"detail": "A valid sign-in ticket is required."}, status=400)
        digest = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
        with transaction.atomic():
            ticket = GoogleSSOLoginTicket.objects.select_for_update().filter(token_hash=digest).first()
            if not ticket or ticket.consumed_at or ticket.expires_at <= timezone.now():
                return Response({"detail": "This sign-in ticket is invalid or expired. Start again."}, status=400)
            ticket.consumed_at = timezone.now()
            ticket.save(update_fields=["consumed_at"])
            user = ticket.user
            if not user.is_active:
                return Response({"detail": "This account is inactive."}, status=403)
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            })


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "registration"

    def create(self, request, *args, **kwargs):
        from django.conf import settings
        if not settings.PUBLIC_REGISTRATION_ENABLED:
            return Response(
                {"detail": "Public registration is disabled. Contact your institution's administrator."},
                status=status.HTTP_403_FORBIDDEN,
            )
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(username=request.data.get("username"))
        record_audit_event(
            actor=user,
            event_type="account_registered",
            instance=user,
            details={"role": user.role},
        )
        try:
            send_email_verification(user)
        except Exception:
            logger.exception("Verification email delivery failed for user id %s.", user.pk)
            return Response(
                {"detail": "Account created, but verification email could not be sent. Please request a new verification email."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"detail": "Account created. Check your email to verify the address before signing in."},
            status=response.status_code,
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email"

    def post(self, request):
        token = request.data.get("token", "")
        try:
            user = verify_email_token(token)
        except (signing.BadSignature, User.DoesNotExist, KeyError, TypeError):
            return Response(
                {"detail": "Verification link is invalid or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_audit_event(actor=user, event_type="email_verified", instance=user)
        return Response({"detail": "Email verified. You can now sign in."})


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email"

    def post(self, request):
        email = request.data.get("email", "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True, email_verified=False).first()
        if user:
            try:
                send_email_verification(user)
            except Exception:
                logger.exception("Verification email delivery failed for user id %s.", user.pk)
                return Response(
                    {"detail": "Email delivery is temporarily unavailable. Please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response({"detail": "If the account needs verification, an email will be sent."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "email"

    def post(self, request):
        email = request.data.get("email", "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True, email_verified=True).first()
        if user:
            try:
                send_password_reset(user)
            except Exception:
                logger.exception("Password reset email delivery failed for user id %s.", user.pk)
                return Response(
                    {"detail": "Email delivery is temporarily unavailable. Please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response({"detail": "If a verified account exists for that email, reset instructions will be sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        uid = request.data.get("uid", "")
        token = request.data.get("token", "")
        password = request.data.get("new_password", "")
        try:
            from django.utils.encoding import force_str
            from django.utils.http import urlsafe_base64_decode
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
            password_validation.validate_password(password, user)
            user = reset_user_password(uid=uid, token=token, password=password)
        except (User.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            user = None
        if user is None:
            return Response(
                {"detail": "Password reset link is invalid or expired, or the password does not meet requirements."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_audit_event(actor=user, event_type="password_reset", instance=user)
        return Response({"detail": "Password updated. You can sign in with the new password."})


class SecureTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    serializer_class = StrongTokenObtainPairSerializer

class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)
    def patch(self, request):
        previous_email = request.user.email
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        if user.email != previous_email:
            user.email_verified = False
            user.save(update_fields=["email_verified"])
            try:
                send_email_verification(user)
            except Exception:
                logger.exception("Verification email delivery failed for user id %s.", user.pk)
                return Response(
                    {"detail": "Profile saved, but email verification could not be sent. Request a verification email later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        record_audit_event(
            actor=user,
            event_type="profile_updated",
            instance=user,
            details={"email_changed": user.email != previous_email},
        )
        return Response(serializer.data)

class PrivacyExportView(APIView):
    def get(self, request):
        user = request.user
        activities = Activity.objects.filter(faculty=user).prefetch_related("evidence")
        submissions = AppraisalSubmission.objects.filter(faculty=user).select_related(
            "period", "policy"
        ).prefetch_related("reviews")
        notifications = Notification.objects.filter(user=user)
        record_audit_event(
            actor=user,
            event_type="personal_data_exported",
            instance=user,
        )
        return Response({
            "exported_at": timezone.now().isoformat(),
            "profile": UserSerializer(user).data,
            "activities": ActivitySerializer(
                activities, many=True, context={"request": request}
            ).data,
            "submissions": SubmissionSerializer(
                submissions, many=True, context={"request": request}
            ).data,
            "notifications": NotificationSerializer(
                notifications, many=True, context={"request": request}
            ).data,
        })

class ActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "doi", "journal_or_venue", "organizer", "faculty__employee_code", "faculty__first_name", "faculty__last_name"]
    ordering_fields = ["activity_date", "title", "created_at", "verification_status"]
    def get_queryset(self):
        user = self.request.user
        qs = Activity.objects.select_related("faculty").prefetch_related("evidence")
        if user.is_superuser or user.role == "ADMIN":
            pass
        elif user.role == "HOD":
            qs = qs.filter(faculty__department=user.department)
        else:
            qs = qs.filter(faculty=user)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        verification = self.request.query_params.get("verification_status")
        if verification:
            qs = qs.filter(verification_status=verification)
        faculty_id = self.request.query_params.get("faculty")
        if faculty_id:
            qs = qs.filter(faculty_id=faculty_id)
        return qs
    def perform_create(self, serializer):
        activity = serializer.save(faculty=self.request.user)
        record_audit_event(
            actor=self.request.user,
            event_type="activity_created",
            instance=activity,
            details={"category": activity.category},
        )

    def perform_update(self, serializer):
        activity = serializer.instance
        if activity and activity._has_submitted_appraisal():
            raise DjangoValidationError("This activity is frozen because the faculty appraisal has already been submitted.")
        changed_fields = sorted(serializer.validated_data.keys())
        activity = serializer.save()
        record_audit_event(
            actor=self.request.user,
            event_type="activity_updated",
            instance=activity,
            details={"changed_fields": changed_fields},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        if instance._has_submitted_appraisal():
            raise DjangoValidationError("This activity is frozen because the faculty appraisal has already been submitted.")
        record_audit_event(
            actor=self.request.user,
            event_type="activity_deleted",
            instance=instance,
            details={"category": instance.category},
        )
        instance.delete()
    def get_permissions(self):
        if self.action == "verify":
            return [IsReviewerOrAdmin()]
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsActivityOwnerOrAdmin()]
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAuthenticated()]
    @action(detail=True, methods=["post"], permission_classes=[IsReviewerOrAdmin])
    def verify(self, request, pk=None):
        activity = self.get_object()
        if request.user.role == "HOD" and activity.faculty.department != request.user.department:
            return Response({"detail": "You can only review activities from your department."}, status=403)
        value = request.data.get("verification_status")
        if value not in ["VERIFIED", "REJECTED", "PENDING"]:
            return Response({"detail": "verification_status must be VERIFIED, REJECTED or PENDING."}, status=400)
        activity.verification_status = value
        activity.reviewer_note = request.data.get("reviewer_note", "")
        activity.save(update_fields=["verification_status", "reviewer_note", "updated_at"])
        record_audit_event(
            actor=request.user,
            event_type="activity_verification_changed",
            instance=activity,
            details={"verification_status": value},
        )
        status_label = activity.get_verification_status_display().lower()
        message = f'Your activity "{activity.title}" was marked {status_label}.'
        if activity.reviewer_note:
            message = f"{message} Reviewer note: {activity.reviewer_note}"
        create_workflow_notification(
            activity.faculty,
            message=message[:300],
            email_subject=f"FacultyAdvance activity update: {activity.title}",
            email_message=message,
        )
        # Keep already-submitted appraisal totals in sync when evidence is verified/rejected.
        for submission in AppraisalSubmission.objects.filter(
            faculty=activity.faculty,
            period__start_date__lte=activity.activity_date,
            period__end_date__gte=activity.activity_date,
        ).select_related("period"):
            submission.total_score = calculate_appraisal(
                activity.faculty, submission.period, submission.policy
            )["total_score"]
            submission.save(update_fields=["total_score", "updated_at"])
        return Response(ActivitySerializer(activity).data)

class EvidenceUploadView(generics.CreateAPIView):
    serializer_class = EvidenceSerializer
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request, activity_id):
        activity = get_object_or_404(Activity, pk=activity_id)
        if activity.faculty_id != request.user.id and request.user.role not in ("HOD", "ADMIN") and not request.user.is_superuser:
            return Response({"detail": "Not allowed."}, status=403)
        if request.user.role == "HOD" and activity.faculty.department != request.user.department:
            return Response({"detail": "Not allowed."}, status=403)
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Select a file."}, status=400)
        from django.conf import settings
        max_upload_bytes = settings.EVIDENCE_UPLOAD_MAX_BYTES
        if upload.size > max_upload_bytes:
            max_upload_mb = max_upload_bytes // (1024 * 1024)
            return Response(
                {"detail": f"File must be {max_upload_mb} MB or smaller."},
                status=400,
            )
        extension = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
        if extension not in {"pdf", "png", "jpg", "jpeg"}:
            return Response({"detail": "Only PDF, PNG and JPG files are accepted."}, status=400)
        try:
            if not scan_uploaded_file(upload):
                return Response({"detail": "Uploaded file failed malware scanning."}, status=400)
        except RuntimeError:
            logger.exception("Malware scan failed for evidence upload by user %s.", request.user.pk)
            return Response({"detail": "Malware scan is unavailable; upload rejected."}, status=503)
        evidence = EvidenceDocument.objects.create(activity=activity, file=upload)
        record_audit_event(
            actor=request.user,
            event_type="evidence_uploaded",
            instance=evidence,
            details={"activity_id": activity.pk, "file_name": evidence.original_name},
        )
        return Response(EvidenceSerializer(evidence).data, status=201)

class EvidenceDownloadView(APIView):
    def get(self, request, evidence_id):
        evidence = get_object_or_404(
            EvidenceDocument.objects.select_related("activity__faculty"),
            pk=evidence_id,
        )
        faculty = evidence.activity.faculty
        if request.user.role == "FACULTY" and faculty.pk != request.user.pk:
            return Response({"detail": "Not allowed."}, status=403)
        if request.user.role == "HOD" and faculty.department != request.user.department:
            return Response({"detail": "Not allowed."}, status=403)
        if request.user.role not in ("FACULTY", "HOD", "ADMIN") and not request.user.is_superuser:
            return Response({"detail": "Not allowed."}, status=403)
        record_audit_event(
            actor=request.user,
            event_type="evidence_downloaded",
            instance=evidence,
            details={"activity_id": evidence.activity_id},
        )
        return FileResponse(
            evidence.file.open("rb"),
            as_attachment=True,
            filename=evidence.original_name or "evidence",
            content_type="application/octet-stream",
        )

class PeriodListView(generics.ListAPIView):
    serializer_class = PeriodSerializer
    queryset = AppraisalPeriod.objects.all()

class CriterionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AppraisalCriterion.objects.all()
    serializer_class = CriterionSerializer
    permission_classes = [IsAdminRole]

class AppraisalPolicyViewSet(ModelViewSet):
    serializer_class = AppraisalPolicySerializer
    permission_classes = [IsAdminRole]
    queryset = AppraisalPolicy.objects.select_related("period", "approved_by")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        policy = serializer.save()
        record_audit_event(
            actor=self.request.user,
            event_type="appraisal_policy_created",
            instance=policy,
            details={"period_id": policy.period_id, "version": policy.version},
        )

    def perform_update(self, serializer):
        policy = serializer.save()
        record_audit_event(
            actor=self.request.user,
            event_type="appraisal_policy_updated",
            instance=policy,
            details={"period_id": policy.period_id, "version": policy.version},
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        policy = self.get_object()
        if policy.status != AppraisalPolicy.Status.DRAFT:
            return Response({"detail": "Only draft policies can be approved."}, status=400)
        policy.status = AppraisalPolicy.Status.APPROVED
        policy.approved_by = request.user
        policy.approved_at = timezone.now()
        policy.save()
        record_audit_event(
            actor=request.user,
            event_type="appraisal_policy_approved",
            instance=policy,
            details={"period_id": policy.period_id, "version": policy.version},
        )
        return Response(self.get_serializer(policy).data)

class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubmissionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["faculty__first_name", "faculty__last_name", "faculty__employee_code", "faculty__department"]
    ordering_fields = ["faculty__first_name", "faculty__employee_code", "submitted_at", "total_score", "status"]
    def get_queryset(self):
        user = self.request.user
        qs = AppraisalSubmission.objects.select_related("faculty", "period").prefetch_related("reviews")
        if user.is_superuser or user.role == "ADMIN":
            pass
        elif user.role == "HOD":
            qs = qs.filter(faculty__department=user.department)
        else:
            qs = qs.filter(faculty=user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs
    @action(detail=False, methods=["post"], url_path="submit")
    def submit_appraisal(self, request):
        if request.user.role != "FACULTY":
            return Response({"detail": "Only faculty members can submit an appraisal."}, status=403)
        period = AppraisalPeriod.objects.filter(is_active=True).first()
        if not period:
            return Response({"detail": "No active appraisal period is configured. Ask an administrator to create one."}, status=400)
        policy = AppraisalPolicy.objects.filter(
            period=period, status=AppraisalPolicy.Status.APPROVED
        ).order_by("-version").first()
        if policy is None:
            return Response(
                {"detail": "No approved appraisal policy is configured for the active period. Contact an administrator."},
                status=400,
            )
        score = calculate_appraisal(request.user, period, policy)
        submission, created = AppraisalSubmission.objects.get_or_create(
            faculty=request.user, period=period,
            defaults={"total_score": score["total_score"], "faculty_statement": request.data.get("faculty_statement", ""), "policy": policy},
        )
        if not created:
            if submission.status not in ["REVISION"]:
                return Response({"detail": "An appraisal for this period has already been submitted.", "submission": SubmissionSerializer(submission).data}, status=409)
            submission.total_score = score["total_score"]
            submission.policy = policy
            submission.faculty_statement = request.data.get("faculty_statement", submission.faculty_statement)
            submission.status = "SUBMITTED"
            submission.save()
        record_audit_event(
            actor=request.user,
            event_type="appraisal_submitted",
            instance=submission,
            details={"period_id": period.pk, "policy_id": policy.pk, "score": score["total_score"]},
        )
        create_workflow_notification(
            request.user,
            message=f"Your appraisal for {period.name} was submitted.",
            email_subject=f"FacultyAdvance appraisal submitted: {period.name}",
            email_message=f"Your appraisal for {period.name} was submitted. You will receive review updates by email as the workflow progresses.",
        )
        reviewers = User.objects.filter(role=User.Role.ADMIN) | User.objects.filter(
            role=User.Role.HOD, department=request.user.department
        )
        for reviewer in reviewers.distinct():
            create_workflow_notification(
                reviewer,
                message=f"{request.user.get_full_name() or request.user.username} submitted an appraisal for {period.name}.",
                email_subject=f"FacultyAdvance appraisal review pending: {period.name}",
                email_message=f"{request.user.get_full_name() or request.user.username} submitted an appraisal for {period.name}. Please review the submission in the admin workflow.",
            )
        return Response(SubmissionSerializer(submission).data, status=201 if created else 200)
    @action(detail=True, methods=["post"], permission_classes=[IsReviewerOrAdmin])
    def review(self, request, pk=None):
        submission = self.get_object()
        if request.user.role == "HOD" and submission.faculty.department != request.user.department:
            return Response({"detail": "You can only review faculty from your department."}, status=403)
        decision = request.data.get("decision")
        allowed = ["UNDER_REVIEW", "REVISION", "APPROVED", "REJECTED"]
        if decision not in allowed:
            return Response({"detail": f"decision must be one of {', '.join(allowed)}."}, status=400)
        comments = request.data.get("comments", "")
        Review.objects.create(submission=submission, reviewer=request.user, decision=decision, comments=comments)
        submission.status = decision
        submission.save(update_fields=["status", "updated_at"])
        record_audit_event(
            actor=request.user,
            event_type="appraisal_reviewed",
            instance=submission,
            details={"decision": decision},
        )
        Notification.objects.create(user=submission.faculty, message=f"Your appraisal status changed to {decision.replace('_', ' ').lower()}. {comments}"[:300])
        return Response(SubmissionSerializer(submission).data)

class ScoreView(APIView):
    def get(self, request):
        period = AppraisalPeriod.objects.filter(is_active=True).first()
        return Response(calculate_appraisal(request.user, period))

class AuditIntegrityView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        from .services import verify_audit_chain
        return Response({"valid": verify_audit_chain()})

class DashboardView(APIView):
    def get(self, request):
        user = request.user
        if user.role == "FACULTY" and not user.is_superuser:
            activities = Activity.objects.filter(faculty=user)
            submissions = AppraisalSubmission.objects.filter(faculty=user)
            period = AppraisalPeriod.objects.filter(is_active=True).first()
            score = calculate_appraisal(user, period)
            data = {"role": user.role, "activity_count": activities.count(), "verified_activities": activities.filter(verification_status="VERIFIED").count(), "publication_count": activities.filter(category="PUBLICATION").count(), "project_count": activities.filter(category="PROJECT").count(), "submission_count": submissions.count(), "latest_submission": SubmissionSerializer(submissions.first()).data if submissions.exists() else None, "score": score}
        else:
            submissions = AppraisalSubmission.objects.all()
            activities = Activity.objects.all()
            if user.role == "HOD" and not user.is_superuser:
                submissions = submissions.filter(faculty__department=user.department)
                activities = activities.filter(faculty__department=user.department)
            data = {"role": user.role, "faculty_count": User.objects.filter(role="FACULTY", **({"department": user.department} if user.role == "HOD" else {})).count(), "submission_count": submissions.count(), "pending_count": submissions.exclude(status__in=["APPROVED", "REJECTED"]).count(), "approved_count": submissions.filter(status="APPROVED").count(), "activity_count": activities.count()}
        return Response(data)

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    @action(detail=False, methods=["post"], url_path="mark_all_read")
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"detail": "All notifications marked as read."})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        obj = self.get_object(); obj.is_read = True; obj.save(update_fields=["is_read"])
        return Response(NotificationSerializer(obj).data)

class OrcidSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Provide a search query using ?q=..."}, status=400)
        try:
            response = requests.get(
                "https://pub.orcid.org/v3.0/search/",
                params={"q": query, "rows": 5},
                headers={"Accept": "application/json"},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            results = []
            for item in payload.get("result", []):
                identifier = item.get("orcid-identifier") or {}
                path = identifier.get("path")
                if not path:
                    continue
                results.append({
                    "orcid_id": path,
                    "display_name": item.get("display_name") or path,
                    "source": "ORCID",
                })
            return Response({"results": results, "source": "ORCID"})
        except requests.RequestException as exc:
            return Response({"detail": "ORCID search is temporarily unavailable.", "error": str(exc)}, status=502)


class OrcidProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orcid_id = request.query_params.get("orcid_id") or request.user.orcid_id
        if not orcid_id:
            return Response({"detail": "Add an ORCID ID to your profile before lookup."}, status=400)
        try:
            response = requests.get(
                f"https://pub.orcid.org/v3.0/{orcid_id}/person",
                headers={"Accept": "application/json"},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            names = payload.get("name", {})
            given = names.get("given-names", {}).get("value") if isinstance(names.get("given-names"), dict) else ""
            family = names.get("family-name", {}).get("value") if isinstance(names.get("family-name"), dict) else ""
            return Response({
                "orcid_id": orcid_id,
                "display_name": " ".join(part for part in [given, family] if part).strip() or orcid_id,
                "source": "ORCID public API",
            })
        except requests.RequestException as exc:
            return Response({"detail": "ORCID profile metadata is temporarily unavailable.", "error": str(exc)}, status=502)


class CrossrefSearchView(APIView):
    """Search Crossref for DOI metadata; users must confirm before saving an item."""
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Provide a search query using ?q=..."}, status=400)
        try:
            response = requests.get("https://api.crossref.org/works", params={"query.bibliographic": query, "rows": 8}, timeout=12, headers={"User-Agent": "FacultyAdvance/1.0 (academic appraisal demo)"})
            response.raise_for_status()
            items = response.json().get("message", {}).get("items", [])
            results = []
            for item in items:
                authors = [" ".join(x for x in [a.get("given"), a.get("family")] if x) for a in item.get("author", [])]
                results.append({"title": (item.get("title") or [""])[0], "doi": item.get("DOI", ""), "authors": ", ".join(authors), "venue": (item.get("container-title") or [""])[0], "published": item.get("published-print") or item.get("published-online") or item.get("created", {}), "type": item.get("type", "")})
            return Response({"results": results, "source": "Crossref", "confirmation_required": True})
        except requests.RequestException as exc:
            return Response({"detail": "Crossref could not be reached. Try again or add the publication manually.", "error": str(exc)}, status=502)

class ImportCrossrefView(APIView):
    def post(self, request):
        doi = request.data.get("doi", "").strip()
        if not doi:
            return Response({"detail": "DOI is required."}, status=400)
        doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        if Activity.objects.filter(faculty=request.user, doi__iexact=doi).exists():
            return Response({"detail": "This DOI is already present in your activities."}, status=409)
        try:
            response = requests.get(f"https://api.crossref.org/works/{doi}", timeout=12, headers={"User-Agent": "FacultyAdvance/1.0 (academic appraisal demo)"})
            response.raise_for_status(); item = response.json()["message"]
            title = (item.get("title") or [""])[0]
            authors = [" ".join(x for x in [a.get("given"), a.get("family")] if x) for a in item.get("author", [])]
            published = item.get("published-print") or item.get("published-online") or item.get("created", {})
            parts = published.get("date-parts", [[date.today().year]])
            ymd = parts[0] + [1, 1]
            activity_date = date(ymd[0], ymd[1], ymd[2])
            activity = Activity.objects.create(faculty=request.user, category="PUBLICATION", title=title[:300], authors=", ".join(authors)[:500], journal_or_venue=(item.get("container-title") or [""])[0][:300], doi=item.get("DOI", doi), activity_date=activity_date, source="CROSSREF", description="Imported from Crossref. Please confirm details and upload supporting evidence.")
            return Response(ActivitySerializer(activity).data, status=201)
        except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
            return Response({"detail": "Could not import this DOI. Check it or add the publication manually.", "error": str(exc)}, status=400)

class SubmissionPdfView(APIView):
    def get(self, request, submission_id):
        submission = get_object_or_404(AppraisalSubmission.objects.select_related("faculty", "period", "policy__period").prefetch_related("faculty__activities", "reviews"), pk=submission_id)
        if request.user.role == "FACULTY" and submission.faculty_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=403)
        if request.user.role == "HOD" and submission.faculty.department != request.user.department:
            return Response({"detail": "Not allowed."}, status=403)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
        styles = getSampleStyleSheet(); story = []
        f = submission.faculty
        story.append(Paragraph("FacultyAdvance — Faculty Appraisal Report", styles["Title"]))
        story.append(Spacer(1, 12))
        policy_label = (
            f"{submission.policy.period.name} v{submission.policy.version}"
            if submission.policy_id
            else "Legacy submission (policy not recorded)"
        )
        profile = [["Faculty name", escape(f.get_full_name() or f.username)], ["Employee code", escape(f.employee_code or "—")], ["Department", escape(f.department or "—")], ["Designation", escape(f.designation or "—")], ["Appraisal period", escape(submission.period.name)], ["Scoring policy", escape(policy_label)], ["Submission date", timezone.localtime(submission.submitted_at).strftime("%d %b %Y, %I:%M %p")], ["Status", escape(submission.get_status_display())], ["Verified activity score", escape(str(submission.total_score))]]
        table = Table(profile, colWidths=[135, 360]); table.setStyle(TableStyle([("BACKGROUND", (0,0),(0,-1),colors.HexColor("#EAF0F8")),("GRID",(0,0),(-1,-1),0.4,colors.grey),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),7)])); story.append(table)
        story.append(Spacer(1, 16)); story.append(Paragraph("Academic activities", styles["Heading2"]))
        rows = [["Category", "Activity", "Date", "Verification"]]
        for a in f.activities.filter(activity_date__gte=submission.period.start_date, activity_date__lte=submission.period.end_date).order_by("-activity_date").iterator(chunk_size=500):
            rows.append([Paragraph(escape(a.get_category_display()), styles["BodyText"]), Paragraph(escape(a.title), styles["BodyText"]), a.activity_date.strftime("%d-%m-%Y"), Paragraph(escape(a.get_verification_status_display()), styles["BodyText"])])
        act_table = LongTable(rows, repeatRows=1, splitByRow=1, colWidths=[105, 235, 75, 80]); act_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1E3A5F")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),5),("VALIGN",(0,0),(-1,-1),"TOP")])); story.append(act_table)
        if submission.faculty_statement:
            story.append(Spacer(1, 14)); story.append(Paragraph("Faculty statement", styles["Heading2"])); story.append(Paragraph(escape(submission.faculty_statement), styles["BodyText"]))
        if submission.reviews.exists():
            story.append(Spacer(1, 14)); story.append(Paragraph("Review history", styles["Heading2"]))
            for review in submission.reviews.all():
                story.append(Paragraph(f"{escape(review.get_decision_display())} — {escape(review.reviewer.get_full_name() or review.reviewer.username)}: {escape(review.comments or 'No comments')}", styles["BodyText"]))
        story.append(Spacer(1, 18)); story.append(Paragraph("This report is generated from the records stored in FacultyAdvance. Scores are indicative and must be interpreted under the institution's approved appraisal policy.", styles["Italic"]))
        doc.build(story); pdf = buffer.getvalue(); buffer.close()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="faculty-appraisal-{f.employee_code or f.username}.pdf"'
        return response

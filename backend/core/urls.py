from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import HealthCheckView, RegisterView, VerifyEmailView, ResendVerificationView, PasswordResetRequestView, PasswordResetConfirmView, SecureTokenObtainPairView, MeView, PrivacyExportView, ActivityViewSet, EvidenceUploadView, EvidenceDownloadView, PeriodListView, CriterionViewSet, AppraisalPolicyViewSet, SubmissionViewSet, ScoreView, AuditIntegrityView, DashboardView, NotificationViewSet, CrossrefSearchView, ImportCrossrefView, SubmissionPdfView, OrcidSearchView, OrcidProfileView, GoogleSSOStartView, GoogleSSOCallbackView, GoogleSSOCompleteView

router = DefaultRouter()
router.register("activities", ActivityViewSet, basename="activity")
router.register("criteria", CriterionViewSet, basename="criterion")
router.register("policies", AppraisalPolicyViewSet, basename="policy")
router.register("submissions", SubmissionViewSet, basename="submission")
router.register("notifications", NotificationViewSet, basename="notification")
urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/token/", SecureTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/google/start/", GoogleSSOStartView.as_view(), name="google-sso-start"),
    path("auth/google/callback/", GoogleSSOCallbackView.as_view(), name="google-sso-callback"),
    path("auth/google/complete/", GoogleSSOCompleteView.as_view(), name="google-sso-complete"),
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("auth/resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/me/export/", PrivacyExportView.as_view(), name="privacy-export"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("score/", ScoreView.as_view(), name="score"),
    path("periods/", PeriodListView.as_view(), name="periods"),
    path("activities/<int:activity_id>/evidence/", EvidenceUploadView.as_view(), name="evidence-upload"),
    path("evidence/<int:evidence_id>/download/", EvidenceDownloadView.as_view(), name="evidence-download"),
    path("audit/integrity/", AuditIntegrityView.as_view(), name="audit-integrity"),
    path("research/crossref/", CrossrefSearchView.as_view(), name="crossref-search"),
    path("research/crossref/import/", ImportCrossrefView.as_view(), name="crossref-import"),
    path("research/orcid/search/", OrcidSearchView.as_view(), name="orcid-search"),
    path("research/orcid/profile/", OrcidProfileView.as_view(), name="orcid-profile"),
    path("submissions/<int:submission_id>/pdf/", SubmissionPdfView.as_view(), name="submission-pdf"),
    path("", include(router.urls)),
]

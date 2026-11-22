from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
import json


class User(AbstractUser):
    class Role(models.TextChoices):
        FACULTY = "FACULTY", "Faculty"
        HOD = "HOD", "HOD / Reviewer"
        ADMIN = "ADMIN", "University Administrator"

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.FACULTY)
    employee_code = models.CharField(max_length=30, unique=True, null=True, blank=True)
    department = models.CharField(max_length=120, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    orcid_id = models.CharField(
        max_length=19,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")],
    )
    google_scholar_url = models.URLField(max_length=500, blank=True)
    email_verified = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role == self.Role.FACULTY:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class OrcidOAuthState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orcid_oauth_states")
    state_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class GoogleSSOLoginTicket(models.Model):
    """Short-lived, single-use handoff from Google OAuth to the SPA."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="google_sso_tickets")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AppraisalPeriod(models.Model):
    name = models.CharField(max_length=120, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class ActivityRevision(models.Model):
    activity_id = models.PositiveBigIntegerField(db_index=True)
    revision_number = models.PositiveIntegerField()
    event_type = models.CharField(max_length=20)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_revisions",
    )

    class Meta:
        ordering = ["-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_id", "revision_number"],
                name="unique_activity_revision_number",
            )
        ]


class Activity(models.Model):
    class Category(models.TextChoices):
        PUBLICATION = "PUBLICATION", "Research publication"
        BOOK = "BOOK", "Book / Chapter"
        SEMINAR = "SEMINAR", "Seminar / Conference"
        FDP = "FDP", "FDP / Workshop"
        PROJECT = "PROJECT", "Research / Academic project"
        TEACHING = "TEACHING", "Teaching activity"
        PATENT = "PATENT", "Patent"
        AWARD = "AWARD", "Award / Recognition"
        SERVICE = "SERVICE", "Institutional / Community service"
        OTHER = "OTHER", "Other achievement"

    class Verification(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    faculty = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities")
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    activity_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    organizer = models.CharField(max_length=250, blank=True)
    role_or_level = models.CharField(max_length=150, blank=True)
    authors = models.CharField(max_length=500, blank=True)
    journal_or_venue = models.CharField(max_length=300, blank=True)
    doi = models.CharField(max_length=250, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=30, default="MANUAL")
    verification_status = models.CharField(max_length=12, choices=Verification.choices, default=Verification.PENDING)
    reviewer_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date", "-created_at"]

    def __str__(self):
        return f"{self.title} ? {self.faculty}"

    def _snapshot(self):
        payload = {
            field: getattr(self, field)
            for field in [
                "id",
                "faculty_id",
                "category",
                "title",
                "description",
                "activity_date",
                "end_date",
                "organizer",
                "role_or_level",
                "authors",
                "journal_or_venue",
                "doi",
                "amount",
                "source",
                "verification_status",
                "reviewer_note",
                "created_at",
                "updated_at",
            ]
        }
        # JSONField accepts only JSON-native values; snapshots include dates and Decimals.
        return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))

    def _has_submitted_appraisal(self):
        from .models import AppraisalSubmission

        return AppraisalSubmission.objects.filter(
            faculty=self.faculty,
            status__in=[
                AppraisalSubmission.Status.SUBMITTED,
                AppraisalSubmission.Status.UNDER_REVIEW,
                AppraisalSubmission.Status.REVISION,
                AppraisalSubmission.Status.APPROVED,
                AppraisalSubmission.Status.REJECTED,
            ],
            period__start_date__lte=self.activity_date,
            period__end_date__gte=self.activity_date,
        ).exists()

    def save(self, *args, **kwargs):
        if self.pk and self._has_submitted_appraisal():
            raise ValidationError("This activity is frozen because the faculty appraisal has already been submitted.")
        super().save(*args, **kwargs)
        revision_number = ActivityRevision.objects.filter(activity_id=self.pk).count() + 1
        event_type = "created" if revision_number == 1 else "updated"
        ActivityRevision.objects.create(
            activity_id=self.pk,
            revision_number=revision_number,
            event_type=event_type,
            snapshot=self._snapshot(),
        )

    def delete(self, *args, **kwargs):
        if self._has_submitted_appraisal():
            raise ValidationError("This activity is frozen because the faculty appraisal has already been submitted.")
        activity_id = self.pk
        snapshot = self._snapshot()
        result = super().delete(*args, **kwargs)
        last_revision = ActivityRevision.objects.filter(activity_id=activity_id).order_by("-revision_number").first()
        revision_number = (last_revision.revision_number + 1) if last_revision else 1
        ActivityRevision.objects.create(
            activity_id=activity_id,
            revision_number=revision_number,
            event_type="deleted",
            snapshot=snapshot,
        )
        return result


class EvidenceDocument(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="evidence")
    file = models.FileField(upload_to="evidence/%Y/%m/", validators=[FileExtensionValidator(["pdf", "png", "jpg", "jpeg"])])
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = self.file.name.rsplit("/", 1)[-1]
        super().save(*args, **kwargs)


class AppraisalCriterion(models.Model):
    category = models.CharField(max_length=20, choices=Activity.Category.choices, unique=True)
    points_per_item = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    description = models.CharField(max_length=250, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["category"]

    def __str__(self):
        return f"{self.get_category_display()} ({self.points_per_item} points)"


class AppraisalPolicy(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        RETIRED = "RETIRED", "Retired"

    period = models.ForeignKey(
        AppraisalPeriod, on_delete=models.PROTECT, related_name="policies"
    )
    version = models.PositiveIntegerField(default=1)
    rules = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_appraisal_policies",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "version"], name="unique_period_policy_version"
            )
        ]

    def clean(self):
        if self.version < 1:
            raise ValidationError({"version": "Policy version must be positive."})
        if not isinstance(self.rules, dict):
            raise ValidationError({"rules": "Rules must be an object keyed by activity category."})
        known_categories = {value for value, _ in Activity.Category.choices}
        for category, rule in self.rules.items():
            if category not in known_categories or not isinstance(rule, dict):
                raise ValidationError({"rules": f"Invalid appraisal rule for {category}."})
            if set(rule) - {"points_per_item", "max_points"}:
                raise ValidationError({"rules": f"{category} contains unsupported rule fields."})
            points = rule.get("points_per_item")
            if isinstance(points, bool) or not isinstance(points, (int, float)) or points < 0:
                raise ValidationError(
                    {"rules": f"{category} must have non-negative points_per_item."}
                )
            cap = rule.get("max_points")
            if cap is not None and (
                isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0
            ):
                raise ValidationError(
                    {"rules": f"{category} max_points must be non-negative or null."}
                )
        if self.status == self.Status.APPROVED and (
            self.approved_by_id is None or self.approved_at is None
        ):
            raise ValidationError(
                "Approved policies require an approving administrator and approval timestamp."
            )
        if self.status == self.Status.APPROVED and set(self.rules) != known_categories:
            raise ValidationError(
                {"rules": "Approved policy must explicitly define every activity category."}
            )

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.status == self.Status.APPROVED:
                raise ValidationError("Approved appraisal policies are immutable.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.APPROVED:
            raise ValidationError("Approved appraisal policies cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.period.name} ? v{self.version} ({self.status})"


class AuditEvent(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
        editable=False,
    )
    event_type = models.CharField(max_length=80, editable=False)
    object_type = models.CharField(max_length=80, editable=False)
    object_id = models.CharField(max_length=80, editable=False)
    details = models.JSONField(default=dict, editable=False)
    previous_hash = models.CharField(max_length=64, blank=True, editable=False)
    entry_hash = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only.")


class AppraisalSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        REVISION = "REVISION", "Revision requested"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    faculty = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    period = models.ForeignKey(AppraisalPeriod, on_delete=models.PROTECT, related_name="submissions")
    policy = models.ForeignKey(
        AppraisalPolicy,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submissions",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    total_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    faculty_statement = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("faculty", "period")
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.faculty} ? {self.period}"


class Review(models.Model):
    submission = models.ForeignKey(AppraisalSubmission, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appraisal_reviews")
    decision = models.CharField(max_length=20, choices=[("UNDER_REVIEW", "Under review"), ("REVISION", "Revision requested"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")])
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=300)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

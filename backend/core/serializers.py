from django.contrib.auth import get_user_model, password_validation
from django.urls import reverse
from urllib.parse import urlparse, parse_qs
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Activity, EvidenceDocument, AppraisalPeriod, AppraisalSubmission, Review, Notification, AppraisalCriterion, AppraisalPolicy, ActivityRevision

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "employee_code", "department", "designation", "phone", "orcid_id", "google_scholar_url"]
        read_only_fields = ["id", "role", "employee_code", "department", "designation"]

    def validate_google_scholar_url(self, value):
        if not value:
            return value
        parsed = urlparse(value)
        if (parsed.scheme != "https" or parsed.hostname != "scholar.google.com"
                or parsed.path.rstrip("/") != "/citations" or not parse_qs(parsed.query).get("user")):
            raise serializers.ValidationError(
                "Enter your public Google Scholar profile URL (https://scholar.google.com/citations?user=...)."
            )
        return value

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=12)
    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password", "employee_code", "department", "designation", "phone", "orcid_id"]
    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, role="FACULTY", **validated_data)

class StrongTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        validated = super().validate(attrs)
        if not self.user.email_verified:
            raise serializers.ValidationError(
                {"detail": "Verify your email address before signing in."}
            )
        return validated


class EvidenceSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceDocument
        fields = ["id", "file", "original_name", "uploaded_at"]
        read_only_fields = ["id", "original_name", "uploaded_at"]

    def get_file(self, obj):
        path = reverse("evidence-download", kwargs={"evidence_id": obj.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path



class ActivityRevisionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True)

    class Meta:
        model = ActivityRevision
        fields = ["id", "activity_id", "revision_number", "event_type", "snapshot", "actor", "actor_name", "created_at"]
        read_only_fields = ["id", "activity_id", "revision_number", "event_type", "snapshot", "actor", "actor_name", "created_at"]

class ActivitySerializer(serializers.ModelSerializer):
    evidence = EvidenceSerializer(many=True, read_only=True)
    faculty_name = serializers.CharField(source="faculty.get_full_name", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    class Meta:
        model = Activity
        fields = ["id", "faculty", "faculty_name", "category", "category_label", "title", "description", "activity_date", "end_date", "organizer", "role_or_level", "authors", "journal_or_venue", "doi", "amount", "source", "verification_status", "reviewer_note", "evidence", "created_at"]
        read_only_fields = ["faculty", "verification_status", "reviewer_note", "source", "created_at"]

class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppraisalPeriod
        fields = "__all__"

class CriterionSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    class Meta:
        model = AppraisalCriterion
        fields = ["id", "category", "category_label", "points_per_item", "description", "is_enabled"]

class AppraisalPolicySerializer(serializers.ModelSerializer):
    rules = serializers.JSONField(required=False)

    class Meta:
        model = AppraisalPolicy
        fields = ["id", "period", "version", "rules", "status", "approved_by", "approved_at", "created_at"]
        read_only_fields = ["id", "status", "approved_by", "approved_at", "created_at"]

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            ) from error

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            ) from error

class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.get_full_name", read_only=True)
    class Meta:
        model = Review
        fields = ["id", "reviewer_name", "decision", "comments", "created_at"]
        read_only_fields = ["id", "reviewer_name", "created_at"]

class SubmissionSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.get_full_name", read_only=True)
    employee_code = serializers.CharField(source="faculty.employee_code", read_only=True)
    department = serializers.CharField(source="faculty.department", read_only=True)
    designation = serializers.CharField(source="faculty.designation", read_only=True)
    period_name = serializers.CharField(source="period.name", read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    class Meta:
        model = AppraisalSubmission
        fields = ["id", "faculty", "faculty_name", "employee_code", "department", "designation", "period", "period_name", "policy", "status", "total_score", "faculty_statement", "submitted_at", "updated_at", "reviews"]
        read_only_fields = ["faculty", "status", "total_score", "submitted_at", "updated_at"]

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "message", "is_read", "created_at"]

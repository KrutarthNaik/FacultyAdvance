from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Activity, EvidenceDocument, AppraisalPeriod, AppraisalCriterion, AppraisalSubmission, Review, Notification, AppraisalPolicy, AuditEvent, ActivityRevision, OrcidOAuthState
from .services import record_audit_event

@admin.register(User)
class FacultyUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Faculty information", {"fields": ("role", "employee_code", "department", "designation", "phone", "orcid_id")}),)
    fieldsets = fieldsets + (("Account verification", {"fields": ("email_verified",)}),)
    list_display = ("username", "email", "first_name", "last_name", "role", "employee_code", "department", "email_verified")
    list_filter = ("role", "department", "email_verified")

    def save_model(self, request, obj, form, change):
        changed_fields = sorted(form.changed_data)
        super().save_model(request, obj, form, change)
        record_audit_event(
            actor=request.user,
            event_type="account_provisioned" if not change else "account_updated",
            instance=obj,
            details={"changed_fields": changed_fields},
        )

class EvidenceInline(admin.TabularInline):
    model = EvidenceDocument
    extra = 0

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "faculty", "category", "activity_date", "verification_status")
    list_filter = ("category", "verification_status", "faculty__department")
    search_fields = ("title", "doi", "faculty__username", "faculty__employee_code")
    inlines = [EvidenceInline]

@admin.register(AppraisalPeriod)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)

@admin.register(AppraisalCriterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = ("category", "points_per_item", "is_enabled")
    readonly_fields = ("category", "points_per_item", "description", "is_enabled")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(AppraisalPolicy)
class AppraisalPolicyAdmin(admin.ModelAdmin):
    list_display = ("period", "version", "status", "approved_by", "approved_at")
    list_filter = ("status", "period")
    readonly_fields = ("approved_by", "approved_at", "created_at")

    def save_model(self, request, obj, form, change):
        was_approved = change and AppraisalPolicy.objects.get(pk=obj.pk).status == AppraisalPolicy.Status.APPROVED
        if obj.status == AppraisalPolicy.Status.APPROVED and obj.approved_by_id is None:
            obj.approved_by = request.user
            from django.utils import timezone
            obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)
        record_audit_event(
            actor=request.user,
            event_type="appraisal_policy_updated" if change else "appraisal_policy_created",
            instance=obj,
            details={"period_id": obj.period_id, "version": obj.version, "approved": obj.status == AppraisalPolicy.Status.APPROVED and not was_approved},
        )

@admin.register(AppraisalSubmission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("faculty", "period", "status", "total_score", "submitted_at")
    list_filter = ("status", "period", "faculty__department")
    search_fields = ("faculty__username", "faculty__employee_code")

admin.site.register(Review)
admin.site.register(Notification)

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "actor", "event_type", "object_type", "object_id")
    list_filter = ("event_type", "object_type", "created_at")
    search_fields = ("object_id", "entry_hash")
    readonly_fields = ("created_at", "actor", "event_type", "object_type", "object_id", "details", "previous_hash", "entry_hash")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActivityRevision)
class ActivityRevisionAdmin(admin.ModelAdmin):
    list_display = ("activity_id", "revision_number", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("event_type",)
    readonly_fields = ("activity_id", "revision_number", "event_type", "snapshot", "actor", "created_at")


@admin.register(OrcidOAuthState)
class OrcidOAuthStateAdmin(admin.ModelAdmin):
    list_display = ("user", "state_hash", "expires_at", "consumed_at")
    readonly_fields = ("user", "state_hash", "expires_at", "consumed_at", "created_at")

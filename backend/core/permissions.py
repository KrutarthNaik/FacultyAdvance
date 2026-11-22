from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or request.user.role == "ADMIN"))

class IsReviewerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or request.user.role in ("HOD", "ADMIN")))

class IsFacultyOwnerOrReviewer(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.role == "ADMIN":
            return True
        if request.user.role == "HOD":
            faculty = getattr(obj, "faculty", None)
            return bool(faculty and faculty.department == request.user.department)
        return getattr(obj, "faculty_id", None) == request.user.id

class IsActivityOwnerOrAdmin(BasePermission):
    """Faculty may edit their own records; only admins may edit other people's records."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user.is_superuser
            or request.user.role == "ADMIN"
            or obj.faculty_id == request.user.id
        )

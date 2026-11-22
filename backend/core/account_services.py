import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User

logger = logging.getLogger(__name__)


password_reset_tokens = PasswordResetTokenGenerator()


def send_email_verification(user):
    token = signing.dumps(
        {"user_id": user.pk, "email": user.email},
        salt="facultyadvance.email-verification",
    )
    link = f"{settings.EMAIL_VERIFICATION_FRONTEND_URL}?token={token}"
    send_mail(
        "Verify your FacultyAdvance email",
        f"Confirm your email address by opening this link:\n\n{link}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_password_reset(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_reset_tokens.make_token(user)
    link = f"{settings.PASSWORD_RESET_FRONTEND_URL}?uid={uid}&token={token}"
    send_mail(
        "Reset your FacultyAdvance password",
        f"Reset your password by opening this link:\n\n{link}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def verify_email_token(token):
    payload = signing.loads(
        token,
        salt="facultyadvance.email-verification",
        max_age=settings.ACCOUNT_TOKEN_MAX_AGE,
    )
    user = User.objects.get(pk=payload["user_id"], email=payload["email"])
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    return user


def reset_user_password(*, uid, token, password):
    user_id = force_str(urlsafe_base64_decode(uid))
    user = User.objects.get(pk=user_id, is_active=True)
    if not password_reset_tokens.check_token(user, token):
        return None
    user.set_password(password)
    user.save(update_fields=["password"])
    return user


def send_alert_email(user, *, subject, message):
    if not getattr(settings, "EMAIL_ALERTS_ENABLED", True):
        return False
    if not user or not getattr(user, "email", None):
        return False
    try:
        return bool(send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True))
    except Exception:
        logger.exception("Workflow email delivery failed for user id %s.", getattr(user, "pk", None))
        return False

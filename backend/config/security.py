from django.core.exceptions import ImproperlyConfigured


DEVELOPMENT_SECRET_KEY = "dev-only-change-this-secret-key"


def validate_secret_key(secret_key, debug):
    if not secret_key or (
        not debug
        and (secret_key == DEVELOPMENT_SECRET_KEY or len(secret_key) < 50)
    ):
        raise ImproperlyConfigured(
            "When DEBUG is disabled, configure a non-development SECRET_KEY "
            "with at least 50 characters."
        )
    return secret_key

from django.core.exceptions import ImproperlyConfigured


CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


def build_email_config(
    *,
    debug,
    backend="",
    host="",
    port=25,
    username="",
    password="",
    use_tls=False,
    use_ssl=False,
    default_from_email="",
):
    backend = backend or (CONSOLE_EMAIL_BACKEND if debug else "")
    if not backend:
        raise ImproperlyConfigured(
            "EMAIL_BACKEND must be explicitly configured when DEBUG is disabled."
        )
    if not debug and backend == CONSOLE_EMAIL_BACKEND:
        raise ImproperlyConfigured(
            "The console email backend cannot be used when DEBUG is disabled."
        )
    if not debug and not default_from_email:
        raise ImproperlyConfigured(
            "DEFAULT_FROM_EMAIL must be explicitly configured when DEBUG is disabled."
        )
    if use_tls and use_ssl:
        raise ImproperlyConfigured("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.")
    if backend == "django.core.mail.backends.smtp.EmailBackend":
        if not host:
            raise ImproperlyConfigured("EMAIL_HOST is required when using Django's SMTP email backend.")
        if not 1 <= port <= 65535:
            raise ImproperlyConfigured("EMAIL_PORT must be between 1 and 65535.")
        if bool(username) != bool(password):
            raise ImproperlyConfigured("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set together.")

    return {
        "EMAIL_BACKEND": backend,
        "EMAIL_HOST": host,
        "EMAIL_PORT": port,
        "EMAIL_HOST_USER": username,
        "EMAIL_HOST_PASSWORD": password,
        "EMAIL_USE_TLS": use_tls,
        "EMAIL_USE_SSL": use_ssl,
        "DEFAULT_FROM_EMAIL": default_from_email or "webmaster@localhost",
    }

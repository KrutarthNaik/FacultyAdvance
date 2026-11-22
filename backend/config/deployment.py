from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlsplit


def build_deployment_security(*, debug, allowed_hosts, cors_origins, trust_proxy=False):
    if not debug:
        if not allowed_hosts:
            raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG is disabled.")
        if not cors_origins or any(not origin.startswith("https://") for origin in cors_origins):
            raise ImproperlyConfigured(
                "Production FRONTEND_ORIGIN values must use HTTPS."
            )

    return {
        "SECURE_SSL_REDIRECT": not debug,
        "SESSION_COOKIE_SECURE": not debug,
        "CSRF_COOKIE_SECURE": not debug,
        "SECURE_HSTS_SECONDS": 31_536_000 if not debug else 0,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
        "SECURE_HSTS_PRELOAD": False,
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "SECURE_REFERRER_POLICY": "strict-origin-when-cross-origin",
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https") if trust_proxy else None,
    }


def validate_vercel_runtime(*, debug, trust_proxy, redis_url):
    if debug:
        raise ImproperlyConfigured("DEBUG=True is not supported on Vercel; deploy with DEBUG=False.")
    if not trust_proxy:
        raise ImproperlyConfigured(
            "TRUST_PROXY_SSL_HEADER=True is required on Vercel to recognize HTTPS at the platform proxy."
        )
    if urlsplit(redis_url).scheme != "rediss":
        raise ImproperlyConfigured(
            "Vercel production requires a TLS Redis URL using the rediss:// scheme."
        )

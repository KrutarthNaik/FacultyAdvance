from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


_SUPPORTED_QUERY_OPTIONS = {
    "application_name",
    "connect_timeout",
    "sslcert",
    "sslkey",
    "sslmode",
    "sslrootcert",
}
_SUPPORTED_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}


def build_database_config(database_url, sqlite_path, debug, conn_max_age=0):
    if conn_max_age < 0:
        raise ImproperlyConfigured("DATABASE_CONN_MAX_AGE cannot be negative.")
    if not database_url:
        if not debug:
            raise ImproperlyConfigured(
                "DATABASE_URL must configure PostgreSQL when DEBUG is disabled."
            )
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(sqlite_path),
        }

    return _postgres_config(database_url, conn_max_age, debug)


def _postgres_config(database_url, conn_max_age, debug):
    try:
        parsed = urlsplit(database_url)
        port = parsed.port
    except ValueError:
        raise ImproperlyConfigured(
            "DATABASE_URL is not a valid PostgreSQL connection URL."
        ) from None

    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "DATABASE_URL must use the postgres or postgresql scheme."
        )
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ImproperlyConfigured(
            "DATABASE_URL must include a database name and hostname."
        )

    query = parse_qs(parsed.query, keep_blank_values=True)
    unsupported_options = set(query) - _SUPPORTED_QUERY_OPTIONS
    if unsupported_options:
        raise ImproperlyConfigured(
            "DATABASE_URL contains unsupported query options: "
            + ", ".join(sorted(unsupported_options))
        )
    if any(len(values) != 1 for values in query.values()):
        raise ImproperlyConfigured("DATABASE_URL query options cannot be repeated.")

    options = {name: values[0] for name, values in query.items()}
    if options.get("sslmode") and options["sslmode"] not in _SUPPORTED_SSL_MODES:
        raise ImproperlyConfigured("DATABASE_URL has an unsupported sslmode.")
    if not debug and options.get("sslmode") != "verify-full":
        raise ImproperlyConfigured(
            "Production DATABASE_URL must explicitly set sslmode=verify-full."
        )
    if "connect_timeout" in options:
        try:
            timeout = int(options["connect_timeout"])
        except ValueError:
            raise ImproperlyConfigured(
                "DATABASE_URL connect_timeout must be a positive integer."
            ) from None
        if timeout < 1:
            raise ImproperlyConfigured(
                "DATABASE_URL connect_timeout must be a positive integer."
            )
        options["connect_timeout"] = timeout

    database_config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(port or ""),
        "CONN_MAX_AGE": conn_max_age,
    }
    if options:
        database_config["OPTIONS"] = options
    return database_config

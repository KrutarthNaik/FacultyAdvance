import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StrongPasswordValidator:
    def validate(self, password, user=None):
        if len(password) < 12:
            raise ValidationError(_("Password must contain at least 12 characters."))
        groups = (
            bool(re.search(r"[a-z]", password)),
            bool(re.search(r"[A-Z]", password)),
            bool(re.search(r"\d", password)),
            bool(re.search(r"[^A-Za-z0-9]", password)),
        )
        if sum(groups) < 3:
            raise ValidationError(
                _("Use at least three of lowercase letters, uppercase letters, digits, and symbols.")
            )

    def get_help_text(self):
        return _("Use at least 12 characters and three character classes.")

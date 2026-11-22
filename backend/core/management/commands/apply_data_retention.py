from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Notification
from core.services import record_audit_event


class Command(BaseCommand):
    help = "Report or remove read notifications older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete eligible read notifications. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options):
        retention_days = settings.NOTIFICATION_RETENTION_DAYS
        if retention_days <= 0:
            raise CommandError(
                "Set NOTIFICATION_RETENTION_DAYS to a positive institution-approved value before running retention."
            )
        cutoff = timezone.now() - timedelta(days=retention_days)
        eligible = Notification.objects.filter(is_read=True, created_at__lt=cutoff)
        count = eligible.count()
        if options["apply"]:
            with transaction.atomic():
                for notification in eligible.iterator():
                    record_audit_event(
                        actor=None,
                        event_type="notification_retention_applied",
                        instance=notification,
                        details={"retention_days": retention_days},
                    )
                eligible.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {count} read notification(s) older than {retention_days} days."
                )
            )
        else:
            self.stdout.write(
                f"Dry run: {count} read notification(s) would be deleted; rerun with --apply to confirm."
            )

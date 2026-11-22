from itertools import zip_longest

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


_REGENERATED_OR_EPHEMERAL_MODELS = {
    "admin.logentry",
    "auth.permission",
    "contenttypes.contenttype",
    "sessions.session",
}


def _key_relationship_rows(model, alias):
    foreign_key_fields = [
        field.attname
        for field in model._meta.concrete_fields
        if field.is_relation and (field.many_to_one or field.one_to_one)
    ]
    field_names = ["pk", *foreign_key_fields]
    queryset = (
        model._base_manager.using(alias)
        .values_list(*field_names)
        .order_by("pk")
    )
    return queryset.iterator(chunk_size=2000)


def _matches_keys_and_relationships(model, source_alias, target_alias):
    sentinel = object()
    source_rows = _key_relationship_rows(model, source_alias)
    target_rows = _key_relationship_rows(model, target_alias)
    return all(
        source_row == target_row
        for source_row, target_row in zip_longest(
            source_rows, target_rows, fillvalue=sentinel
        )
    )


class Command(BaseCommand):
    help = (
        "Read-only comparison of model row counts and database constraints "
        "between a source and target database."
    )

    def add_arguments(self, parser):
        parser.add_argument("--source-alias", default="migration_source")
        parser.add_argument("--target-alias", default="default")

    def handle(self, *args, **options):
        source_alias = options["source_alias"]
        target_alias = options["target_alias"]
        missing_aliases = {
            alias
            for alias in (source_alias, target_alias)
            if alias not in connections.databases
        }
        if missing_aliases:
            raise CommandError(
                "Database alias is not configured: " + ", ".join(sorted(missing_aliases))
            )

        models = [
            model
            for model in apps.get_models(include_auto_created=True)
            if model._meta.managed
            and model._meta.label_lower not in _REGENERATED_OR_EPHEMERAL_MODELS
        ]
        try:
            for model in models:
                source_count = model._base_manager.using(source_alias).count()
                target_count = model._base_manager.using(target_alias).count()
                if source_count != target_count:
                    raise CommandError(
                        f"Row-count mismatch for {model._meta.label_lower}: "
                        f"source={source_count}, target={target_count}."
                    )
                if not _matches_keys_and_relationships(
                    model, source_alias, target_alias
                ):
                    raise CommandError(
                        f"Primary-key or relationship mismatch for "
                        f"{model._meta.label_lower}."
                    )

            for alias in {source_alias, target_alias}:
                connections[alias].check_constraints()
        except CommandError:
            raise
        except Exception:
            raise CommandError(
                "Database comparison or constraint validation failed; "
                "details are suppressed to avoid exposing record data."
            ) from None

        self.stdout.write(
            self.style.SUCCESS(
                f"Matched row counts for {len(models)} models; "
                "source and target constraints passed."
            )
        )

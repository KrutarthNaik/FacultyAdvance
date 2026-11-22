import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from .models import Activity, ActivityRevision, AppraisalPolicy, AuditEvent


def record_activity_revision(*, activity, actor=None, event_type, snapshot=None):
    revision_number = ActivityRevision.objects.filter(activity_id=activity.pk).count() + 1
    payload = snapshot or {
        field: getattr(activity, field)
        for field in [
            "id", "faculty_id", "category", "title", "description", "activity_date", "end_date",
            "organizer", "role_or_level", "authors", "journal_or_venue", "doi", "amount",
            "source", "verification_status", "reviewer_note", "created_at", "updated_at",
        ]
    }
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    return ActivityRevision.objects.create(
        activity_id=activity.pk,
        revision_number=revision_number,
        event_type=event_type,
        snapshot=payload,
        actor=actor,
    )


def scan_uploaded_file(file_obj):
    scanner = getattr(settings, "MALWARE_SCANNER", "disabled").strip().lower()
    if scanner in {"", "disabled", "off", "none"}:
        return True

    file_obj.seek(0)
    payload = file_obj.read()
    file_obj.seek(0)
    if scanner == "clamd":
        host = getattr(settings, "CLAMD_HOST", "127.0.0.1")
        port = getattr(settings, "CLAMD_PORT", 3310)
        timeout = getattr(settings, "CLAMD_TIMEOUT", 5)
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                sock.sendall(b"zPING\0")
                try:
                    ping = sock.recv(4096)
                except socket.timeout as exc:
                    raise RuntimeError("Clamd did not respond to a ping request.") from exc
                if b"PONG" not in ping and b"OK" not in ping:
                    raise RuntimeError("Clamd did not return a valid ping response.")
                sock.sendall(b"nINSTREAM\0")
                for start in range(0, len(payload), 1024):
                    chunk = payload[start:start + 1024]
                    sock.sendall(len(chunk).to_bytes(4, byteorder="big", signed=False) + chunk)
                sock.sendall(b"\x00\x00\x00\x00")
                response = b""
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    response += chunk
                    normalized_response = response.rstrip(b"\x00")
                    if (normalized_response.endswith(b"OK") or b"FOUND" in normalized_response
                            or b"ERROR" in normalized_response):
                        break
        except OSError as exc:
            raise RuntimeError("Clamd scan service is not reachable.") from exc
        text = response.decode("utf-8", errors="replace").upper()
        if "FOUND" in text:
            return False
        if "ERROR" in text:
            raise RuntimeError("Clamd scan reported an error.")
        if text.rstrip("\x00").endswith("OK"):
            return True
        raise RuntimeError("Clamd returned an unexpected scan response.")

    if scanner in {"clamscan", "clamav"}:
        binary = shutil.which("clamscan") or shutil.which("clamdscan")
        if binary is None:
            raise RuntimeError("No ClamAV client is installed or available on PATH.")
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(payload)
            temp_path = handle.name
        try:
            result = subprocess.run(
                [binary, "--no-summary", "--infected", temp_path],
                capture_output=True,
                text=True,
                timeout=getattr(settings, "CLAMD_TIMEOUT", 5),
            )
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise RuntimeError("ClamAV scan reported an error.")

    raise RuntimeError(f"Unsupported malware scanner configuration: {scanner}")


import hashlib
import json
from decimal import Decimal
from django.db import connection, transaction
from django.utils import timezone
from .models import Activity, AppraisalPolicy, AuditEvent


def calculate_appraisal(faculty, period=None, policy=None):
    if period is not None and policy is None:
        policy = AppraisalPolicy.objects.filter(
            period=period, status=AppraisalPolicy.Status.APPROVED
        ).order_by("-version").first()
    activity_qs = Activity.objects.filter(faculty=faculty, verification_status="VERIFIED")
    if period is not None:
        activity_qs = activity_qs.filter(activity_date__gte=period.start_date, activity_date__lte=period.end_date)
    rows = []
    total = Decimal("0")
    for category, label in Activity.Category.choices:
        count = activity_qs.filter(category=category).count()
        rule = policy.rules.get(category, {}) if policy else {}
        points = Decimal(str(rule.get("points_per_item", 0)))
        subtotal = points * count
        cap = rule.get("max_points")
        if cap is not None:
            subtotal = min(subtotal, Decimal(str(cap)))
        total += subtotal
        rows.append({"category": category, "label": label, "verified_count": count, "points_per_item": str(points), "subtotal": str(subtotal)})
    return {
        "total_score": str(total),
        "breakdown": rows,
        "policy": {
            "configured": policy is not None,
            "name": policy.period.name if policy else None,
            "version": policy.version if policy else None,
        },
        "note": (
            "Only verified activities are included under the approved period-specific appraisal policy."
            if policy
            else "No approved appraisal policy is configured for this period. Scores are unavailable until an administrator approves a policy."
        ),
    }


@transaction.atomic
def record_audit_event(*, actor, event_type, instance, details=None):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [731942018])
    previous = AuditEvent.objects.select_for_update().order_by("-id").first()
    previous_hash = previous.entry_hash if previous else ""
    created_at = timezone.now()
    payload = {
        "actor_id": actor.pk if actor else None,
        "event_type": event_type,
        "object_type": instance._meta.label,
        "object_id": str(instance.pk),
        "details": details or {},
        "previous_hash": previous_hash,
        "created_at": created_at.isoformat(),
    }
    entry_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return AuditEvent.objects.create(
        actor=actor,
        event_type=event_type,
        object_type=instance._meta.label,
        object_id=str(instance.pk),
        details=details or {},
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )


def verify_audit_chain():
    previous_hash = ""
    for event in AuditEvent.objects.order_by("id").iterator():
        payload = {
            "actor_id": event.actor_id,
            "event_type": event.event_type,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "details": event.details,
            "previous_hash": previous_hash,
            "created_at": event.created_at.isoformat(),
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        if event.previous_hash != previous_hash or event.entry_hash != expected:
            return False
        previous_hash = event.entry_hash
    return True

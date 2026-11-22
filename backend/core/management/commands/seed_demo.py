from datetime import date
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import AppraisalPeriod, AppraisalCriterion, Activity, AppraisalPolicy

class Command(BaseCommand):
    help = "Create demo faculty, HOD, administrator, appraisal period and illustrative criteria."
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo users and illustrative appraisal rules may only be created when DEBUG=True.")
        User = get_user_model()
        admin, _ = User.objects.get_or_create(username="universityadmin", defaults={"email":"admin@example.com", "first_name":"University", "last_name":"Admin", "role":"ADMIN", "is_staff":True})
        admin.role="ADMIN"; admin.is_staff=True; admin.email_verified=True; admin.set_password("Admin@12345"); admin.save()
        hod, _ = User.objects.get_or_create(username="hod", defaults={"email":"hod@example.com", "first_name":"Department", "last_name":"HOD", "role":"HOD", "department":"Computer Engineering", "employee_code":"HOD001"})
        hod.role="HOD"; hod.department="Computer Engineering"; hod.email_verified=True; hod.set_password("Hod@12345"); hod.save()
        faculty, _ = User.objects.get_or_create(username="faculty", defaults={"email":"faculty@example.com", "first_name":"Aarav", "last_name":"Shah", "role":"FACULTY", "department":"Computer Engineering", "designation":"Assistant Professor", "employee_code":"FAC001"})
        faculty.role="FACULTY"; faculty.department="Computer Engineering"; faculty.email_verified=True; faculty.set_password("Faculty@12345"); faculty.save()
        period, _ = AppraisalPeriod.objects.get_or_create(name="Academic Year 2026-27", defaults={"start_date":date(2026,4,1), "end_date":date(2027,3,31), "is_active":True})
        period.is_active=True; period.save()
        points = {"PUBLICATION":10,"BOOK":12,"SEMINAR":2,"FDP":3,"PROJECT":15,"TEACHING":1,"PATENT":15,"AWARD":5,"SERVICE":2,"OTHER":1}
        for category, value in points.items():
            AppraisalCriterion.objects.get_or_create(category=category, defaults={"points_per_item":value, "description":"Illustrative demo value; replace with approved university criteria."})
        AppraisalPolicy.objects.get_or_create(
            period=period,
            version=1,
            defaults={
                "rules": {
                    category: {"points_per_item": value, "max_points": None}
                    for category, value in points.items()
                },
                "status": AppraisalPolicy.Status.APPROVED,
                "approved_by": admin,
                "approved_at": timezone.now(),
            },
        )
        if not faculty.activities.exists():
            Activity.objects.create(faculty=faculty, category="PUBLICATION", title="A Survey of Responsible AI in Education", authors="Aarav Shah, Demo Co-author", journal_or_venue="Demo Journal", doi="10.0000/demo.2026.001", activity_date=date(2026,7,15), verification_status="VERIFIED")
            Activity.objects.create(faculty=faculty, category="FDP", title="Faculty Development Programme on AI", organizer="Demo University", activity_date=date(2026,8,10), verification_status="PENDING")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("Faculty: faculty / Faculty@12345 | HOD: hod / Hod@12345 | Admin: universityadmin / Admin@12345")

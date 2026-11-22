from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_googlessologinticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='google_scholar_url',
            field=models.URLField(blank=True, max_length=500),
        ),
    ]

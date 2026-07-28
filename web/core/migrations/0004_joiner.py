import django.contrib.auth.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0003_material_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="Joiner",
            fields=[],
            options={
                "verbose_name": "joiner",
                "verbose_name_plural": "joiners",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("auth.user",),
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
    ]

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quiz",
            name="pass_mark",
            field=models.PositiveIntegerField(
                default=80, validators=[django.core.validators.MaxValueValidator(100)]
            ),
        ),
    ]

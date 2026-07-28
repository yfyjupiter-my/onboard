from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_quiz_pass_mark"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="url",
            field=models.URLField(blank=True),
        ),
        migrations.AlterField(
            model_name="material",
            name="file",
            field=models.FileField(blank=True, upload_to="materials/"),
        ),
        migrations.AlterField(
            model_name="material",
            name="type",
            field=models.CharField(
                choices=[("pdf", "PDF"), ("video", "Video"), ("link", "Link")],
                max_length=5,
            ),
        ),
    ]

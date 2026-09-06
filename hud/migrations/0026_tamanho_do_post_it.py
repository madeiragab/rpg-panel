from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0025_ouvintes_do_audio"),
    ]

    operations = [
        migrations.AddField(
            model_name="stickynote",
            name="width",
            field=models.PositiveSmallIntegerField(default=180),
        ),
        migrations.AddField(
            model_name="stickynote",
            name="height",
            field=models.PositiveSmallIntegerField(default=118),
        ),
    ]

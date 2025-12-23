from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0006_userprofile_avatar_userprofile_display_name_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="description",
            field=models.TextField(blank=True),
        ),
    ]

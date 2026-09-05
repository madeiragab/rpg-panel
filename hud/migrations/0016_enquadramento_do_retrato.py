from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0015_playback_para_campanhas_antigas"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="image_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="character",
            name="image_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="character",
            name="image_focus_y",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="npc",
            name="image_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="npc",
            name="image_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="npc",
            name="image_focus_y",
            field=models.FloatField(default=0.5),
        ),
    ]

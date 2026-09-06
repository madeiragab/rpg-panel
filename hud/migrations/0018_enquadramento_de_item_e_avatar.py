from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0017_fichas_de_inimigo"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="image_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="item",
            name="image_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="item",
            name="image_focus_y",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="image_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="image_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="image_focus_y",
            field=models.FloatField(default=0.5),
        ),
    ]

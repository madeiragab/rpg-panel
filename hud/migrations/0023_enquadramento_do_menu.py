from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0022_descricao_da_habilidade"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="card_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="character",
            name="card_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="character",
            name="card_focus_y",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="npc",
            name="card_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="npc",
            name="card_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="npc",
            name="card_focus_y",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="enemy",
            name="card_zoom",
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="enemy",
            name="card_focus_x",
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name="enemy",
            name="card_focus_y",
            field=models.FloatField(default=0.5),
        ),
    ]

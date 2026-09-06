from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0021_habilidade_com_campos"),
    ]

    operations = [
        migrations.AddField(
            model_name="characterability",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="npcability",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="enemyability",
            name="description",
            field=models.TextField(blank=True),
        ),
    ]

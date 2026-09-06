from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0020_post_it_no_quadro"),
    ]

    operations = [
        migrations.AddField(
            model_name="characterability",
            name="damage",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="characterability",
            name="extras",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="npcability",
            name="damage",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="npcability",
            name="extras",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="enemyability",
            name="damage",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="enemyability",
            name="extras",
            field=models.JSONField(blank=True, default=list),
        ),
    ]

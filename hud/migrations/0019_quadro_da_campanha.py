import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hud", "0018_enquadramento_de_item_e_avatar"),
    ]

    operations = [
        migrations.AddField(
            model_name="character",
            name="board_x",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="character",
            name="board_y",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="npc",
            name="board_x",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="npc",
            name="board_y",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="enemy",
            name="board_x",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="enemy",
            name="board_y",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Polaroid",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image_zoom", models.PositiveSmallIntegerField(default=100)),
                ("image_focus_x", models.FloatField(default=0.5)),
                ("image_focus_y", models.FloatField(default=0.5)),
                ("board_x", models.FloatField(blank=True, null=True)),
                ("board_y", models.FloatField(blank=True, null=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to="polaroids/")),
                ("caption", models.CharField(blank=True, max_length=120)),
                ("tilt", models.SmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="polaroids",
                        to="hud.campaign",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="polaroids",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
    ]

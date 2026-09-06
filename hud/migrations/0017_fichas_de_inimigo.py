import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hud", "0016_enquadramento_do_retrato"),
    ]

    operations = [
        migrations.CreateModel(
            name="Enemy",
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
                ("name", models.CharField(max_length=120)),
                ("image", models.ImageField(blank=True, null=True, upload_to="enemies/")),
                ("visible", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enemies",
                        to="hud.campaign",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_enemies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="EnemyAbility",
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
                ("name", models.CharField(max_length=80)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "enemy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="abilities",
                        to="hud.enemy",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="EnemyAttribute",
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
                ("name", models.CharField(max_length=80)),
                ("value", models.CharField(max_length=40)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "enemy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attributes",
                        to="hud.enemy",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="EnemyBar",
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
                ("name", models.CharField(max_length=80)),
                ("current", models.IntegerField(default=0)),
                ("max_value", models.IntegerField(default=100)),
                ("color", models.CharField(default="#e11d2e", max_length=20)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "enemy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bars",
                        to="hud.enemy",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="EnemySkill",
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
                ("name", models.CharField(max_length=80)),
                ("value", models.CharField(blank=True, max_length=40)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "enemy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="skills",
                        to="hud.enemy",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
    ]

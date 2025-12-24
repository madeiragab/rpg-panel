from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0009_alter_npc_visible"),
    ]

    operations = [
        migrations.CreateModel(
            name="NPCSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("value", models.CharField(blank=True, max_length=40)),
                ("order", models.PositiveIntegerField(default=0)),
                ("npc", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skills", to="hud.npc")),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="NPCBar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("current", models.IntegerField(default=0)),
                ("max_value", models.IntegerField(default=100)),
                ("color", models.CharField(default="#ff4444", max_length=20)),
                ("order", models.PositiveIntegerField(default=0)),
                ("npc", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bars", to="hud.npc")),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="NPCAbility",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("order", models.PositiveIntegerField(default=0)),
                ("npc", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="abilities", to="hud.npc")),
            ],
            options={
                "ordering": ["order", "name"],
            },
        ),
    ]

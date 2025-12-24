from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hud", "0007_item_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="NPC",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("image", models.ImageField(blank=True, null=True, upload_to="npcs/")),
                ("hp_max", models.PositiveIntegerField(default=10)),
                ("hp_current", models.PositiveIntegerField(default=10)),
                ("sp_max", models.PositiveIntegerField(default=10)),
                ("sp_current", models.PositiveIntegerField(default=10)),
                ("inventory_capacity", models.PositiveIntegerField(default=16)),
                ("visible", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to_character", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="npcs", to="hud.character")),
                ("campaign", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="npcs", to="hud.campaign")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="created_npcs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="NPCInventorySlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField()),
                ("item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="npc_slots", to="hud.item")),
                ("npc", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="slots", to="hud.npc")),
            ],
            options={
                "ordering": ["position"],
                "unique_together": {("npc", "position")},
            },
        ),
    ]

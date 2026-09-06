import django.db.models.deletion
from django.db import migrations, models


def criar(nome, dono, para):
    return migrations.CreateModel(
        name=nome,
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
            ("damage", models.CharField(blank=True, max_length=60)),
            ("description", models.TextField(blank=True)),
            ("extras", models.JSONField(blank=True, default=list)),
            ("order", models.PositiveIntegerField(default=0)),
            (
                dono,
                models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="attacks",
                    to=para,
                ),
            ),
        ],
        options={"ordering": ["order", "name"], "abstract": False},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0023_enquadramento_do_menu"),
    ]

    operations = [
        criar("CharacterAttack", "character", "hud.character"),
        criar("NPCAttack", "npc", "hud.npc"),
        criar("EnemyAttack", "enemy", "hud.enemy"),
    ]

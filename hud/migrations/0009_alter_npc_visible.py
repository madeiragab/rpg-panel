from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0008_npc_npcventoryslot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="npc",
            name="visible",
            field=models.BooleanField(default=False),
        ),
    ]

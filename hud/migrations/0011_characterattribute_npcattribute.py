# Generated migration

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hud', '0010_npcskill_npcbar_npcability'),
    ]

    operations = [
        migrations.CreateModel(
            name='CharacterAttribute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('value', models.CharField(max_length=40)),
                ('order', models.PositiveIntegerField(default=0)),
                ('character', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attributes', to='hud.character')),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='NPCAttribute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('value', models.CharField(max_length=40)),
                ('order', models.PositiveIntegerField(default=0)),
                ('npc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attributes', to='hud.npc')),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
    ]

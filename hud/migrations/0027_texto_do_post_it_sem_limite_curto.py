# O banco não muda: `max_length` num TextField não vira restrição de coluna,
# quem corta é o `save()` do modelo. Esta migração existe para o estado do
# Django bater com o modelo — sem ela, o `makemigrations --check` do CI reprova
# todo commit seguinte por uma pendência que não é dele.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hud', '0026_tamanho_do_post_it'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stickynote',
            name='text',
            field=models.TextField(blank=True, max_length=20000),
        ),
    ]

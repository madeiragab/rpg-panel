from django.db import migrations


def create_default_bars(apps, schema_editor):
    """Cria barras HP e SP para personagens que ainda não têm"""
    Character = apps.get_model('hud', 'Character')
    CharacterBar = apps.get_model('hud', 'CharacterBar')
    
    for character in Character.objects.all():
        # Cria barra HP se tem valores
        if character.hp_max > 0:
            CharacterBar.objects.create(
                character=character,
                name='HP',
                current=character.hp_current,
                max_value=character.hp_max,
                color='#ff4444',
                order=0
            )
        
        # Cria barra SP se tem valores
        if character.sp_max > 0:
            CharacterBar.objects.create(
                character=character,
                name='SP',
                current=character.sp_current,
                max_value=character.sp_max,
                color='#4444ff',
                order=1
            )


class Migration(migrations.Migration):

    dependencies = [
        ('hud', '0009_characterbar'),
    ]

    operations = [
        migrations.RunPython(create_default_bars, reverse_code=migrations.RunPython.noop),
    ]

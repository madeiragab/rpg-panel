from django.db import migrations


def criar_estado_das_campanhas_existentes(apps, schema_editor):
    """O signal só dispara em campanha nova.

    Sem este passo, toda campanha criada antes do player ficaria sem linha de
    estado, e o widget quebraria justamente nas mesas que já estão em uso.
    """
    Campaign = apps.get_model("hud", "Campaign")
    PlaybackState = apps.get_model("hud", "PlaybackState")

    PlaybackState.objects.bulk_create(
        [
            PlaybackState(campaign=campanha)
            for campanha in Campaign.objects.filter(playback__isnull=True)
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0014_audiotrack_playbackstate"),
    ]

    operations = [
        migrations.RunPython(
            criar_estado_das_campanhas_existentes, migrations.RunPython.noop
        ),
    ]

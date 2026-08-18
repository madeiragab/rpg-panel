from django.db import migrations


def apagar_tokens_antigos(apps, schema_editor):
    """Os tokens gravados até aqui estão em texto puro.

    Não dá para convertê-los: o valor guardado é o próprio segredo, e o novo
    formato guarda o hash dele. Como todo token vive 24 horas e serve a um
    pedido em andamento, apagar é mais honesto do que deixar linha que nunca
    mais vai casar com nada. Quem estiver no meio de uma recuperação pede outra.
    """
    apps.get_model("hud", "PasswordResetToken").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hud", "0012_merge_20260805_1221"),
    ]

    operations = [
        migrations.RunPython(apagar_tokens_antigos, migrations.RunPython.noop),
    ]

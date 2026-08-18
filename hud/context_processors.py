from __future__ import annotations

from .models import UserProfile


def user_role(request):
    if not request.user.is_authenticated:
        return {"is_master_user": False, "user_profile": None}

    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"role": UserProfile.ROLE_MASTER if request.user.is_staff else UserProfile.ROLE_PLAYER},
    )
    return {"is_master_user": profile.is_master, "user_profile": profile}


def pusher(request):
    """Chave pública do Pusher para o widget de áudio.

    Só a chave e o cluster: são os dois valores que o navegador precisa para
    assinar o canal, e ambos são públicos por natureza. O segredo fica no
    servidor e é o que impede alguém de publicar evento no canal de uma mesa
    onde não entra.

    Vazias quando o Pusher não está configurado — aí o player cai no polling.
    """
    from django.conf import settings

    return {
        "pusher_key": settings.PUSHER_KEY,
        "pusher_cluster": settings.PUSHER_CLUSTER,
    }

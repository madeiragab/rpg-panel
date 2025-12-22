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

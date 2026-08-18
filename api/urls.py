from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("campaigns", views.CampaignViewSet, basename="campaign")
router.register("characters", views.CharacterViewSet, basename="character")
router.register("npcs", views.NPCViewSet, basename="npc")
router.register("items", views.ItemViewSet, basename="item")

urlpatterns = [
    path("token/", views.TokenPorSenhaView.as_view(), name="api_token"),
    path("token/refresh/", views.RenovarTokenView.as_view(), name="api_token_refresh"),
    path("token/logout/", views.RevogarTokenView.as_view(), name="api_token_logout"),
    path("me/", views.PerfilView.as_view(), name="api_me"),
    path("pusher/auth/", views.PusherAuthView.as_view(), name="api_pusher_auth"),
    path("", include(router.urls)),
]

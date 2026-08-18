"""Views da API.

O escopo é feito no `get_queryset`, não no `has_object_permission`. A diferença
importa: fora do queryset, um id de outra mesa devolve 404 e não conta nada; se o
filtro ficasse só na permissão, o 403 já confirmaria que aquele id existe.

As regras de papel vêm de `api.permissions`, que é o mesmo conjunto que o painel
HTML aplica. A API não tem uma segunda versão delas.
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from hud.models import (
    Campaign,
    Character,
    CharacterBar,
    InventorySlot,
    Item,
    NPC,
    NPCBar,
    NPCInventorySlot,
    UserProfile,
)

from .permissions import (
    campanhas_do_usuario,
    eh_mestre,
    participa,
    pode_editar_npc,
    pode_editar_personagem,
    pode_mexer_status,
    pode_ver_npc,
    pode_ver_personagem,
)
from .serializers import (
    AdicionarJogadorSerializer,
    AtribuirItemSerializer,
    CampaignSerializer,
    CharacterBarSerializer,
    CharacterSerializer,
    CharacterStatusSerializer,
    InventorySlotSerializer,
    ItemSerializer,
    NPCBarSerializer,
    NPCInventorySlotSerializer,
    NPCSerializer,
    PerfilSerializer,
)
from .throttles import ThrottleDeToken


class TokenPorSenhaView(TokenObtainPairView):
    """Troca usuário e senha por um par de tokens.

    É o único endereço da API que aceita senha, então é o único que precisa de
    freio próprio: o resto já exige um access válido para chegar na view.
    """

    throttle_classes = [ThrottleDeToken]


class RenovarTokenView(TokenRefreshView):
    throttle_classes = [ThrottleDeToken]


class RevogarTokenView(TokenBlacklistView):
    """Logout: manda o refresh recebido para a blacklist.

    O access continua valendo até expirar — são 15 minutos, e é o preço de não
    consultar o banco a cada requisição.
    """

    throttle_classes = [ThrottleDeToken]


class PerfilView(RetrieveUpdateAPIView):
    serializer_class = PerfilSerializer

    def get_object(self):
        perfil, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return perfil


# Todas herdam de `IsAuthenticated`, não de `BasePermission`: declarar
# `permission_classes` num viewset substitui o padrão do settings, e com uma
# permissão crua o anônimo passava direto para o `get_queryset` — que tenta
# filtrar por um `AnonymousUser` e devolve 500 onde devia devolver 401.
class PermissaoCampanha(IsAuthenticated):
    def has_object_permission(self, request, view, campanha):
        if request.method in SAFE_METHODS:
            return participa(request.user, campanha)
        return eh_mestre(request.user, campanha)


class CampaignViewSet(viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [PermissaoCampanha]

    def get_queryset(self):
        return campanhas_do_usuario(self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        # Mesmo comportamento do painel: quem cria é o mestre e entra também
        # como jogador, senão o próprio modo jogador o deixaria de fora da mesa.
        campanha = serializer.save(master=self.request.user)
        campanha.players.add(self.request.user)

    @action(detail=True, methods=["post"], url_path="players")
    def adicionar_jogador(self, request, pk=None):
        campanha = self.get_object()
        corpo = AdicionarJogadorSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        usuario = corpo.validated_data["user"]

        if usuario == campanha.master:
            return Response(
                {"detail": "O mestre já está na campanha."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        campanha.players.add(usuario)
        return Response(CampaignSerializer(campanha, context={"request": request}).data)

    @action(detail=True, methods=["delete"], url_path=r"players/(?P<user_pk>[^/.]+)")
    def remover_jogador(self, request, pk=None, user_pk=None):
        campanha = self.get_object()
        jogador = get_object_or_404(campanha.players, pk=user_pk)

        # Sair da mesa não pode deixar a ficha atribuída a quem não está mais
        # nela: o painel desvincula, e aqui é a mesma coisa.
        Character.objects.filter(campaign=campanha, assigned_to=jogador).update(
            assigned_to=None
        )
        campanha.players.remove(jogador)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="leave")
    def sair(self, request, pk=None):
        # Sem `get_object`: sair é coisa de jogador, e o `get_object` cobraria
        # permissão de escrita, que só o mestre tem.
        campanha = get_object_or_404(self.get_queryset(), pk=pk)
        if campanha.master_id == request.user.id:
            return Response(
                {"detail": "O mestre não sai da própria campanha."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        Character.objects.filter(campaign=campanha, assigned_to=request.user).update(
            assigned_to=None
        )
        campanha.players.remove(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissaoPersonagem(IsAuthenticated):
    def has_object_permission(self, request, view, personagem):
        if request.method in SAFE_METHODS:
            return pode_ver_personagem(request.user, personagem)
        if request.method in ("PUT", "PATCH"):
            # O jogador atribuído passa aqui, mas o serializer dele só tem os
            # campos de status — a ficha em si continua sendo do mestre.
            return pode_mexer_status(request.user, personagem)
        return pode_editar_personagem(request.user, personagem)


class CharacterViewSet(viewsets.ModelViewSet):
    permission_classes = [PermissaoPersonagem]

    def get_queryset(self):
        usuario = self.request.user
        minhas = campanhas_do_usuario(usuario)
        return (
            Character.objects.filter(campaign__in=minhas)
            .filter(Q(campaign__master=usuario) | Q(visible=True) | Q(assigned_to=usuario))
            .distinct()
            .order_by("name")
        )

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            personagem = self.get_object()
            if not eh_mestre(self.request.user, personagem.campaign):
                return CharacterStatusSerializer
        return CharacterSerializer

    def perform_create(self, serializer):
        campanha = serializer.validated_data.get("campaign")
        if not eh_mestre(self.request.user, campanha):
            self.permission_denied(
                self.request, message="Só o mestre da campanha cria personagem nela."
            )
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get", "post"], url_path="bars")
    def barras(self, request, pk=None):
        personagem = self.get_object()

        if request.method == "GET":
            return Response(CharacterBarSerializer(personagem.bars.all(), many=True).data)

        if not eh_mestre(request.user, personagem.campaign):
            self.permission_denied(request, message="Só o mestre cria barra.")

        corpo = CharacterBarSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        barra = corpo.save(character=personagem, order=personagem.bars.count())
        return Response(CharacterBarSerializer(barra).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"bars/(?P<bar_pk>[^/.]+)")
    def barra(self, request, pk=None, bar_pk=None):
        personagem = self.get_object()
        barra = get_object_or_404(CharacterBar, pk=bar_pk, character=personagem)

        if request.method == "DELETE":
            if not eh_mestre(request.user, personagem.campaign):
                self.permission_denied(request, message="Só o mestre apaga barra.")
            barra.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        campos = set(request.data)
        if not eh_mestre(request.user, personagem.campaign) and campos - {"current"}:
            # O dono da ficha move a barra; renomear e mudar o máximo é do mestre.
            self.permission_denied(request, message="Você só pode mudar o valor atual.")

        corpo = CharacterBarSerializer(barra, data=request.data, partial=True)
        corpo.is_valid(raise_exception=True)
        corpo.save()
        return Response(corpo.data)

    @action(detail=True, methods=["get"], url_path="slots")
    def slots(self, request, pk=None):
        personagem = self.get_object()
        personagem.ensure_slots()
        return Response(
            InventorySlotSerializer(personagem.slots.order_by("position"), many=True).data
        )

    @action(detail=True, methods=["put"], url_path=r"slots/(?P<position>[0-9]+)")
    def atribuir_slot(self, request, pk=None, position=None):
        personagem = self.get_object()
        if not eh_mestre(request.user, personagem.campaign):
            self.permission_denied(request, message="Só o mestre mexe no inventário.")

        personagem.ensure_slots()
        slot = get_object_or_404(InventorySlot, character=personagem, position=position)

        corpo = AtribuirItemSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        item = corpo.validated_data["item"]

        if item is not None and item.campaign_id != personagem.campaign_id:
            # Item de outra mesa no slot vaza nome e imagem do material dela.
            return Response(
                {"item": "Esse item não é desta campanha."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slot.item = item
        slot.save()
        return Response(InventorySlotSerializer(slot).data)


class PermissaoNPC(IsAuthenticated):
    def has_object_permission(self, request, view, npc):
        if request.method in SAFE_METHODS:
            return pode_ver_npc(request.user, npc)
        return pode_editar_npc(request.user, npc)


class NPCViewSet(viewsets.ModelViewSet):
    serializer_class = NPCSerializer
    permission_classes = [PermissaoNPC]

    def get_queryset(self):
        usuario = self.request.user
        minhas = campanhas_do_usuario(usuario)
        return (
            NPC.objects.filter(campaign__in=minhas)
            .filter(
                Q(campaign__master=usuario)
                | Q(visible=True, assigned_to_character__assigned_to=usuario)
            )
            .distinct()
            .order_by("name")
        )

    def perform_create(self, serializer):
        campanha = serializer.validated_data.get("campaign")
        if not eh_mestre(self.request.user, campanha):
            self.permission_denied(
                self.request, message="Só o mestre da campanha cria NPC nela."
            )
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get", "post"], url_path="bars")
    def barras(self, request, pk=None):
        npc = self.get_object()

        if request.method == "GET":
            return Response(NPCBarSerializer(npc.bars.all(), many=True).data)

        corpo = NPCBarSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        barra = corpo.save(npc=npc, order=npc.bars.count())
        return Response(NPCBarSerializer(barra).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"bars/(?P<bar_pk>[^/.]+)")
    def barra(self, request, pk=None, bar_pk=None):
        npc = self.get_object()
        barra = get_object_or_404(NPCBar, pk=bar_pk, npc=npc)

        if request.method == "DELETE":
            barra.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        corpo = NPCBarSerializer(barra, data=request.data, partial=True)
        corpo.is_valid(raise_exception=True)
        corpo.save()
        return Response(corpo.data)

    @action(detail=True, methods=["get"], url_path="slots")
    def slots(self, request, pk=None):
        npc = self.get_object()
        npc.ensure_slots()
        return Response(
            NPCInventorySlotSerializer(npc.slots.order_by("position"), many=True).data
        )

    @action(detail=True, methods=["put"], url_path=r"slots/(?P<position>[0-9]+)")
    def atribuir_slot(self, request, pk=None, position=None):
        npc = self.get_object()
        npc.ensure_slots()
        slot = get_object_or_404(NPCInventorySlot, npc=npc, position=position)

        corpo = AtribuirItemSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        item = corpo.validated_data["item"]

        if item is not None and item.campaign_id != npc.campaign_id:
            return Response(
                {"item": "Esse item não é desta campanha."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slot.item = item
        slot.save()
        return Response(NPCInventorySlotSerializer(slot).data)


class PermissaoItem(IsAuthenticated):
    def has_object_permission(self, request, view, item):
        if request.method in SAFE_METHODS:
            return participa(request.user, item.campaign)
        return eh_mestre(request.user, item.campaign)


class ItemViewSet(viewsets.ModelViewSet):
    serializer_class = ItemSerializer
    permission_classes = [PermissaoItem]

    def get_queryset(self):
        minhas = campanhas_do_usuario(self.request.user)
        return Item.objects.filter(campaign__in=minhas).distinct().order_by("name")

    def perform_create(self, serializer):
        campanha = serializer.validated_data.get("campaign")
        if not eh_mestre(self.request.user, campanha):
            self.permission_denied(
                self.request, message="Só o mestre da campanha cria item nela."
            )
        serializer.save(created_by=self.request.user)

"""Serializers da API.

Duas coisas que valem explicação:

1. `campaign` é de escrita só na criação. Mover um personagem de campanha pela
   API arrastaria itens de slot e vínculo de jogador para uma mesa onde eles não
   existem; se um dia isso for preciso, é uma operação própria, não um PATCH.
2. Existe um serializer separado só para os status (`CharacterStatusSerializer`).
   O jogador atribuído à ficha mexe na vida, não na ficha — a diferença entre os
   dois papéis é qual serializer a view escolhe, não uma lista de campos
   verificada na mão dentro do update.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from hud.models import (
    AudioListener,
    AudioTrack,
    Campaign,
    Character,
    CharacterAbility,
    CharacterAttribute,
    CharacterBar,
    CharacterSkill,
    InventorySlot,
    Item,
    NPC,
    NPCAbility,
    NPCAttribute,
    NPCBar,
    NPCInventorySlot,
    NPCSkill,
    PlaybackState,
    UserProfile,
)

User = get_user_model()


class UserResumoSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="profile.display_name", read_only=True)
    nickname = serializers.CharField(source="profile.nickname", read_only=True)
    role = serializers.CharField(source="profile.role", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "nickname", "role"]


class PerfilSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["username", "email", "display_name", "nickname", "role", "avatar"]
        read_only_fields = ["role"]


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ["id", "campaign", "name", "description", "image", "created_at"]
        read_only_fields = ["created_at"]
        extra_kwargs = {"campaign": {"required": True}}


class CampaignSerializer(serializers.ModelSerializer):
    master = UserResumoSerializer(read_only=True)
    players = UserResumoSerializer(many=True, read_only=True)
    sou_mestre = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "description", "banner",
            "master", "players", "sou_mestre",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_sou_mestre(self, campaign) -> bool:
        pedido = self.context.get("request")
        return bool(pedido) and campaign.master_id == pedido.user.id


class CharacterSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterSkill
        fields = ["id", "name", "value", "order"]


class CharacterAbilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterAbility
        fields = ["id", "name", "order"]


class CharacterAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterAttribute
        fields = ["id", "name", "value", "order"]


class CharacterBarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacterBar
        fields = ["id", "name", "current", "max_value", "color", "order"]

    def validate(self, dados):
        maximo = dados.get("max_value", getattr(self.instance, "max_value", None))
        atual = dados.get("current", getattr(self.instance, "current", None))
        if maximo is not None and maximo <= 0:
            raise serializers.ValidationError({"max_value": "Tem que ser maior que zero."})
        if atual is not None and maximo is not None and atual > maximo:
            raise serializers.ValidationError({"current": "Não pode passar do máximo."})
        return dados


class InventorySlotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = InventorySlot
        fields = ["id", "position", "item"]


class CharacterSerializer(serializers.ModelSerializer):
    skills = CharacterSkillSerializer(many=True, read_only=True)
    abilities = CharacterAbilitySerializer(many=True, read_only=True)
    attributes = CharacterAttributeSerializer(many=True, read_only=True)
    bars = CharacterBarSerializer(many=True, read_only=True)
    slots = InventorySlotSerializer(many=True, read_only=True)

    class Meta:
        model = Character
        fields = [
            "id", "campaign", "name", "image",
            "hp_max", "hp_current", "sp_max", "sp_current",
            "inventory_capacity", "assigned_to", "visible",
            "created_by", "created_at", "updated_at",
            "skills", "abilities", "attributes", "bars", "slots",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Trocar de campanha não é um PATCH: ver o docstring do módulo.
        if self.instance is not None:
            self.fields["campaign"].read_only = True


class CharacterStatusSerializer(serializers.ModelSerializer):
    """O que o jogador atribuído à ficha pode mudar."""

    class Meta:
        model = Character
        fields = ["id", "hp_current", "sp_current"]


class NPCSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCSkill
        fields = ["id", "name", "value", "order"]


class NPCAbilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCAbility
        fields = ["id", "name", "order"]


class NPCAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCAttribute
        fields = ["id", "name", "value", "order"]


class NPCBarSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCBar
        fields = ["id", "name", "current", "max_value", "color", "order"]

    def validate(self, dados):
        maximo = dados.get("max_value", getattr(self.instance, "max_value", None))
        atual = dados.get("current", getattr(self.instance, "current", None))
        if maximo is not None and maximo <= 0:
            raise serializers.ValidationError({"max_value": "Tem que ser maior que zero."})
        if atual is not None and maximo is not None and atual > maximo:
            raise serializers.ValidationError({"current": "Não pode passar do máximo."})
        return dados


class NPCInventorySlotSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = NPCInventorySlot
        fields = ["id", "position", "item"]


class NPCSerializer(serializers.ModelSerializer):
    skills = NPCSkillSerializer(many=True, read_only=True)
    abilities = NPCAbilitySerializer(many=True, read_only=True)
    attributes = NPCAttributeSerializer(many=True, read_only=True)
    bars = NPCBarSerializer(many=True, read_only=True)
    slots = NPCInventorySlotSerializer(many=True, read_only=True)

    class Meta:
        model = NPC
        fields = [
            "id", "campaign", "name", "image",
            "hp_max", "hp_current", "sp_max", "sp_current",
            "inventory_capacity", "assigned_to_character", "visible",
            "created_by", "created_at", "updated_at",
            "skills", "abilities", "attributes", "bars", "slots",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["campaign"].read_only = True


class AtribuirItemSerializer(serializers.Serializer):
    """Corpo do pedido que põe ou tira um item de um slot.

    `item` nulo esvazia o slot. A checagem de campanha não está aqui porque
    depende do slot, que a view conhece e o serializer não.
    """

    item = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(), allow_null=True, required=False, default=None
    )


class AdicionarJogadorSerializer(serializers.Serializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())


class AudioTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioTrack
        fields = ["id", "youtube_id", "title", "order"]
        read_only_fields = ["youtube_id", "order"]


class NovaFaixaSerializer(serializers.Serializer):
    """Entrada de faixa nova: o mestre cola um link, não um id.

    O `url` aceita qualquer formato do YouTube — a normalização é da view, que
    chama `api.youtube.extrair_id`.
    """

    url = serializers.CharField(max_length=500)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)


class ReordenarFaixasSerializer(serializers.Serializer):
    """A lista inteira de ids na ordem nova.

    Mandar a lista toda em vez de "mova a faixa X para a posição 3" evita que
    dois arrastões seguidos se cruzem e deixem a ordem em algo que ninguém pediu.
    """

    order = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)


class PlaybackStateSerializer(serializers.ModelSerializer):
    position_seconds = serializers.SerializerMethodField()
    stale = serializers.BooleanField(source="esfriou", read_only=True)
    server_time = serializers.SerializerMethodField()

    class Meta:
        model = PlaybackState
        fields = [
            "track", "is_playing", "position_seconds",
            "loop_mode", "updated_at", "stale", "server_time",
        ]

    def get_position_seconds(self, estado) -> float:
        # A posição de agora, não a de quando o mestre salvou: quem chega
        # depois entraria atrasado pelo tanto que o pedido demorou.
        return round(estado.posicao_agora(), 2)

    def get_server_time(self, estado) -> str:
        # O cliente compara o relógio dele com o nosso antes de decidir que
        # está fora de sincronia. Relógio de usuário erra com frequência.
        return timezone.now().isoformat()


class OuvinteSerializer(serializers.ModelSerializer):
    """Quem está no áudio, com a cara que a mesa reconhece.

    Numa sessão as pessoas são os personagens, então é a ficha que aparece — o
    avatar do perfil só entra para quem não tem uma, o mestre à frente. As duas
    fontes têm os mesmos três números de enquadramento (`RetratoEnquadrado`), e
    é por isso que o widget desenha as duas com o mesmo código.

    A ficha vem pronta no contexto, em `fichas`. Buscar aqui dentro custaria uma
    consulta por ouvinte, e esta lista é redesenhada a cada dez segundos.
    """

    user_id = serializers.IntegerField(read_only=True)
    name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    zoom = serializers.SerializerMethodField()
    focus_x = serializers.SerializerMethodField()
    focus_y = serializers.SerializerMethodField()
    is_master = serializers.SerializerMethodField()

    class Meta:
        model = AudioListener
        fields = ["user_id", "name", "image", "zoom", "focus_x", "focus_y", "is_master"]

    def _ficha(self, ouvinte):
        return (self.context.get("fichas") or {}).get(ouvinte.user_id)

    def _perfil(self, ouvinte):
        return getattr(ouvinte.user, "profile", None)

    def _retrato(self, ouvinte):
        """De onde sai a imagem e o corte dela: a ficha, ou o perfil."""
        ficha = self._ficha(ouvinte)
        if ficha is not None and ficha.image:
            return ficha, ficha.image
        perfil = self._perfil(ouvinte)
        if perfil is not None and perfil.avatar:
            return perfil, perfil.avatar
        return None, None

    def get_name(self, ouvinte) -> str:
        ficha = self._ficha(ouvinte)
        if ficha is not None:
            return ficha.name
        perfil = self._perfil(ouvinte)
        if perfil is not None:
            return perfil.display_name or perfil.nickname or ouvinte.user.username
        return ouvinte.user.username

    def get_image(self, ouvinte) -> str:
        _, imagem = self._retrato(ouvinte)
        return imagem.url if imagem else ""

    def get_zoom(self, ouvinte) -> int:
        dono, _ = self._retrato(ouvinte)
        return getattr(dono, "image_zoom", 100) or 100

    def get_focus_x(self, ouvinte) -> float:
        dono, _ = self._retrato(ouvinte)
        return getattr(dono, "image_focus_x", 0.5)

    def get_focus_y(self, ouvinte) -> float:
        dono, _ = self._retrato(ouvinte)
        return getattr(dono, "image_focus_y", 0.5)

    def get_is_master(self, ouvinte) -> bool:
        return ouvinte.user_id == self.context.get("mestre_id")


class PresencaSerializer(serializers.Serializer):
    """O corpo do batimento de presença: entrar, continuar, ou sair.

    `listening` ausente vale como `true` porque o pedido normal é o batimento —
    a saída é o caso raro, e é ela que carrega o campo.
    """

    listening = serializers.BooleanField(required=False, default=True)


class EstadoDoPlayerSerializer(serializers.Serializer):
    """O que o mestre manda ao mexer nos controles."""

    track = serializers.PrimaryKeyRelatedField(
        queryset=AudioTrack.objects.all(), allow_null=True, required=False
    )
    is_playing = serializers.BooleanField(required=False)
    position_seconds = serializers.FloatField(required=False, min_value=0)
    loop_mode = serializers.ChoiceField(
        choices=PlaybackState.LOOP_CHOICES, required=False
    )

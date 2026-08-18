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
from rest_framework import serializers

from hud.models import (
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

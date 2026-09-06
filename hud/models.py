from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


INVENTORY_ROWS = 4
INVENTORY_COLUMNS = 4
TOTAL_SLOTS = INVENTORY_ROWS * INVENTORY_COLUMNS


class Campaign(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    banner = models.ImageField(upload_to="campaigns/", null=True, blank=True)
    master = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns_as_master",
    )
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="campaigns_as_player",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name


class RetratoEnquadrado(models.Model):
    """O zoom e o pedaço da foto que aparece dentro da moldura da ficha.

    A moldura tem proporção fixa. Guardar só o arquivo obriga a escolher entre
    mostrar a foto inteira (com tarja em volta) ou cortar pelo centro — e o
    centro geométrico quase nunca é o rosto. Estes três números dizem qual
    pedaço o mestre escolheu, e ficam no banco porque o corte tem que ser o
    mesmo para o jogador que abre a ficha do outro lado da mesa.

    O ponto vai de 0 (borda esquerda/topo) a 1 (direita/base), como fração da
    sobra que o zoom criou: assim ele continua valendo se a moldura mudar de
    tamanho na tela do outro.
    """

    ZOOM_MINIMO = 100
    ZOOM_MAXIMO = 400

    image_zoom = models.PositiveSmallIntegerField(default=100)
    image_focus_x = models.FloatField(default=0.5)
    image_focus_y = models.FloatField(default=0.5)

    class Meta:
        abstract = True

    def clamp_framing(self) -> None:
        zoom = self.image_zoom if self.image_zoom is not None else 100
        self.image_zoom = min(max(int(zoom), self.ZOOM_MINIMO), self.ZOOM_MAXIMO)
        for campo in ("image_focus_x", "image_focus_y"):
            ponto = getattr(self, campo)
            ponto = 0.5 if ponto is None else float(ponto)
            setattr(self, campo, min(max(ponto, 0.0), 1.0))

    def reset_framing(self) -> None:
        """Foto nova, enquadramento novo: o corte antigo não vale para outra imagem."""
        self.image_zoom = 100
        self.image_focus_x = 0.5
        self.image_focus_y = 0.5


class UserProfile(RetratoEnquadrado):
    ROLE_MASTER = "MASTER"
    ROLE_PLAYER = "PLAYER"
    ROLE_CHOICES = (
        (ROLE_MASTER, "Master"),
        (ROLE_PLAYER, "Player"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_PLAYER)
    display_name = models.CharField(max_length=120, blank=True)  # Nome
    nickname = models.CharField(max_length=60, blank=True)  # Apelido
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.user.username} ({self.role})"

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        return super().save(*args, **kwargs)

    @property
    def is_master(self) -> bool:
        return self.role == self.ROLE_MASTER

    @property
    def is_player(self) -> bool:
        return self.role == self.ROLE_PLAYER


class NPC(RetratoEnquadrado):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="npcs",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="npcs/", null=True, blank=True)
    hp_max = models.PositiveIntegerField(default=10)
    hp_current = models.PositiveIntegerField(default=10)
    sp_max = models.PositiveIntegerField(default=10)
    sp_current = models.PositiveIntegerField(default=10)
    inventory_capacity = models.PositiveIntegerField(default=16)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_npcs",
    )
    assigned_to_character = models.ForeignKey(
        "Character",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npcs",
    )
    visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def clamp_stats(self) -> None:
        self.hp_current = min(self.hp_current, self.hp_max)
        self.sp_current = min(self.sp_current, self.sp_max)

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_stats()
        self.clamp_framing()
        return super().save(*args, **kwargs)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("position", flat=True))
        # Cria slots faltantes
        missing = [pos for pos in range(1, self.inventory_capacity + 1) if pos not in existing]
        NPCInventorySlot.objects.bulk_create(
            [NPCInventorySlot(npc=self, position=pos) for pos in missing],
            ignore_conflicts=True,
        )
        # Remove slots excedentes (quando capacidade diminui)
        self.slots.filter(position__gt=self.inventory_capacity).delete()


class Character(RetratoEnquadrado):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="characters",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="characters/", null=True, blank=True)
    hp_max = models.PositiveIntegerField(default=10)
    hp_current = models.PositiveIntegerField(default=10)
    sp_max = models.PositiveIntegerField(default=10)
    sp_current = models.PositiveIntegerField(default=10)
    inventory_capacity = models.PositiveIntegerField(default=16)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_characters",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="characters",
    )
    visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def clamp_stats(self) -> None:
        self.hp_current = min(self.hp_current, self.hp_max)
        self.sp_current = min(self.sp_current, self.sp_max)

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_stats()
        self.clamp_framing()
        return super().save(*args, **kwargs)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("position", flat=True))
        # Cria slots faltantes
        missing = [pos for pos in range(1, self.inventory_capacity + 1) if pos not in existing]
        InventorySlot.objects.bulk_create(
            [InventorySlot(character=self, position=pos) for pos in missing],
            ignore_conflicts=True,
        )
        # Remove slots excedentes (quando capacidade diminui)
        self.slots.filter(position__gt=self.inventory_capacity).delete()


class CharacterSkill(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class CharacterAbility(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="abilities")
    name = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class CharacterBar(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#ff4444")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class CharacterAttribute(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name} = {self.value}"


class NPCSkill(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCAbility(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="abilities")
    name = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCBar(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#ff4444")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCAttribute(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name} = {self.value}"


class Enemy(RetratoEnquadrado):
    """A ficha do inimigo: a mesma do personagem, sem inventário.

    Inimigo não carrega mochila. O que ele deixa cair vira item da campanha
    pela mão do mestre, então não há `InventorySlot` aqui — e é só isso que o
    separa do NPC. Também não tem os campos `hp_*`/`sp_*`: eles existem em
    `Character` e `NPC` por compatibilidade com os dados de antes das barras, e
    uma ficha nova não precisa herdar essa dívida.

    Nasce escondido. Quem revela é o mestre, quando quer que a mesa veja a
    barra de vida do que está na frente dela.
    """

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="enemies",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="enemies/", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_enemies",
    )
    visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        return super().save(*args, **kwargs)


class EnemySkill(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyAbility(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="abilities")
    name = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyBar(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#e11d2e")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyAttribute(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name} = {self.value}"


class Item(RetratoEnquadrado):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="items",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="items/", null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="items",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        return super().save(*args, **kwargs)


class InventorySlot(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveIntegerField()
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="slots")

    class Meta:
        ordering = ["position"]
        unique_together = ("character", "position")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name} slot {self.position}"

    @property
    def label(self) -> str:
        return f"Slot {self.position}"

    @property
    def row(self) -> int:
        return (self.position - 1) // INVENTORY_COLUMNS

    @property
    def col(self) -> int:
        return (self.position - 1) % INVENTORY_COLUMNS


class NPCInventorySlot(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveIntegerField()
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="npc_slots")

    class Meta:
        ordering = ["position"]
        unique_together = ("npc", "position")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name} slot {self.position}"

    @property
    def label(self) -> str:
        return f"Slot {self.position}"

    @property
    def row(self) -> int:
        return (self.position - 1) // INVENTORY_COLUMNS

    @property
    def col(self) -> int:
        return (self.position - 1) % INVENTORY_COLUMNS


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ANN001
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=Character)
def create_character_slots(sender, instance: Character, created: bool, **kwargs):  # noqa: ANN001
    if created:
        instance.ensure_slots()


@receiver(post_save, sender=NPC)
def create_npc_slots(sender, instance: NPC, created: bool, **kwargs):  # noqa: ANN001
    if created:
        instance.ensure_slots()


class PasswordResetToken(models.Model):
    """O que fica guardado é o hash do token, nunca o token em si.

    O valor sorteado só existe dentro do link que vai por e-mail. Guardar ele
    cru no banco significaria que qualquer cópia do db.sqlite3 — backup,
    download, olhada no admin — vira senha de todo mundo.

    SHA-256 puro basta aqui: o token tem 32 bytes de aleatoriedade real, então
    não há o que adivinhar por força bruta. Senha de usuário é outra história e
    continua no hasher do Django.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Reset token for {self.user.username}"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def emitir(cls, user, validade: timedelta) -> str:
        """Cria o registro e devolve o token cru, que só o e-mail vê."""
        raw_token = secrets.token_urlsafe(32)
        cls.objects.create(
            user=user,
            token=cls.hash_token(raw_token),
            expires_at=timezone.now() + validade,
        )
        return raw_token


class AudioTrack(models.Model):
    """Uma faixa da trilha da campanha, apontando para um vídeo do YouTube.

    Guardamos o id de onze caracteres, não a URL inteira. A mesma faixa chega
    de cinco formatos diferentes (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`,
    com lista e tempo pendurados atrás), e normalizar na entrada evita ter a
    mesma música quatro vezes na lista por causa do formato do link.
    """

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="tracks"
    )
    youtube_id = models.CharField(max_length=20)
    title = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracks_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("campaign", "youtube_id")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title or self.youtube_id


class PlaybackState(models.Model):
    """O que está tocando numa campanha, agora.

    Ninguém transmite áudio: cada navegador toca o vídeo por conta própria e usa
    esta linha para saber o quê, de onde e se está rodando. Por isso
    `position_seconds` sozinho não basta — ele é a posição no instante
    `updated_at`. Quem chega depois calcula onde a faixa deveria estar somando o
    tempo decorrido, senão todo mundo entraria atrasado pelo tanto que demorou
    para pedir.
    """

    LOOP_OFF = "OFF"
    LOOP_ONE = "ONE"
    LOOP_ALL = "ALL"
    LOOP_CHOICES = (
        (LOOP_OFF, "Sem repetição"),
        (LOOP_ONE, "Repetir a faixa"),
        (LOOP_ALL, "Repetir a lista"),
    )

    # Depois deste tempo sem notícia do mestre, o estado não vale mais: a aba
    # dele caiu, fechou ou dormiu. Sem isso os jogadores ficariam tocando
    # sozinhos uma trilha que o mestre parou de ouvir faz meia hora.
    SEGUNDOS_ATE_ESFRIAR = 90

    campaign = models.OneToOneField(
        Campaign, on_delete=models.CASCADE, related_name="playback"
    )
    track = models.ForeignKey(
        AudioTrack, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_playing = models.BooleanField(default=False)
    position_seconds = models.FloatField(default=0)
    loop_mode = models.CharField(max_length=3, choices=LOOP_CHOICES, default=LOOP_OFF)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.campaign.name}: {self.track or 'nada'}"

    @property
    def esfriou(self) -> bool:
        idade = (timezone.now() - self.updated_at).total_seconds()
        return idade > self.SEGUNDOS_ATE_ESFRIAR

    def posicao_agora(self) -> float:
        """Onde a faixa está neste instante, não onde estava quando salvamos."""
        if not self.is_playing or self.esfriou:
            return self.position_seconds
        decorrido = (timezone.now() - self.updated_at).total_seconds()
        return self.position_seconds + max(decorrido, 0)


@receiver(post_save, sender=Campaign)
def create_playback_state(sender, instance: Campaign, created: bool, **kwargs):  # noqa: ANN001
    if created:
        PlaybackState.objects.create(campaign=instance)

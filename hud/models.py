from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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


class UserProfile(models.Model):
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

    @property
    def is_master(self) -> bool:
        return self.role == self.ROLE_MASTER

    @property
    def is_player(self) -> bool:
        return self.role == self.ROLE_PLAYER


class Character(models.Model):
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
        return super().save(*args, **kwargs)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("position", flat=True))
        missing = [pos for pos in range(1, self.inventory_capacity + 1) if pos not in existing]
        InventorySlot.objects.bulk_create(
            [InventorySlot(character=self, position=pos) for pos in missing],
            ignore_conflicts=True,
        )


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


class Item(models.Model):
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


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ANN001
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=Character)
def create_character_slots(sender, instance: Character, created: bool, **kwargs):  # noqa: ANN001
    if created:
        instance.ensure_slots()


class PasswordResetToken(models.Model):
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

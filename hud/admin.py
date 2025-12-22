from django.contrib import admin

from .models import Campaign, Character, CharacterAbility, CharacterSkill, InventorySlot, Item, UserProfile


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "master", "created_at")
    list_filter = ("master", "created_at")
    search_fields = ("name", "master__username")
    filter_horizontal = ("players",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


class InventorySlotInline(admin.TabularInline):
    model = InventorySlot
    extra = 0
    fields = ("position", "item")
    ordering = ("position",)


class CharacterSkillInline(admin.TabularInline):
    model = CharacterSkill
    extra = 0
    fields = ("name", "value", "order")
    ordering = ("order", "name")


class CharacterAbilityInline(admin.TabularInline):
    model = CharacterAbility
    extra = 0
    fields = ("name", "order")
    ordering = ("order", "name")


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "assigned_to", "created_by", "hp_current", "sp_current", "image")
    list_filter = ("assigned_to",)
    search_fields = ("name", "assigned_to__username")
    inlines = [InventorySlotInline, CharacterSkillInline, CharacterAbilityInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at", "image")
    search_fields = ("name",)


@admin.register(InventorySlot)
class InventorySlotAdmin(admin.ModelAdmin):
    list_display = ("character", "position", "item")
    list_filter = ("character",)
    ordering = ("character", "position")


@admin.register(CharacterSkill)
class CharacterSkillAdmin(admin.ModelAdmin):
    list_display = ("character", "name", "value", "order")
    list_filter = ("character",)
    ordering = ("order", "name")


@admin.register(CharacterAbility)
class CharacterAbilityAdmin(admin.ModelAdmin):
    list_display = ("character", "name", "order")
    list_filter = ("character",)
    ordering = ("order", "name")

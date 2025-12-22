import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rpg_panel.settings')
django.setup()

from django.contrib.auth.models import User
from hud.models import Character, Campaign

# Ver dados
user = User.objects.get(username='admin')
campaign = Campaign.objects.first()
character = Character.objects.get(pk=2)

print(f'Mestre da campanha: {campaign.master.username}')
print(f'Personagem vinculado a: {character.assigned_to}')
print(f'Personagem criado por: {character.created_by.username}')
print(f'Campaign do personagem: {character.campaign}')
print(f'User admin é mestre? {campaign.master == user}')

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rpg_panel.settings')
django.setup()

from django.contrib.auth.models import User

# Criar admin se não existir
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
    print("Admin criado: admin / admin123")
else:
    print("Admin já existe")


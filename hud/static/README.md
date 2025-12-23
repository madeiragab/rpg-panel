# Arquivos Visuais do RPG Panel

Esta pasta contém todos os arquivos estáticos (CSS e JavaScript) do projeto.

## Estrutura

```
hud/static/hud/
├── styles.css      # Estilos principais (glass-morphism, cores, layout)
├── inventory.js    # Lógica de gerenciamento de inventário (adicionar/remover itens)
└── drag.js         # Funcionalidade de drag-and-drop para itens
```

## Como usar

Os arquivos são servidos pelo Django via `{% static 'hud/...' %}`:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'hud/styles.css' %}">
<script src="{% static 'hud/inventory.js' %}"></script>
```

## Coletar arquivos estáticos

Para produção, rode:

```bash
python manage.py collectstatic --noinput
```

Isso copia todos os arquivos para `staticfiles/` para serem servidos pelo WhiteNoise.

## Desenvolvimento

- Edite os arquivos em `hud/static/hud/`
- O Django serve automaticamente em modo DEBUG
- Em produção, use WhiteNoise (já configurado em settings.py)

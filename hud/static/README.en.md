> 🇧🇷 [Português](README.md) · 🇬🇧 **English**

# RPG Panel visual assets

This folder holds all the project's static files (CSS and JavaScript).

## Structure

```
hud/static/hud/
├── styles.css      # Main styles (glass-morphism, colors, layout)
├── inventory.js    # Inventory management logic (add/remove items)
└── drag.js         # Drag-and-drop functionality for items
```

## How to use

The files are served by Django through `{% static 'hud/...' %}`:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'hud/styles.css' %}">
<script src="{% static 'hud/inventory.js' %}"></script>
```

## Collecting static files

For production, run:

```bash
python manage.py collectstatic --noinput
```

This copies every file into `staticfiles/` to be served by WhiteNoise.

## Development

- Edit the files in `hud/static/hud/`
- Django serves them automatically in DEBUG mode
- In production, use WhiteNoise (already configured in `settings.py`)

# RPG Panel 🎲

RPG Panel is a private web panel for managing tabletop RPG campaigns.  
It centralizes campaigns, players, characters, and inventory with clear role separation between game masters and players.

This is **not a public product**, **not a game engine**, and **not a complete RPG system**.  
It exists to replace scattered PDFs, notes, and spreadsheets when a campaign grows.

---

## Purpose

Provide a simple and consistent way to organize RPG campaign data:

- Campaigns
- Players
- Characters
- Inventory
- Access control (master vs player)

No rule automation.  
No dice engine.  
No attempt to replace the tabletop experience.

---

## Roles

### Game Master
- Create, edit, and delete campaigns
- Manage players inside a campaign
- Create and assign characters
- Manage items and inventory
- Reassign characters between players

### Player
- View campaigns they belong to
- View all campaign characters
- Fully access only their assigned character
- Manage their own profile

---

## Features

### Campaigns
- Create, edit, and delete campaigns
- Optional banner image per campaign
- Master is automatically added as a player
- Safe deletion with exact-name confirmation

### Players
- Add players via live search (nickname, name, or username)
- List all campaign participants
- Controlled removal by the master

### Characters
- Characters always belong to a campaign
- Each character is assigned to a player
- Player reassignment via dropdown
- Central character detail view
- Character navigation bar for quick switching

### Inventory
- Slot-based inventory system
- Configurable capacity per character
- Guaranteed empty slots for consistent UI
- Structure prepared for future drag-and-drop

### User Accounts
- Registration and authentication
- User profile with:
  - Display name
  - Nickname (used for search)
  - Avatar image

---

## Tech Stack

### Backend
- Python 3.11
- Django 5.x
- SQLite (development)
- Pillow (image handling)

### Frontend
- Django Templates
- CSS (glass-morphism style)
- Vanilla JavaScript

No SPA.  
No frontend frameworks.  
No unnecessary dependencies.

---

## Project Structure



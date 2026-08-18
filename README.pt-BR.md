> 🇧🇷 **Português** · 🇬🇧 [English](README.md)

# RPG Panel 🎲

[![ci](https://github.com/madeiragab/rpg-panel/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/madeiragab/rpg-panel/actions/workflows/ci.yml)

O RPG Panel é um painel web privado para gerenciar campanhas de RPG de mesa. Ele centraliza campanhas, jogadores, personagens, NPCs e inventário, com separação clara de papéis entre mestres e jogadores.

Isto **não é um produto público**, **não é uma engine de jogo** e **não é um sistema de RPG completo**. Ele existe para substituir PDFs, anotações e planilhas espalhadas quando uma campanha cresce.

## Documentação

| Documento | O que contém |
|---|---|
| [docs/architecture.pt-BR.md](docs/architecture.pt-BR.md) | Layout do app, fluxo de requisição, modelo de permissões, signals |
| [docs/data-model.pt-BR.md](docs/data-model.pt-BR.md) | Todos os modelos, relacionamentos e invariantes |
| [docs/api.pt-BR.md](docs/api.pt-BR.md) | API REST: autenticação JWT, endereços, papéis |
| [docs/deployment.pt-BR.md](docs/deployment.pt-BR.md) | Variáveis de ambiente, deploy, arquivos estáticos/mídia |

---

## Propósito

Oferecer um jeito simples e consistente de organizar os dados de uma campanha de RPG:

- Campanhas
- Jogadores
- Personagens e NPCs
- Inventário
- Controle de acesso (mestre vs jogador)

Sem automação de regras.
Sem motor de dados.
Sem tentativa de substituir a experiência da mesa.

---

## Papéis

Os papéis são **por campanha**, não globais: a mesma conta é mestre das campanhas que criou e jogador nas campanhas para as quais foi convidada.

### Mestre
- Criar, editar e excluir campanhas
- Gerenciar jogadores dentro de uma campanha
- Criar e atribuir personagens e NPCs
- Gerenciar itens e inventário
- Reatribuir personagens entre jogadores
- Alternar a visibilidade de personagens/NPCs para os jogadores
- Pré-visualizar a campanha como jogador com `?mode=player`

### Jogador
- Ver as campanhas de que participa
- Ver os personagens visíveis da campanha
- Acessar por completo apenas o personagem atribuído a si
- Gerenciar o próprio perfil

---

## Funcionalidades

### Campanhas
- Criar, editar e excluir campanhas
- Imagem de banner opcional por campanha
- O mestre é adicionado automaticamente como jogador
- Exclusão segura com confirmação pelo nome exato
- Jogadores podem sair de uma campanha

### Jogadores
- Adicionar jogadores por busca ao vivo (apelido, nome ou usuário)
- Listar todos os participantes da campanha
- Remoção controlada pelo mestre

### Personagens
- Personagens sempre pertencem a uma campanha
- Cada personagem é atribuído a um jogador
- Reatribuição de jogador via dropdown
- Visão central de detalhes do personagem
- Barra de navegação entre personagens para troca rápida
- Alternador de visibilidade (esconder dos jogadores personagens em construção)

### NPCs
- NPCs no escopo da campanha, com a mesma estrutura de ficha dos personagens
- Escondidos dos jogadores por padrão (`visible = False`)
- Podem ser vinculados a um personagem (familiares, companheiros, montarias)

### Fichas de personagem
Cada personagem e NPC suporta:
- **Barras** — recursos com nome personalizado, valores atual/máximo e uma cor (HP e SP foram migrados para esse sistema genérico)
- **Atributos** — pares nome/valor livres (Força, Destreza, …)
- **Perícias** — nome mais um valor opcional
- **Habilidades** — habilidades nomeadas
- Todos são ordenados pelo usuário por meio de um campo `order`

### Inventário
- Sistema de inventário por slots, renderizado em uma grade de 4 colunas
- Capacidade configurável por personagem/NPC (padrão: 16 slots)
- Os slots são criados automaticamente e mantidos em sincronia quando a capacidade muda
- Slots vazios são garantidos, então a interface nunca fica com buracos

### Contas de usuário
- Cadastro e autenticação
- Redefinição de senha por e-mail com tokens de uso único e prazo de validade
- Perfil de usuário com nome de exibição, apelido (usado na busca) e avatar

---

## Stack

### Backend
- Python 3.11
- Django 5.2 LTS
- Django REST Framework + SimpleJWT (a API em `/api/`)
- SQLite (desenvolvimento)
- Pillow (tratamento de imagens)
- Gunicorn + WhiteNoise (produção)

### Frontend
- Django Templates
- CSS (estilo glass-morphism)
- JavaScript puro (drag/drop do inventário, busca ao vivo, atualização de barras via AJAX)

Sem SPA.
Sem frameworks de frontend.
Sem dependências desnecessárias.

---

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate no Linux)
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse http://127.0.0.1:8000.

Para desenvolvimento local você pode rodar com `DEBUG=True`; um `SECRET_KEY` de fallback exclusivo para desenvolvimento é usado automaticamente. **Em produção, tanto `DJANGO_SECRET_KEY` quanto as credenciais de e-mail precisam estar definidas** — veja [docs/deployment.pt-BR.md](docs/deployment.pt-BR.md).

---

## Estrutura do Projeto

```text
rpg-panel/
├─ manage.py
├─ Procfile                    → ponto de entrada do gunicorn no deploy
├─ nixpacks.toml               → configuração de build
├─ requirements.txt
│
├─ rpg_panel/                  → configuração do projeto
│  ├─ settings.py              → configurações via ambiente (secret key, e-mail, BD)
│  ├─ urls.py                  → URLs raiz + serviço de mídia
│  ├─ wsgi.py / asgi.py
│
├─ hud/                        → a única aplicação
│  ├─ models.py                → Campaign, Character, NPC, Item, slots, barras…
│  ├─ views.py                 → todas as views (páginas + endpoints JSON)
│  ├─ forms.py                 → ModelForms de cada entidade editável
│  ├─ urls.py                  → rotas do app
│  ├─ admin.py                 → registro no admin do Django
│  ├─ context_processors.py    → injeta o papel do usuário em todo template
│  ├─ templatetags/            → filtros de template personalizados
│  ├─ migrations/
│  └─ static/hud/              → styles.css, inventory.js, drag.js
│
└─ templates/
   ├─ base.html
   ├─ hud/                     → dashboards, páginas de campanha/personagem/NPC
   └─ registration/            → login, cadastro, redefinição de senha
```

---

Feito por **Gabriel Madeira** · [github.com/madeiragab](https://github.com/madeiragab)

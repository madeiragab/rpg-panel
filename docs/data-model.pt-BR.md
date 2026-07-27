> 🇧🇷 **Português** · 🇬🇧 [English](data-model.md)

# Modelo de Dados

Todos os modelos vivem em `hud/models.py`. Tudo está no escopo de uma **campanha**, que é a raiz de agregação do domínio.

```mermaid
erDiagram
    User ||--|| UserProfile : "tem"
    User ||--o{ Campaign : "mestra"
    User }o--o{ Campaign : "joga em"
    Campaign ||--o{ Character : "contém"
    Campaign ||--o{ NPC : "contém"
    Campaign ||--o{ Item : "contém"
    User ||--o{ Character : "atribuído a"
    Character ||--o{ InventorySlot : "tem"
    NPC ||--o{ NPCInventorySlot : "tem"
    InventorySlot }o--o| Item : "guarda"
    Character ||--o{ CharacterBar : "tem"
    Character ||--o{ CharacterAttribute : "tem"
    Character ||--o{ CharacterSkill : "tem"
    Character ||--o{ CharacterAbility : "tem"
    Character ||--o{ NPC : "companheiros vinculados"
    User ||--o{ PasswordResetToken : "solicita"
```

## Campaign

O contêiner do qual todo o resto pendura.

| Campo | Observações |
|---|---|
| `name`, `description` | |
| `banner` | Imagem opcional (`campaigns/`) |
| `master` | FK para usuário — **a única conta com direito de edição** |
| `players` | M2M para usuários; o mestre é adicionado automaticamente na criação |
| `created_at`, `updated_at` | Ordenado do mais recente para o mais antigo |

Excluir uma campanha cascateia para seus personagens, NPCs e itens — daí a confirmação pelo nome exato na interface.

## UserProfile

Criado automaticamente por um signal `post_save` em `User`.

| Campo | Observações |
|---|---|
| `role` | `MASTER` / `PLAYER` — **legado**, a autorização real é por campanha |
| `display_name` | Nome completo exibido na interface |
| `nickname` | Usado pela busca de jogadores |
| `avatar` | Imagem opcional (`avatars/`) |

## Character e NPC

`Character` e `NPC` são estruturalmente gêmeos — mesmos atributos, mesma mecânica de inventário, mesmas subentidades de ficha. Diferem na propriedade e na visibilidade padrão:

| | Character | NPC |
|---|---|---|
| Pertence a | Campanha | Campanha |
| Controlado por | Um jogador (`assigned_to`) | O mestre |
| `visible` padrão | `True` | `False` |
| Vínculo extra | — | `assigned_to_character` (companheiro de um personagem) |

Campos compartilhados: `name`, `image`, `hp_max`/`hp_current`, `sp_max`/`sp_current`, `inventory_capacity` (padrão 16), `created_by`, timestamps.

Dois invariantes são garantidos no `save()`:

- **`clamp_stats()`** — `hp_current` e `sp_current` nunca podem exceder seus máximos, não importa o que um formulário ou endpoint envie.
- **`ensure_slots()`** — o inventário sempre tem exatamente `inventory_capacity` slots (veja abaixo).

> Os campos `hp_*` / `sp_*` são o sistema original de atributos. A migração `0010_migrate_hp_sp_to_bars` os moveu para o sistema genérico de **barras**; as colunas são mantidas por compatibilidade com os dados existentes e com os endpoints `modify_hp` / `modify_sp`.

## Subentidades da ficha

Cada uma delas existe em uma versão `Character…` e uma `NPC…`, todas ordenadas por `order` e depois `name`:

| Modelo | Campos | Propósito |
|---|---|---|
| `…Bar` | `name`, `current`, `max_value`, `color` | Recursos personalizados (HP, mana, sanidade…) |
| `…Attribute` | `name`, `value` | Atributos livres (FOR, DES…) |
| `…Skill` | `name`, `value` (opcional) | Perícias |
| `…Ability` | `name` | Habilidades nomeadas |

Os valores são `CharField`, não números, de propósito: sistemas diferentes escrevem atributos como `18`, `+3` ou `d8`, e o painel não os interpreta.

## Item e slots de inventário

`Item` tem escopo de campanha e é compartilhado: a mesma linha de item pode estar em vários inventários, porque os slots a referenciam por FK.

`InventorySlot` / `NPCInventorySlot`:

| Campo | Observações |
|---|---|
| `character` / `npc` | Dono |
| `position` | Começa em 1; `unique_together` com o dono |
| `item` | Anulável — `SET_NULL`, então excluir um item esvazia o slot em vez de destruí-lo |

Os auxiliares de layout (`row`, `col`) derivam a posição na grade a partir de `INVENTORY_COLUMNS = 4`, e é por isso que a interface renderiza uma grade de 4 colunas sem armazenar coordenadas.

### O contrato de `ensure_slots()`

```python
existing = set(self.slots.values_list("position", flat=True))
missing  = [p for p in range(1, self.inventory_capacity + 1) if p not in existing]
# bulk_create(missing, ignore_conflicts=True)
# depois: apaga os slots com position > inventory_capacity
```

Consequências que vale conhecer:

- Os slots são **sempre** materializados no banco, nunca renderizados como placeholders virtuais — o template pode iterar `character.slots` diretamente.
- **Reduzir a capacidade apaga os slots excedentes**, e qualquer item que estivesse neles é desatribuído (a linha do `Item` em si sobrevive).
- O método pode ser chamado repetidamente com segurança (`ignore_conflicts=True`).

## PasswordResetToken

| Campo | Observações |
|---|---|
| `user` | FK |
| `token` | String aleatória única usada na URL de redefinição |
| `created_at`, `expires_at` | Validade verificada no momento do resgate |
| `used` | Flag de uso único |

Os tokens nunca são apagados após o uso, o que deixa uma trilha de auditoria das tentativas de redefinição.

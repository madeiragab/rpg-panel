> 🇧🇷 **Português** · 🇬🇧 [English](architecture.md)

# Arquitetura

O RPG Panel é um projeto Django deliberadamente pequeno: **um pacote de projeto** (`rpg_panel`) e **uma aplicação** (`hud`). Não há camada de API nem SPA — as páginas são templates Django renderizados no servidor, e as poucas partes interativas (inventário, barras, busca de jogadores) chamam pequenos endpoints JSON no mesmo módulo de views.

```text
Navegador
  │  páginas HTML                         │  fetch() JSON
  ▼                                       ▼
hud/urls.py ─────────────► hud/views.py ─────────────► hud/models.py
                              │                            │
                              ├─ hud/forms.py              └─ signals
                              └─ templates/
```

## Modelo de permissões

Esta é a parte que vale entender, porque **não** é um sistema de papéis global.

O `UserProfile.role` existe e é mantido por compatibilidade retroativa, mas a autorização é decidida **por campanha, por requisição**:

```python
is_master = campaign.master == request.user
is_player = request.user in campaign.players.all()
```

Consequências:

- A mesma conta é mestre das campanhas que criou e jogadora nas campanhas para as quais foi convidada — sem precisar de contas separadas.
- Toda view que toca dados de campanha recalcula essas duas flags e devolve `HttpResponseForbidden` quando ambas são falsas.
- Os templates recebem `is_master` e renderizam os controles de edição apenas para o mestre.

### Modo de pré-visualização como jogador

Acrescentar `?mode=player` à URL de uma campanha ou personagem força `is_master` a `False` naquela requisição. Isso permite ao mestre ver exatamente o que seus jogadores veem (inclusive o que está escondido pela flag `visible`) sem precisar sair da conta.

> `_user_is_master()` em `views.py` é um **stub legado que sempre retorna `True`** — ele é anterior ao modelo por campanha e só é referenciado por templates antigos. Não use em verificações novas.

### Acesso em nível de personagem

`character_detail` é mais restritivo que o acesso à campanha:

| Situação | Resultado |
|---|---|
| O usuário é o mestre da campanha | Acesso total de edição |
| O usuário está na campanha, ou o personagem é atribuído a ele | Acesso de leitura |
| O personagem não tem campanha (dado legado) | Recai sobre `created_by` / `assigned_to` |
| Nenhum dos casos | `403 Forbidden` |

## Signals (`hud/models.py`)

Três receivers de `post_save` mantêm os dados consistentes sem espalhar código de configuração pelas views:

| Signal | Efeito |
|---|---|
| `User` criado | Cria o `UserProfile` correspondente |
| `Character` criado | Chama `ensure_slots()` para montar a grade de inventário |
| `NPC` criado | O mesmo para o inventário do NPC |

`ensure_slots()` é idempotente e também roda depois que o mestre edita uma ficha: cria em lote os slots faltantes e apaga os slots além da nova capacidade, então reduzir um inventário nunca deixa posições órfãs.

## Views: páginas vs endpoints JSON

O `hud/views.py` mistura dois tipos de view, distinguíveis pelo tipo de retorno:

- **Views de página** retornam `HttpResponse` (templates renderizados): `master_dashboard`, `player_dashboard`, `campaign_detail`, `character_detail`, `npc_detail`, `character_list`, `user_page`, `register`, `forgot_password`, `reset_password`.
- **Endpoints JSON** retornam `JsonResponse` e são chamados pelo JavaScript da página — todos são `@require_POST`, exceto a busca: `search_players`, `assign_slot`, `modify_hp`, `modify_sp`, `modify_bar`, `add_character_bar`, `delete_bar`, `add_npc_bar`, `modify_npc_bar`, `delete_npc_bar`, `toggle_character_visibility`, `toggle_npc_visibility`.

Páginas com múltiplos formulários (como `character_detail`, que edita a ficha, perícias, habilidades e atributos) despacham por um campo oculto `form_type` e usam `prefix`es de formulário do Django para evitar colisão entre nomes de campos.

## Redefinição de senha

O fluxo de redefinição embutido do Django foi substituído por um customizado, para que o texto do e-mail e o tempo de vida do token fiquem sob controle do projeto:

1. `forgot_password` localiza a conta e cria um `PasswordResetToken` com um carimbo de expiração.
2. O link é enviado por SMTP do Gmail (credenciais vindas de variáveis de ambiente — veja [deployment.pt-BR.md](deployment.pt-BR.md)).
3. `reset_password` valida o token (existe, não está `used`, não expirou), define a nova senha e queima **todos** os tokens abertos daquela conta — pedir três resets e usar um não pode deixar os outros dois valendo.

A tela de confirmação é a mesma exista ou não a conta, e não mostra endereço nenhum. Responder "usuário não encontrado" entregaria quais contas existem para quem estivesse chutando nomes; pelo mesmo motivo o envio é `fail_silently`, para que uma falha de SMTP no caminho do usuário existente não vire o mesmo vazamento por outra porta.

## Assets de frontend

`hud/static/hud/` guarda três arquivos, carregados pelos templates que precisam deles:

- `styles.css` — o tema glass-morphism;
- `inventory.js` — renderização de slots e atribuição de itens;
- `drag.js` — arrastar e soltar entre slots do inventário.

Os arquivos estáticos são servidos pelo **WhiteNoise** em produção com nomes comprimidos e com hash (`CompressedManifestStaticFilesStorage`), então o `collectstatic` precisa rodar a cada deploy.

> 🇧🇷 **Português** · 🇬🇧 [English](audio-player.md)

# Player de áudio da campanha

Um widget flutuante nas telas de campanha e de ficha. O mestre monta a trilha com links do YouTube, arrasta para ordenar e controla o que toca; quem está na mesa ouve junto.

## O que trafega (e o que não trafega)

**Não há áudio saindo do servidor.** O que existe no banco é uma linha dizendo *qual faixa*, *de que segundo* e *se está tocando*. Cada navegador toca o vídeo por conta própria a partir disso.

Essa é a razão de o player caber num plano grátis: cinco pessoas ouvindo a mesma trilha custam ao servidor cinco linhas de JSON, não cinco fluxos de áudio.

## A miniatura fica visível de propósito

Os Termos da API do YouTube não permitem esconder o player nem separar o áudio do vídeo. Um iframe de 1 pixel funcionaria tecnicamente e poderia custar a conta.

Então o widget mostra o vídeo em 200×113, com os controles do painel em volta. O tamanho está no CSS do próprio widget (`templates/hud/_audio_player.html`), num lugar só.

## Cada um ouve no seu volume

O volume e o mudo são locais, e continuam locais de propósito: o mestre controla *o que* toca, não *o quanto* cada pessoa ouve. Quem está de fone e quem está na caixa de som não deveriam depender um do outro.

## O clique obrigatório do jogador

Navegador nenhum deixa áudio começar sem gesto humano. Por isso o jogador vê um botão **"Entrar no áudio"** — ele existe só para haver um clique antes do primeiro play. Depois disso o mestre controla tudo.

Não dá para contornar; é regra do navegador, não escolha do projeto.

## Sincronização

`PlaybackState` guarda `position_seconds` **e** `updated_at`. A posição sozinha não bastaria: ela é a posição *naquele instante*. Quem abre a página no meio da música soma o tempo decorrido e entra onde a mesa está, não onde a música estava quando o mestre apertou play.

O cliente só dá `seek` se a diferença passar de 2,5 segundos. Corrigir desvio menor que isso soaria como engasgo a cada verificação, e ninguém numa mesa de RPG percebe dois segundos de trilha ambiente.

### Quando o mestre some

A aba do mestre manda um batimento a cada 15 segundos. Passados **90 segundos** sem notícia, o estado *esfria*: os clientes param de avançar a posição e o widget mostra pausado.

Sem isso, uma aba fechada às pressas deixaria a mesa tocando sozinha uma trilha que o mestre parou de ouvir faz meia hora.

## Tempo real: Pusher, com polling embaixo

O PythonAnywhere não serve WebSocket. O empurrão vem de fora: o Django publica no Pusher, os navegadores escutam o canal da campanha.

**O Pusher é acelerador, não mecanismo.** O banco é a fonte da verdade e o widget faz polling a cada 10 segundos de qualquer jeito. Sem chave configurada, com o Pusher fora do ar, ou com o plano grátis estourado, o player continua funcionando — só deixa de ser instantâneo. Por isso `realtime.publicar` engole exceção: uma falha de rede lá não pode transformar em erro 500 um comando que já foi salvo.

### Canal privado

O canal é `private-campanha-{id}-audio`. Canal público seria mais simples, mas a chave do Pusher vai para o navegador — é pública por desenho — e qualquer um com ela assinaria o canal de qualquer mesa e acompanharia a trilha dos outros.

Com `private-`, o Pusher pergunta ao nosso servidor antes de deixar entrar. `POST /api/pusher/auth/` responde, aplicando a mesma regra do resto: participa da campanha, entra.

## A ponte entre a página e a API

A página é autenticada por sessão; a API só entende JWT. Em vez de aceitar cookie na API — o que traria CSRF de volta por uma porta sem vigilância — a página pede um access de 15 minutos em `GET /audio/token/` e usa ele nas chamadas.

Não há aumento de privilégio: o usuário obteria esse mesmo token mandando a própria senha em `/api/token/`. O refresh não passa por ali, porque um refresh de sete dias dentro do HTML seria bem pior do que um access que morre sozinho.

## Endereços

Todos sob a campanha, com as regras de sempre — ler é de quem participa, escrever é do mestre.

| Método | Endereço | Quem pode |
|---|---|---|
| `GET` | `/api/campaigns/{id}/audio/` | mestre e jogadores |
| `POST` | `/api/campaigns/{id}/audio/tracks/` | mestre — corpo `{"url": "..."}` |
| `DELETE` | `/api/campaigns/{id}/audio/tracks/{track_id}/` | mestre |
| `PATCH` | `/api/campaigns/{id}/audio/order/` | mestre — corpo `{"order": [ids]}` |
| `PATCH` | `/api/campaigns/{id}/audio/state/` | mestre |
| `POST` | `/api/pusher/auth/` | quem participa da campanha do canal |

### Por que a reordenação manda a lista inteira

`{"order": [3, 1, 2]}`, não "mova a faixa 3 para a posição 1". Dois arrastões seguidos com a segunda forma se cruzariam e deixariam a fila em algo que ninguém pediu. O servidor ainda confere se a lista bate exatamente com as faixas da campanha — se não bater, a tela está velha e o pedido é recusado.

### Links aceitos

`api/youtube.py` normaliza qualquer formato para o id de onze caracteres: `watch?v=`, `youtu.be/`, `shorts/`, `embed/`, `music.youtube.com`, com lista e tempo pendurados atrás, ou o id cru. Sem isso, a mesma música entraria quatro vezes na lista só por causa de qual botão do YouTube o mestre usou para copiar.

## Configuração

Quatro variáveis de ambiente, todas opcionais:

| Variável | Para quê |
|---|---|
| `PUSHER_APP_ID` | id do app no painel do Pusher |
| `PUSHER_KEY` | chave **pública** — vai para o navegador, é assim mesmo |
| `PUSHER_SECRET` | segredo; **nunca sai do servidor** |
| `PUSHER_CLUSTER` | o cluster do app (`mt1`, `us2`, `eu`...). Padrão: `mt1` |

Sem elas o player funciona no polling. Para ligar o tempo real: criar uma conta grátis no Pusher, criar um app do tipo Channels, copiar as quatro e pôr no `.env` do host (no PythonAnywhere, no arquivo de WSGI ou nas variáveis da aba Web).

O plano grátis do Pusher dá 200 mil mensagens por dia e 100 conexões simultâneas — folga larga para qualquer mesa de RPG.

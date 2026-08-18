/* Player de áudio da campanha.
 *
 * Como funciona, em uma frase: o servidor guarda *o que* está tocando e *de
 * onde*, e cada navegador toca o vídeo por conta própria. Não há áudio saindo
 * do servidor — o que trafega é uma linha de estado.
 *
 * Três coisas que valem saber antes de mexer aqui:
 *
 * 1. Só o mestre escreve. O botão do jogador mexe no volume dele e em nada mais;
 *    a regra de verdade está no servidor, isto aqui é só a tela.
 *
 * 2. O navegador não deixa áudio começar sozinho. Por isso o jogador tem o botão
 *    "Entrar no áudio": ele existe para haver um clique humano antes do play,
 *    senão o YouTube devolve o vídeo mudo ou parado.
 *
 * 3. O Pusher é acelerador, não mecanismo. Sem chave, ou com o Pusher fora do
 *    ar, o `polling` lento segura o player. Por isso ele nunca é desligado.
 */
(() => {
  const raiz = document.getElementById('player-audio');
  if (!raiz) return;

  const CAMPANHA = raiz.dataset.campanha;
  const SOU_MESTRE = raiz.dataset.mestre === '1';
  const PUSHER_KEY = raiz.dataset.pusherKey || '';
  const PUSHER_CLUSTER = raiz.dataset.pusherCluster || 'mt1';

  const INTERVALO_POLLING = 10000;   // rede de segurança, não o caminho normal
  const INTERVALO_BATIMENTO = 15000; // o mestre dizendo "ainda estou aqui"
  const DESVIO_TOLERADO = 2.5;       // segundos antes de valer um seek

  const elemento = (id) => document.getElementById(id);
  const agora = elemento('pa-agora');
  const lista = elemento('pa-lista');
  const aviso = elemento('pa-aviso');
  const estadoCurto = elemento('pa-estado-curto');

  let token = null;
  let tokenExpiraEm = 0;
  let estado = null;
  let faixas = [];
  let player = null;
  let playerPronto = false;
  let liberadoPeloUsuario = SOU_MESTRE; // o mestre clica para tocar, já é o gesto
  let mudo = false;
  let volume = 60;

  // ---------------------------------------------------------------- utilidades

  function mostrarAviso(texto) {
    aviso.textContent = texto || '';
  }

  async function pegarToken() {
    // O access dura 15 minutos; renovamos com folga para não descobrir que
    // venceu no meio de um clique do mestre.
    if (token && Date.now() < tokenExpiraEm - 60000) return token;

    const resposta = await fetch(raiz.dataset.urlToken, { credentials: 'same-origin' });
    if (!resposta.ok) throw new Error('token');
    const corpo = await resposta.json();
    token = corpo.access;
    tokenExpiraEm = Date.now() + 15 * 60 * 1000;
    return token;
  }

  async function api(caminho, opcoes = {}) {
    const acesso = await pegarToken();
    const resposta = await fetch(`/api/campaigns/${CAMPANHA}${caminho}`, {
      ...opcoes,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${acesso}`,
        ...(opcoes.headers || {}),
      },
    });
    if (!resposta.ok) {
      const erro = await resposta.json().catch(() => ({}));
      throw new Error(Object.values(erro)[0] || `Falhou (${resposta.status})`);
    }
    return resposta.status === 204 ? null : resposta.json();
  }

  function faixaAtual() {
    if (!estado || !estado.track) return null;
    return faixas.find((f) => f.id === estado.track) || null;
  }

  function indiceAtual() {
    const atual = faixaAtual();
    return atual ? faixas.indexOf(atual) : -1;
  }

  function nomeDaFaixa(faixa) {
    return faixa ? (faixa.title || faixa.youtube_id) : 'Nada tocando.';
  }

  // ------------------------------------------------------------------ desenho

  function desenhar() {
    const atual = faixaAtual();
    agora.textContent = nomeDaFaixa(atual);
    estadoCurto.textContent = estado && estado.is_playing && !estado.stale ? '▶' : '⏸';

    if (SOU_MESTRE) {
      const tocar = elemento('pa-tocar');
      if (tocar) tocar.textContent = estado && estado.is_playing ? '⏸' : '▶';
      const loop = elemento('pa-loop');
      if (loop && estado) {
        const rotulo = { OFF: '↻ off', ONE: '↻ faixa', ALL: '↻ lista' };
        loop.textContent = rotulo[estado.loop_mode] || '↻ off';
      }
    }

    lista.innerHTML = '';
    faixas.forEach((faixa, indice) => {
      const item = document.createElement('li');
      if (atual && faixa.id === atual.id) item.classList.add('tocando');

      const nome = document.createElement('span');
      nome.className = 'pa-nome';
      nome.textContent = `${indice + 1}. ${nomeDaFaixa(faixa)}`;
      item.appendChild(nome);

      if (SOU_MESTRE) {
        item.draggable = true;
        item.dataset.id = faixa.id;
        ligarArrasto(item);

        const tocarEsta = document.createElement('button');
        tocarEsta.textContent = '▶';
        tocarEsta.title = 'Tocar esta';
        tocarEsta.onclick = () => mandarEstado({ track: faixa.id, position_seconds: 0, is_playing: true });
        item.appendChild(tocarEsta);

        const remover = document.createElement('button');
        remover.textContent = '✕';
        remover.title = 'Tirar da lista';
        remover.onclick = () => comErro(() => api(`/audio/tracks/${faixa.id}/`, { method: 'DELETE' }).then(aplicar));
        item.appendChild(remover);
      }

      lista.appendChild(item);
    });
  }

  // ----------------------------------------------------------------- arrastar

  let arrastada = null;

  function ligarArrasto(item) {
    item.addEventListener('dragstart', () => {
      arrastada = item;
      item.classList.add('arrastando');
    });
    item.addEventListener('dragend', () => {
      item.classList.remove('arrastando');
      arrastada = null;
      salvarOrdem();
    });
    item.addEventListener('dragover', (evento) => {
      evento.preventDefault();
      if (!arrastada || arrastada === item) return;
      const caixa = item.getBoundingClientRect();
      const depois = evento.clientY > caixa.top + caixa.height / 2;
      item.parentNode.insertBefore(arrastada, depois ? item.nextSibling : item);
    });
  }

  function salvarOrdem() {
    const ordem = [...lista.querySelectorAll('li')].map((item) => Number(item.dataset.id));
    // Mandamos a lista inteira, não "mova X para 3": dois arrastões seguidos se
    // cruzariam e deixariam a ordem em algo que ninguém pediu.
    comErro(() => api('/audio/order/', {
      method: 'PATCH',
      body: JSON.stringify({ order: ordem }),
    }).then(aplicar));
  }

  // ------------------------------------------------------------------ YouTube

  window.onYouTubeIframeAPIReady = () => {
    player = new YT.Player('pa-video', {
      height: '113',
      width: '200',
      playerVars: { playsinline: 1, controls: 0, disablekb: 1, rel: 0 },
      events: {
        onReady: () => {
          playerPronto = true;
          player.setVolume(volume);
          sincronizar();
        },
        onStateChange: (evento) => {
          // Só o mestre decide o que vem depois: se cada navegador escolhesse
          // sozinho, a mesa se espalharia em faixas diferentes.
          if (evento.data === YT.PlayerState.ENDED && SOU_MESTRE) proxima(true);
        },
      },
    });
  };

  function carregarApiDoYoutube() {
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(script);
  }

  function sincronizar() {
    if (!playerPronto || !estado) return;

    const atual = faixaAtual();
    if (!atual) {
      if (player.getPlayerState && player.getPlayerState() === YT.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      return;
    }

    const tocandoAgora = estado.is_playing && !estado.stale;
    const dados = player.getVideoData ? player.getVideoData() : {};
    const trocouDeFaixa = !dados || dados.video_id !== atual.youtube_id;

    if (trocouDeFaixa) {
      if (!liberadoPeloUsuario) {
        // Sem gesto do usuário o navegador recusaria o play. Deixamos a faixa
        // carregada e paramos aqui; o botão "Entrar no áudio" resolve.
        player.cueVideoById(atual.youtube_id, estado.position_seconds);
        mostrarAviso('Clique em "Entrar no áudio" para ouvir a trilha.');
        return;
      }
      player.loadVideoById(atual.youtube_id, estado.position_seconds);
      if (!tocandoAgora) player.pauseVideo();
      return;
    }

    if (!liberadoPeloUsuario) return;

    const posicaoLocal = player.getCurrentTime ? player.getCurrentTime() : 0;
    if (Math.abs(posicaoLocal - estado.position_seconds) > DESVIO_TOLERADO) {
      player.seekTo(estado.position_seconds, true);
    }

    const estadoLocal = player.getPlayerState();
    if (tocandoAgora && estadoLocal !== YT.PlayerState.PLAYING) player.playVideo();
    if (!tocandoAgora && estadoLocal === YT.PlayerState.PLAYING) player.pauseVideo();
  }

  // ------------------------------------------------------------------- estado

  function aplicar(corpo) {
    if (!corpo) return;
    estado = corpo.state;
    faixas = corpo.tracks;
    desenhar();
    sincronizar();
  }

  function comErro(acao) {
    mostrarAviso('');
    Promise.resolve()
      .then(acao)
      .catch((erro) => mostrarAviso(erro.message || 'Não deu certo.'));
  }

  function mandarEstado(mudancas) {
    comErro(() => api('/audio/state/', {
      method: 'PATCH',
      body: JSON.stringify(mudancas),
    }).then(aplicar));
  }

  function buscar() {
    comErro(() => api('/audio/').then(aplicar));
  }

  function proxima(automatico = false) {
    if (!faixas.length) return;
    const indice = indiceAtual();

    if (automatico && estado.loop_mode === 'ONE') {
      mandarEstado({ track: faixas[indice].id, position_seconds: 0, is_playing: true });
      return;
    }

    const seguinte = indice + 1;
    if (seguinte >= faixas.length) {
      if (estado.loop_mode === 'ALL') {
        mandarEstado({ track: faixas[0].id, position_seconds: 0, is_playing: true });
      } else if (automatico) {
        mandarEstado({ is_playing: false, position_seconds: 0 });
      }
      return;
    }

    mandarEstado({ track: faixas[seguinte].id, position_seconds: 0, is_playing: true });
  }

  function anterior() {
    if (!faixas.length) return;
    const indice = indiceAtual();
    const alvo = indice <= 0 ? faixas.length - 1 : indice - 1;
    mandarEstado({ track: faixas[alvo].id, position_seconds: 0, is_playing: true });
  }

  // ----------------------------------------------------------------- controles

  elemento('pa-topo').addEventListener('click', () => raiz.classList.toggle('recolhido'));

  elemento('pa-mudo').addEventListener('click', () => {
    mudo = !mudo;
    if (playerPronto) mudo ? player.mute() : player.unMute();
    elemento('pa-mudo').textContent = mudo ? '🔇' : '🔊';
  });

  elemento('pa-volume').addEventListener('input', (evento) => {
    volume = Number(evento.target.value);
    if (playerPronto) player.setVolume(volume);
  });

  if (SOU_MESTRE) {
    elemento('pa-tocar').addEventListener('click', () => {
      if (!estado) return;
      if (!estado.track && faixas.length) {
        mandarEstado({ track: faixas[0].id, position_seconds: 0, is_playing: true });
        return;
      }
      const posicao = playerPronto && player.getCurrentTime ? player.getCurrentTime() : 0;
      mandarEstado({ is_playing: !estado.is_playing, position_seconds: posicao });
    });

    elemento('pa-proxima').addEventListener('click', () => proxima(false));
    elemento('pa-anterior').addEventListener('click', anterior);

    elemento('pa-loop').addEventListener('click', () => {
      const roda = { OFF: 'ONE', ONE: 'ALL', ALL: 'OFF' };
      mandarEstado({ loop_mode: roda[estado ? estado.loop_mode : 'OFF'] });
    });

    elemento('pa-link').addEventListener('keydown', (evento) => {
      if (evento.key !== 'Enter') return;
      const url = evento.target.value.trim();
      if (!url) return;
      comErro(() => api('/audio/tracks/', {
        method: 'POST',
        body: JSON.stringify({ url }),
      }).then((corpo) => {
        evento.target.value = '';
        aplicar(corpo);
      }));
    });

    // O batimento é o que mantém o estado "quente". Sem ele o servidor conclui,
    // com razão, que a aba do mestre sumiu, e manda todo mundo parar.
    setInterval(() => {
      if (!estado || !estado.is_playing || !playerPronto) return;
      const posicao = player.getCurrentTime ? player.getCurrentTime() : 0;
      comErro(() => api('/audio/state/', {
        method: 'PATCH',
        body: JSON.stringify({ position_seconds: posicao, is_playing: true }),
      }).then((corpo) => { estado = corpo.state; faixas = corpo.tracks; }));
    }, INTERVALO_BATIMENTO);
  } else {
    elemento('pa-entrar').addEventListener('click', () => {
      liberadoPeloUsuario = true;
      mostrarAviso('');
      elemento('pa-entrar').style.display = 'none';
      sincronizar();
    });
  }

  // -------------------------------------------------------------- tempo real

  async function ligarPusher() {
    if (!PUSHER_KEY) return;

    // O canal é privado: o Pusher vai pedir uma assinatura ao nosso servidor
    // antes de deixar entrar, e é lá que se confere se a pessoa é da mesa.
    // Sem isso, qualquer um com a chave pública acompanharia a trilha de
    // qualquer campanha.
    const acesso = await pegarToken();

    const script = document.createElement('script');
    script.src = 'https://js.pusher.com/8.2/pusher.min.js';
    script.onload = () => {
      const pusher = new Pusher(PUSHER_KEY, {
        cluster: PUSHER_CLUSTER,
        authEndpoint: '/api/pusher/auth/',
        auth: { headers: { Authorization: `Bearer ${acesso}` } },
      });
      pusher.subscribe(`private-campanha-${CAMPANHA}-audio`).bind('audio', aplicar);
    };
    document.head.appendChild(script);
  }

  carregarApiDoYoutube();
  ligarPusher().catch(() => mostrarAviso('Tempo real indisponível; a trilha atualiza a cada 10s.'));
  buscar();
  // O polling continua mesmo com Pusher ligado: é o que salva a mesa se o
  // empurrão se perder, e de dez em dez segundos não pesa na cota do host.
  setInterval(buscar, INTERVALO_POLLING);
})();

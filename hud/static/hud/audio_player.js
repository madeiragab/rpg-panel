/* Player de áudio da campanha.
 *
 * Como funciona, em uma frase: o servidor guarda *o que* está tocando e *de
 * onde*, e cada navegador toca o vídeo por conta própria. Não há áudio saindo
 * do servidor — o que trafega é uma linha de estado.
 *
 * Quatro coisas que valem saber antes de mexer aqui:
 *
 * 1. Só o mestre escreve o estado da trilha. O jogador escreve uma coisa só: a
 *    presença dele. A regra de verdade está no servidor; isto aqui é a tela.
 *
 * 2. O navegador não deixa áudio começar sozinho. Por isso existe o botão
 *    "Entrar no áudio" — para todo mundo, mestre incluído: ele é o gesto humano
 *    que o navegador cobra antes do primeiro play, e é também o que põe o
 *    personagem da pessoa na roda de quem está ouvindo.
 *
 * 3. A posição não vem só do servidor: ela *anda* no cliente. Entre uma
 *    resposta e outra, o navegador soma o tempo que passou desde que recebeu, e
 *    compara com o que o vídeo dele está tocando. É isso que faz a mesa se
 *    juntar de volta sozinha depois de um anúncio, de um buffer ou de um
 *    notebook que dormiu — sem esperar o próximo `polling`.
 *
 * 4. O Pusher é acelerador, não mecanismo. Sem chave, ou com o Pusher fora do
 *    ar, o `polling` lento segura o player. Por isso ele nunca é desligado.
 */
(() => {
  const raiz = document.getElementById('player-audio');
  if (!raiz) return;

  const CAMPANHA = raiz.dataset.campanha;
  const SOU_MESTRE = raiz.dataset.mestre === '1';
  const MEU_ID = Number(raiz.dataset.eu);
  const PUSHER_KEY = raiz.dataset.pusherKey || '';
  const PUSHER_CLUSTER = raiz.dataset.pusherCluster || 'mt1';

  const INTERVALO_POLLING = 10000;   // rede de segurança, não o caminho normal
  const INTERVALO_BATIMENTO = 15000; // o mestre dizendo "ainda estou aqui"
  const INTERVALO_CONFERIDA = 1000;  // de quanto em quanto o cliente se compara
  const DESVIO_TOLERADO = 1.5;       // segundos antes de valer um seek
  const ESPERA_ENTRE_SEEKS = 2500;   // um seek por vez; ver `conferirDesvio`
  const ESPERA_PELO_SOM = 4000;      // até desconfiar que o navegador barrou

  const elemento = (id) => document.getElementById(id);
  const agora = elemento('pa-agora');
  const lista = elemento('pa-lista');
  const aviso = elemento('pa-aviso');
  const estadoCurto = elemento('pa-estado-curto');
  const rodaDeOuvintes = elemento('pa-ouvintes');
  const botaoEntrar = elemento('pa-entrar');
  const botaoSair = elemento('pa-sair');

  let token = null;
  let tokenExpiraEm = 0;
  let estado = null;
  let faixas = [];
  let ouvintes = [];
  let assinaturaDaRoda = null;
  let player = null;
  let playerPronto = false;

  /* A trilha tem que atravessar a troca de página.
   *
   * Cada clique no painel — abrir uma ficha, voltar para a campanha — recarrega
   * a página inteira e leva o player junto. Sem memória, a pessoa saía do áudio
   * a cada navegação e tinha que clicar de novo; numa sessão de RPG, que é
   * andar de ficha em ficha, isso é o tempo todo.
   *
   * `sessionStorage` é a memória com o prazo certo: ela sobrevive à navegação
   * dentro da aba e morre junto com a aba. Assim voltar para o painel amanhã
   * não começa a tocar música sozinho — e é por aba, então duas mesas abertas
   * lado a lado não se atrapalham.
   *
   * Isto está num try: aba anônima e navegador com armazenamento bloqueado
   * lançam no acesso, e uma trilha que não lembra é muito melhor do que um
   * player que não carrega. */
  const CHAVE_OUVINDO = `trilha:ouvindo:${CAMPANHA}`;
  const CHAVE_ABERTO = `trilha:aberto:${CAMPANHA}`;

  function lembrar(deposito, chave, ligado) {
    try {
      if (ligado) deposito.setItem(chave, '1');
      else deposito.removeItem(chave);
    } catch (erro) { /* sem memória: o player continua, só esquece */ }
  }

  function lembrado(deposito, chave) {
    try {
      return deposito.getItem(chave) === '1';
    } catch (erro) {
      return false;
    }
  }

  // A pessoa está no áudio agora. É o que libera o som — o navegador exige um
  // clique humano antes do primeiro play — e é o que põe o retrato dela na roda.
  // Já vem ligado quando a página anterior desta aba estava no áudio.
  let ouvindo = lembrado(sessionStorage, CHAVE_OUVINDO);

  let recebidoEm = 0;     // performance.now() de quando este estado chegou
  let ultimoSeek = 0;
  let paradoDesde = 0;    // desde quando devia estar tocando e não está
  let mudo = false;
  let volume = 60;

  // ---------------------------------------------------------------- utilidades

  /* O erro precisa aparecer com a gaveta fechada.
   *
   * O widget nasce recolhido, e o aviso mora lá no fim do corpo: um player
   * quebrado ficava quebrado em silêncio, e quem estava na mesa só sabia que
   * "não funcionou". A barra do topo assume a cor e a marca do erro, que é o
   * único pedaço que está sempre à vista. */
  function mostrarAviso(texto) {
    aviso.textContent = texto || '';
    raiz.classList.toggle('com-erro', !!texto);
    if (texto) estadoCurto.textContent = '⚠';
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

  function endereco(caminho) {
    return `/api/campaigns/${CAMPANHA}${caminho}`;
  }

  async function api(caminho, opcoes = {}) {
    const acesso = await pegarToken();
    const resposta = await fetch(endereco(caminho), {
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

  function tocandoAgora() {
    return !!(estado && estado.is_playing && !estado.stale);
  }

  /* Onde a faixa está *neste instante*, não onde estava quando a resposta saiu
     do servidor.

     O servidor já manda a posição corrigida pelo tempo que ele mesmo levou; o
     que falta é o tempo que passou aqui desde que a resposta chegou. Contamos
     com `performance.now()`, que anda sozinho, e não com o relógio do sistema:
     relógio de usuário erra em minutos, e um minuto de erro aqui viraria um
     seek para o meio da música a cada segundo. */
  function posicaoEsperada() {
    if (!estado) return 0;
    if (!tocandoAgora()) return estado.position_seconds;
    return estado.position_seconds + (performance.now() - recebidoEm) / 1000;
  }

  // ------------------------------------------------------------------ desenho

  function desenhar() {
    const atual = faixaAtual();
    agora.textContent = nomeDaFaixa(atual);
    if (raiz.classList.contains('com-erro')) {
      estadoCurto.textContent = '⚠';
    } else {
      const simbolo = tocandoAgora() ? '▶' : '⏸';
      estadoCurto.textContent = ouvintes.length
        ? `${simbolo} ${ouvintes.length}👤`
        : simbolo;
    }

    botaoEntrar.hidden = ouvindo;
    botaoSair.hidden = !ouvindo;
    // Quem ainda não entrou precisa saber que está perdendo alguma coisa. O
    // recado vai no próprio botão, e não no aviso: o aviso é onde os erros
    // aparecem, e um dos dois apagaria o outro a cada volta do polling.
    botaoEntrar.textContent = tocandoAgora() ? 'Entrar no áudio ▶' : 'Entrar no áudio';
    botaoEntrar.classList.toggle('chamando', tocandoAgora());
    // O widget nasce recolhido, e um botão dentro de uma gaveta fechada não
    // convida ninguém. Recolhido e com a mesa tocando, a barra chama.
    raiz.classList.toggle('chamando', tocandoAgora() && !ouvindo);

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
        tocarEsta.onclick = () => comandoDoMestre(
          () => mandarEstado({ track: faixa.id, position_seconds: 0, is_playing: true }),
        );
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

  /* A roda de quem está ouvindo.

     Só é redesenhada quando muda de gente: o `polling` traz a lista a cada dez
     segundos, e refazer os retratos a cada volta faria as fotos piscarem na
     tela de todo mundo por nada. */
  function desenharOuvintes() {
    const assinatura = JSON.stringify(
      ouvintes.map((o) => [o.user_id, o.name, o.image, o.is_master]),
    );
    if (assinatura === assinaturaDaRoda) return;
    assinaturaDaRoda = assinatura;

    rodaDeOuvintes.innerHTML = '';

    if (!ouvintes.length) {
      const vazio = document.createElement('span');
      vazio.className = 'pa-ninguem';
      vazio.textContent = 'Ninguém no áudio ainda.';
      rodaDeOuvintes.appendChild(vazio);
      return;
    }

    ouvintes.forEach((pessoa) => {
      const caixa = document.createElement('div');
      caixa.className = 'pa-ouvinte';
      if (pessoa.is_master) caixa.classList.add('mestre');
      if (pessoa.user_id === MEU_ID) caixa.classList.add('eu');
      caixa.title = pessoa.is_master ? `${pessoa.name} (mestre)` : pessoa.name;

      // As mesmas classes e os mesmos data-* das outras molduras do painel: o
      // portrait.js posiciona a foto com o corte que o dono escolheu, e o
      // retrato aqui fica igual ao da ficha em vez de cortado pelo meio.
      const moldura = document.createElement('div');
      moldura.className = 'portrait-thumb redondo minusculo';
      moldura.setAttribute('data-portrait-frame', '');
      moldura.dataset.encaixe = 'preencher';
      moldura.dataset.zoom = pessoa.zoom;
      moldura.dataset.focusX = pessoa.focus_x;
      moldura.dataset.focusY = pessoa.focus_y;

      if (pessoa.image) {
        const foto = document.createElement('img');
        foto.src = pessoa.image;
        foto.alt = pessoa.name;
        moldura.appendChild(foto);
      } else {
        moldura.classList.add('empty');
        const inicial = document.createElement('span');
        inicial.className = 'pa-inicial';
        inicial.textContent = (pessoa.name || '?').trim().charAt(0).toUpperCase();
        caixa.appendChild(inicial);
      }

      caixa.insertBefore(moldura, caixa.firstChild);
      rodaDeOuvintes.appendChild(caixa);
    });

    if (window.hudPortrait) window.hudPortrait.prepararTodas(rodaDeOuvintes);
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
          // Voltar a tocar é o fim de alguma interrupção — um anúncio, um
          // buffer, a faixa que acabou de carregar. É o melhor momento para
          // conferir onde a mesa está: a API não avisa quando um anúncio
          // começa ou termina, mas avisa isto.
          if (evento.data === YT.PlayerState.PLAYING) conferirDesvio();

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

  function videoCarregado() {
    const dados = playerPronto && player.getVideoData ? player.getVideoData() : null;
    return dados ? dados.video_id : null;
  }

  /* Põe o player na faixa certa. Trocar de vídeo é o caso pesado — recarrega o
     iframe — então ele acontece aqui, e o acerto fino de posição fica com o
     `conferirDesvio`, que roda de segundo em segundo. */
  function sincronizar() {
    if (!playerPronto || !estado) return;

    const atual = faixaAtual();
    if (!atual) {
      if (player.getPlayerState && player.getPlayerState() === YT.PlayerState.PLAYING) {
        player.pauseVideo();
      }
      return;
    }

    const trocouDeFaixa = videoCarregado() !== atual.youtube_id;

    if (trocouDeFaixa) {
      if (!ouvindo) {
        // Sem gesto do usuário o navegador recusaria o play. Deixamos a faixa
        // engatilhada e paramos aqui; o botão "Entrar no áudio" resolve.
        player.cueVideoById(atual.youtube_id, posicaoEsperada());
        return;
      }
      ultimoSeek = performance.now();
      player.loadVideoById(atual.youtube_id, posicaoEsperada());
      if (!tocandoAgora()) player.pauseVideo();
      return;
    }

    if (!ouvindo) return;
    conferirDesvio();
  }

  /* O acerto fino, uma vez por segundo.
   *
   * Este é o pedaço que faz a mesa ouvir a mesma coisa. O navegador compara o
   * segundo que ele está tocando com o segundo em que a mesa está e, se a
   * diferença passar do tolerado, pula para lá.
   *
   * Anúncio é o caso que ele resolve calado. Durante um, o YouTube reporta o
   * tempo do anúncio e ignora o `seekTo` — quem estiver vendo propaganda
   * apareceria como "fora de sincronia" e receberia um pulo por segundo que não
   * ia a lugar nenhum. Por isso a espera entre seeks: durante o anúncio as
   * tentativas ficam raras e inofensivas, e no instante em que ele acaba a
   * primeira delas cai em pé, no segundo onde o resto da mesa está.
   *
   * A tolerância existe pelo motivo oposto: corrigir meio segundo soaria como
   * um engasgo a cada volta, e um segundo e meio de trilha ambiente ninguém
   * numa mesa de RPG percebe. */
  function conferirDesvio() {
    if (!playerPronto || !ouvindo || !estado) return;

    const atual = faixaAtual();
    if (!atual) return;

    // Faixa errada carregada é assunto do `sincronizar`, que troca o vídeo.
    if (videoCarregado() !== atual.youtube_id) {
      sincronizar();
      return;
    }

    const estadoLocal = player.getPlayerState();

    if (!tocandoAgora()) {
      if (estadoLocal === YT.PlayerState.PLAYING) player.pauseVideo();
      paradoDesde = 0;
      return;
    }

    const alvo = posicaoEsperada();
    const local = player.getCurrentTime ? player.getCurrentTime() : 0;

    if (Math.abs(local - alvo) > DESVIO_TOLERADO
        && performance.now() - ultimoSeek > ESPERA_ENTRE_SEEKS) {
      ultimoSeek = performance.now();
      player.seekTo(alvo, true);
    }

    /* `playVideo()` não devolve erro quando o navegador recusa: ele
       simplesmente não acontece. A única forma de saber é insistir e olhar o
       relógio — se a mesa está tocando e este player continua parado depois de
       alguns segundos, o clique não valeu como gesto.

       O recado é "clique em qualquer lugar", e não "clique aqui de novo",
       porque é isso que resolve: um clique qualquer na página libera o áudio, e
       a tentativa do segundo seguinte já entra. Insistir também cobre o caso
       oposto — vídeo que demora a carregar não é bloqueio, e some sozinho. */
    if (estadoLocal !== YT.PlayerState.PLAYING
        && estadoLocal !== YT.PlayerState.BUFFERING) {
      player.playVideo();
      if (!paradoDesde) paradoDesde = performance.now();
      if (performance.now() - paradoDesde > ESPERA_PELO_SOM) {
        mostrarAviso('O navegador barrou o som. Clique em qualquer lugar da página.');
      }
    } else if (paradoDesde) {
      paradoDesde = 0;
      mostrarAviso('');
    }
  }

  // ------------------------------------------------------------------- estado

  function aplicar(corpo) {
    if (!corpo) return;
    // A hora de chegada é a âncora de tudo que o `posicaoEsperada` calcula
    // depois; marcá-la antes de desenhar mantém a conta honesta.
    recebidoEm = performance.now();
    estado = corpo.state;
    faixas = corpo.tracks;
    if (corpo.listeners) ouvintes = corpo.listeners;
    desenhar();
    desenharOuvintes();
    sincronizar();
  }

  function comErro(acao) {
    mostrarAviso('');
    Promise.resolve()
      .then(acao)
      .catch((erro) => mostrarAviso(erro.message || 'Não deu certo.'));
  }

  function mandarEstado(mudancas) {
    return api('/audio/state/', {
      method: 'PATCH',
      body: JSON.stringify(mudancas),
    }).then(aplicar);
  }

  /* A volta do polling.
   *
   * Quem está no áudio busca pelo endereço da presença, e não pelo do estado.
   * Os dois devolvem o mesmo corpo — o de presença só carimba o `last_seen` de
   * quebra. Com isso o batimento e o polling viram **uma requisição só** em vez
   * de duas: numa mesa de seis pessoas é a diferença entre 60 e 36 pedidos por
   * minuto, e num host de plano grátis essa conta é a que decide se o painel
   * fica de pé no meio da sessão. */
  function buscar() {
    comErro(() => (ouvindo ? mandarPresenca(true) : api('/audio/').then(aplicar)));
  }

  function proxima(automatico = false) {
    if (!faixas.length) return;
    const indice = indiceAtual();

    if (automatico && estado.loop_mode === 'ONE') {
      comErro(() => mandarEstado({ track: faixas[indice].id, position_seconds: 0, is_playing: true }));
      return;
    }

    const seguinte = indice + 1;
    if (seguinte >= faixas.length) {
      if (estado.loop_mode === 'ALL') {
        comErro(() => mandarEstado({ track: faixas[0].id, position_seconds: 0, is_playing: true }));
      } else if (automatico) {
        comErro(() => mandarEstado({ is_playing: false, position_seconds: 0 }));
      }
      return;
    }

    comErro(() => mandarEstado({ track: faixas[seguinte].id, position_seconds: 0, is_playing: true }));
  }

  function anterior() {
    if (!faixas.length) return;
    const indice = indiceAtual();
    const alvo = indice <= 0 ? faixas.length - 1 : indice - 1;
    comErro(() => mandarEstado({ track: faixas[alvo].id, position_seconds: 0, is_playing: true }));
  }

  // ----------------------------------------------------------------- presença

  function mandarPresenca(ligado) {
    return api('/audio/presence/', {
      method: 'POST',
      body: JSON.stringify({ listening: ligado }),
    }).then(aplicar);
  }

  function entrar() {
    if (ouvindo) return;
    ouvindo = true;
    lembrar(sessionStorage, CHAVE_OUVINDO, true);
    mostrarAviso('');
    desenhar();
    // O play tem que sair de dentro do clique, antes de qualquer `await`: o
    // navegador só reconhece o gesto enquanto o handler está rodando.
    sincronizar();
    comErro(() => mandarPresenca(true));
  }

  function sair() {
    ouvindo = false;
    paradoDesde = 0;
    lembrar(sessionStorage, CHAVE_OUVINDO, false);
    // Sair é decisão da pessoa, e ela vale para as próximas páginas também: sem
    // apagar a memória aqui, a navegação seguinte a colocaria de volta no áudio
    // que ela acabou de deixar.
    if (playerPronto && player.pauseVideo) player.pauseVideo();
    desenhar();
    comErro(() => mandarPresenca(false));
  }

  /* Mexer nos controles é entrar no áudio.
   *
   * O mestre não deveria ter que clicar em dois botões para ouvir a própria
   * trilha, e o clique dele nos controles serve de gesto tão bem quanto o
   * outro. Entrar antes de mandar o comando também acerta a ordem: a resposta
   * do servidor já vem com ele na roda. */
  function comandoDoMestre(acao) {
    if (!ouvindo) entrar();
    comErro(acao);
  }

  botaoEntrar.addEventListener('click', entrar);
  botaoSair.addEventListener('click', sair);

  /* Aba que fecha some da roda na hora, e não daqui a quarenta e cinco segundos.
     `keepalive` é o que deixa o pedido sair de uma página que está morrendo;
     sem ele o navegador cancela a saída no meio. Se falhar, não faz mal: o
     `last_seen` velho tira a pessoa da roda sozinho. */
  // ----------------------------------------------------------------- controles

  /* Abrir e fechar a gaveta é preferência, e preferência atravessa a sessão —
     por isso `localStorage` aqui, e `sessionStorage` para o "estou no áudio".
     Quem abriu a trilha não quer ela fechada de novo em cada página.

     A chave guarda o **aberto**, e não o recolhido: sem chave nenhuma vale o
     que o template mandou, que é nascer recolhida. Guardar o contrário faria a
     ausência de preferência e a preferência "fechado" ficarem indistinguíveis. */
  if (lembrado(localStorage, CHAVE_ABERTO)) raiz.classList.remove('recolhido');

  elemento('pa-topo').addEventListener('click', () => {
    raiz.classList.toggle('recolhido');
    lembrar(localStorage, CHAVE_ABERTO, !raiz.classList.contains('recolhido'));
  });

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
        comandoDoMestre(() => mandarEstado({ track: faixas[0].id, position_seconds: 0, is_playing: true }));
        return;
      }
      // A posição que vale é a do player do mestre quando ele tem uma: é o
      // relógio da mesa. Sem player pronto, a última que o servidor conhece.
      const posicao = playerPronto && player.getCurrentTime
        ? player.getCurrentTime()
        : posicaoEsperada();
      comandoDoMestre(() => mandarEstado({ is_playing: !estado.is_playing, position_seconds: posicao }));
    });

    elemento('pa-proxima').addEventListener('click', () => {
      if (!ouvindo) entrar();
      proxima(false);
    });
    elemento('pa-anterior').addEventListener('click', () => {
      if (!ouvindo) entrar();
      anterior();
    });

    elemento('pa-loop').addEventListener('click', () => {
      const roda = { OFF: 'ONE', ONE: 'ALL', ALL: 'OFF' };
      comErro(() => mandarEstado({ loop_mode: roda[estado ? estado.loop_mode : 'OFF'] }));
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

    /* O batimento do mestre é o que mantém o estado "quente" e o que corrige a
       posição da mesa: o servidor extrapola a partir do último que chegou.
       Sem ele o servidor conclui, com razão, que a aba do mestre sumiu, e manda
       todo mundo parar. */
    setInterval(() => {
      if (!estado || !estado.is_playing || !playerPronto) return;
      const posicao = player.getCurrentTime ? player.getCurrentTime() : 0;
      comErro(() => api('/audio/state/', {
        method: 'PATCH',
        body: JSON.stringify({ position_seconds: posicao, is_playing: true }),
      }).then(aplicar));
    }, INTERVALO_BATIMENTO);
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
  // A conferida é local e não fala com o servidor: é ela que junta de volta
  // quem ficou para trás num anúncio, sem esperar a próxima resposta.
  setInterval(conferirDesvio, INTERVALO_CONFERIDA);

  /* Aba escondida tem `setInterval` estrangulado pelo navegador — vira um
     disparo por minuto — e o vídeo continua tocando. Quando ela volta, a
     posição pode estar longe: conferimos na hora, sem esperar o próximo tique.
     Um notebook que dormiu volta pelo mesmo caminho. */
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    buscar();
  });

  /* O primeiro clique da página nova destrava o som.
   *
   * Quem atravessa a troca de página volta no áudio sem clicar em nada, e aí
   * depende de o navegador aceitar tocar sem gesto — o Chrome costuma aceitar
   * num site onde a pessoa já ouviu música antes, o Firefox costuma não. Quando
   * não aceita, a conferida de cada segundo tenta e falha em silêncio até
   * aparecer um gesto qualquer.
   *
   * Este ouvinte transforma o primeiro clique em qualquer lugar do painel —
   * abrir uma aba, mexer numa barra — no gesto que faltava, sem que a pessoa
   * precise achar o botão da trilha. É o que o aviso manda fazer. */
  document.addEventListener('click', () => {
    if (ouvindo) conferirDesvio();
  }, { capture: true });
})();

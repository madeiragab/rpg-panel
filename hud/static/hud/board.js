/* O quadro da campanha: arrastar as peças e mexer nas barras sem sair dali.

   A posição vai para o servidor em fração do quadro (0 a 1), e não em pixel.
   O mestre arruma a mesa no monitor grande e o mesmo arranjo continua de pé no
   notebook — em pixel, metade das peças cairia fora da tela.

   As barras não têm rota única: personagem, NPC e inimigo respondem em
   endereços de formato diferente. Cada botão já vem com o seu, então o código
   aqui não precisa saber de qual dos três a peça é. */
(() => {
  const quadro = document.getElementById('quadro');
  if (!quadro) return;

  const urlMover = quadro.dataset.moveUrl;
  const entre = (n, min, max) => Math.min(Math.max(n, min), max);

  function csrf() {
    if (window.hudConfig && window.hudConfig.csrfToken) return window.hudConfig.csrfToken;
    const campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
  }

  /* ------------------------------------------------------------ arrastar -- */

  let arrasto = null;

  function guardarPosicao(peca) {
    if (!urlMover) return;
    const corpo = new URLSearchParams();
    corpo.append('kind', peca.dataset.kind);
    corpo.append('id', peca.dataset.id);
    corpo.append('x', peca.dataset.x);
    corpo.append('y', peca.dataset.y);
    fetch(urlMover, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
      body: corpo,
    }).catch(() => {});
  }

  function ligarArraste(peca) {
    peca.addEventListener('pointerdown', (e) => {
      // Botão, link e controle de zoom continuam clicáveis: sem esta saída, o
      // arraste engoliria o clique de todos eles.
      if (e.target.closest('button, a, input, textarea, [data-portrait-frame].editavel')) return;
      const caixa = quadro.getBoundingClientRect();
      const dela = peca.getBoundingClientRect();
      arrasto = {
        peca,
        // Onde dentro da peça o dedo pegou: sem isso ela pula com o centro no
        // cursor no primeiro pixel de movimento.
        dx: e.clientX - (dela.left + dela.width / 2),
        dy: e.clientY - (dela.top + dela.height / 2),
        caixa,
      };
      peca.setPointerCapture(e.pointerId);
      peca.classList.add('arrastando');
      e.preventDefault();
    });

    peca.addEventListener('pointermove', (e) => {
      if (!arrasto || arrasto.peca !== peca) return;
      const { caixa, dx, dy } = arrasto;
      const x = entre((e.clientX - dx - caixa.left) / caixa.width, 0, 1);
      const y = entre((e.clientY - dy - caixa.top) / caixa.height, 0, 1);
      peca.dataset.x = x.toFixed(4);
      peca.dataset.y = y.toFixed(4);
      peca.style.left = `${(x * 100).toFixed(2)}%`;
      peca.style.top = `${(y * 100).toFixed(2)}%`;
      e.preventDefault();
    });

    const soltar = () => {
      if (!arrasto || arrasto.peca !== peca) return;
      arrasto = null;
      peca.classList.remove('arrastando');
      if (peca.dataset.x !== undefined) guardarPosicao(peca);
    };
    peca.addEventListener('pointerup', soltar);
    peca.addEventListener('pointercancel', soltar);
  }

  /* --------------------------------------------------------------- barras -- */

  function ligarBotaoDeBarra(botao) {
    botao.addEventListener('click', () => {
      const barra = botao.closest('.peca-barra');
      const corpo = new URLSearchParams();
      corpo.append('action', botao.dataset.acao);
      corpo.append('amount', botao.dataset.passo);

      fetch(botao.dataset.barraUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
        body: corpo,
      })
        .then((r) => r.json())
        .then((data) => {
          if (!data.success || !barra) return;
          // Quem pinta é o bars.js, e é ele que sabe de todas as cópias desta
          // barra na página. O quadro só repassa o valor que voltou.
          if (window.hudBarras) {
            window.hudBarras.aplicarUm(barra.dataset.barKind, barra.dataset.barId, data.current);
          }
        })
        .catch(() => {});
    });
  }

  /* Os botões da barra nascem recolhidos. Uma peça com três barras abertas é
     uma coluna de doze botões, e na maior parte da sessão só se olha o valor —
     mas quem abriu uma barra para o combate não quer que ela feche sozinha no
     F5 seguinte, então o que está aberto fica guardado no navegador. */
  const CHAVE_ABERTAS = 'hud:barras-abertas';

  function abertas() {
    try {
      const guardado = JSON.parse(localStorage.getItem(CHAVE_ABERTAS) || '[]');
      return new Set(Array.isArray(guardado) ? guardado : []);
    } catch (e) {
      return new Set();
    }
  }

  function guardarAbertas(conjunto) {
    try {
      localStorage.setItem(CHAVE_ABERTAS, JSON.stringify([...conjunto]));
    } catch (e) {
      /* Navegador sem armazenamento: a barra abre e fecha do mesmo jeito. */
    }
  }

  function ligarAbrirBarra(cabeca) {
    const barra = cabeca.closest('.peca-barra');
    const botoes = barra && barra.querySelector('.peca-barra-botoes');
    if (!botoes) return;

    const nome = `${barra.dataset.barKind}:${barra.dataset.barId}`;
    const mostrar = (aberta) => {
      botoes.hidden = !aberta;
      cabeca.setAttribute('aria-expanded', aberta ? 'true' : 'false');
      barra.classList.toggle('aberta', aberta);
      cabeca.title = aberta ? 'Recolher os botões desta barra' : 'Abrir os botões desta barra';
    };

    mostrar(abertas().has(nome));

    cabeca.addEventListener('click', () => {
      const abrindo = botoes.hidden;
      mostrar(abrindo);
      const guardadas = abertas();
      if (abrindo) guardadas.add(nome);
      else guardadas.delete(nome);
      guardarAbertas(guardadas);
    });
  }

  /* -------------------------------------------------------------- post-it -- */

  /* O texto salva sozinho: post-it com botão "salvar" não é post-it. A espera
     evita um POST por tecla, e o blur fecha a conta na hora de sair — quem
     escreve e troca de aba não pode perder o que digitou. */
  function ligarPostIt(campo) {
    let agendado = null;

    /* Manda só o que mudou. O servidor grava campo a campo justamente para
       isto: um pedido de tamanho não pode carregar um texto vazio junto e
       apagar a anotação. */
    function guardar(dados) {
      clearTimeout(agendado);
      const corpo = new URLSearchParams();
      Object.entries(dados).forEach(([chave, valor]) => corpo.append(chave, valor));
      return fetch(campo.dataset.salvarUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
        body: corpo,
      }).catch(() => {});
    }

    function guardarTexto() {
      guardar({ text: campo.value }).then(() => campo.classList.remove('sujo'));
    }

    campo.addEventListener('input', () => {
      campo.classList.add('sujo');
      clearTimeout(agendado);
      agendado = setTimeout(guardarTexto, 700);
    });
    campo.addEventListener('blur', () => {
      if (campo.classList.contains('sujo')) guardarTexto();
    });

    /* O tamanho é escolhido arrastando o canto, e o navegador não avisa quando
       o arraste acaba — só que o elemento mudou de tamanho, dezenas de vezes
       por segundo. A espera é o que transforma isso num POST só, no tamanho em
       que a pessoa parou.

       O primeiro disparo do ResizeObserver é o do próprio layout inicial, e não
       um arraste: guardá-lo mandaria um POST por post-it toda vez que o quadro
       abrisse. Por isso a primeira medida só é anotada. */
    if (!('ResizeObserver' in window)) return;

    let ultimo = null;
    let esperando = null;

    new ResizeObserver(() => {
      const largura = Math.round(campo.offsetWidth);
      const altura = Math.round(campo.offsetHeight);
      if (!largura || !altura) return;

      const medida = `${largura}x${altura}`;
      if (ultimo === null) { ultimo = medida; return; }
      if (medida === ultimo) return;
      ultimo = medida;

      clearTimeout(esperando);
      esperando = setTimeout(() => guardar({ width: largura, height: altura }), 500);
    }).observe(campo);
  }

  /* ------------------------------------------------- enquadrar a polaroid -- */

  /* A foto ocupa quase toda a polaroid. Se a moldura fosse sempre arrastável
     não sobraria onde pegar para mover a peça, então o enquadramento entra e
     sai por botão: ligado, a moldura ganha o data-save-url e o portrait.js
     passa a tratá-la como editor. */
  function ligarEnquadrar(botao) {
    const peca = botao.closest('.peca');
    const moldura = peca && peca.querySelector('[data-portrait-frame]');
    if (!moldura) return;

    botao.addEventListener('click', () => {
      const ligando = !moldura.dataset.saveUrl;
      if (ligando) {
        moldura.dataset.saveUrl = botao.dataset.enquadrar;
      } else {
        delete moldura.dataset.saveUrl;
      }
      peca.classList.toggle('enquadrando', ligando);
      botao.classList.toggle('ligado', ligando);
      botao.title = ligando ? 'Terminar o enquadramento' : 'Ajustar o pedaço da foto que aparece';
      if (window.hudPortrait) window.hudPortrait.preparar(moldura);
    });
  }

  /* Uma peça pregada agora tem que ganhar os mesmos eventos das que vieram no
     HTML. É por aqui que o ajax.js apresenta a recém-chegada. */
  function registrar(peca) {
    if (!peca || !peca.classList || !peca.classList.contains('peca')) return;
    ligarArraste(peca);
    peca.querySelectorAll('[data-barra-url]').forEach(ligarBotaoDeBarra);
    peca.querySelectorAll('[data-abrir-barra]').forEach(ligarAbrirBarra);
    peca.querySelectorAll('.post-it-texto').forEach(ligarPostIt);
    peca.querySelectorAll('[data-enquadrar]').forEach(ligarEnquadrar);
    const vazio = quadro.querySelector('.quadro-vazio');
    if (vazio) vazio.remove();
  }

  /* ------------------------------------------- a altura do quadro -- */

  /* O quadro enche a tela sozinho.
   *
   * Antes ele tinha uma altura fixa em `vh` e uma alça de `resize` para o resto,
   * e a alça era ruim de usar por um motivo estrutural: ela fica na borda de
   * baixo, então esticar empurra a alça para fora da tela e a rolagem assume no
   * meio do arrasto. Dava para crescer meia tela por vez, soltando e repetindo.
   *
   * Medir é melhor do que adivinhar: `vh` não sabe quanto o título, as abas e o
   * texto de ajuda comeram acima do quadro, e essa altura muda de tela para
   * tela. `getBoundingClientRect().top` sabe.
   *
   * A alça continua ali para quem quiser um quadro maior que a tela — e agora a
   * altura escolhida fica guardada. É preferência de quem olha, não do quadro:
   * a posição das peças é fração, então o arranjo é o mesmo em qualquer altura,
   * e cada um pode ver a mesa no tamanho que couber no monitor dele. */
  const CHAVE_ALTURA = `quadro:altura:${quadro.dataset.campanha || 'x'}`;
  const RESPIRO_ABAIXO = 16;
  const ALTURA_MINIMA = 320;

  let alturaQueAplicamos = 0;

  function alturaGuardada() {
    try {
      return Number(localStorage.getItem(CHAVE_ALTURA)) || 0;
    } catch (erro) {
      return 0;
    }
  }

  function guardarAltura(px) {
    try {
      localStorage.setItem(CHAVE_ALTURA, String(px));
    } catch (erro) { /* sem memória: o quadro continua, só esquece */ }
  }

  function aplicarAltura(px) {
    alturaQueAplicamos = Math.round(px);
    // O `min-height` do CSS é o que segura o quadro sem JS. Daqui em diante
    // quem manda é a medida, e um piso em `vh` só brigaria com ela numa tela
    // baixa — devolvendo a rolagem que este código existe para tirar.
    quadro.style.minHeight = '0px';
    quadro.style.height = `${alturaQueAplicamos}px`;
  }

  /* Quanto sobra do começo do quadro até o fim do painel.
   *
   * A conta é contra o painel rolável, e não contra a janela, porque só ela é
   * estável: medir `window.innerHeight - rect.top` daria uma altura diferente
   * conforme o painel estivesse rolado — o quadro cresceria ao rolar para baixo
   * e sobraria ao voltar. Somar o `scrollTop` desfaz a rolagem da conta e
   * devolve a posição do quadro dentro do painel, que não muda. */
  function espacoDisponivel() {
    const painel = quadro.closest('.content');
    if (!painel) return window.innerHeight - quadro.getBoundingClientRect().top;
    const dentro = quadro.getBoundingClientRect().top
      - painel.getBoundingClientRect().top
      + painel.scrollTop;
    return painel.clientHeight - dentro;
  }

  function ajustarAltura() {
    const escolhida = alturaGuardada();
    if (escolhida) {
      aplicarAltura(escolhida);
      return;
    }
    // Aba fechada não tem medida: `offsetParent` nulo é o sinal disso, e um
    // quadro de altura zero não volta sozinho. É o clique na aba que chama
    // isto de novo, aí sim com a medida de verdade.
    if (!quadro.offsetParent) return;
    aplicarAltura(Math.max(espacoDisponivel() - RESPIRO_ABAIXO, ALTURA_MINIMA));
  }

  if ('ResizeObserver' in window) {
    new ResizeObserver(() => {
      const agora = Math.round(quadro.offsetHeight);
      if (!agora) return;
      // Um pixel de diferença é arredondamento nosso, não escolha de ninguém.
      if (Math.abs(agora - alturaQueAplicamos) <= 1) return;
      alturaQueAplicamos = agora;
      guardarAltura(agora);
    }).observe(quadro);
  }

  window.addEventListener('resize', ajustarAltura);
  ajustarAltura();

  quadro.querySelectorAll('.peca').forEach(ligarArraste);
  quadro.querySelectorAll('[data-barra-url]').forEach(ligarBotaoDeBarra);
  quadro.querySelectorAll('[data-abrir-barra]').forEach(ligarAbrirBarra);
  quadro.querySelectorAll('.post-it-texto').forEach(ligarPostIt);
  quadro.querySelectorAll('[data-enquadrar]').forEach(ligarEnquadrar);

  window.hudQuadro = { registrar, ajustarAltura };
})();

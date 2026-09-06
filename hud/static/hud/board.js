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

  quadro.querySelectorAll('.peca').forEach((peca) => {
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
  });

  /* --------------------------------------------------------------- barras -- */

  quadro.querySelectorAll('[data-barra-url]').forEach((botao) => {
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
          const valor = barra.querySelector('.peca-barra-valor');
          const cheia = barra.querySelector('.peca-barra-cheia');
          const maximo = Number(valor.dataset.max) || 1;
          valor.textContent = `${data.current} / ${maximo}`;
          cheia.style.width = `${entre((data.current / maximo) * 100, 0, 100)}%`;
        })
        .catch(() => {});
    });
  });

  /* -------------------------------------------------------------- post-it -- */

  /* O texto salva sozinho: post-it com botão "salvar" não é post-it. A espera
     evita um POST por tecla, e o blur fecha a conta na hora de sair — quem
     escreve e troca de aba não pode perder o que digitou. */
  quadro.querySelectorAll('.post-it-texto').forEach((campo) => {
    let agendado = null;

    function guardar() {
      clearTimeout(agendado);
      const corpo = new URLSearchParams();
      corpo.append('text', campo.value);
      fetch(campo.dataset.salvarUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
        body: corpo,
      })
        .then(() => campo.classList.remove('sujo'))
        .catch(() => {});
    }

    campo.addEventListener('input', () => {
      campo.classList.add('sujo');
      clearTimeout(agendado);
      agendado = setTimeout(guardar, 700);
    });
    campo.addEventListener('blur', () => {
      if (campo.classList.contains('sujo')) guardar();
    });
  });

  /* ------------------------------------------------- enquadrar a polaroid -- */

  /* A foto ocupa quase toda a polaroid. Se a moldura fosse sempre arrastável
     não sobraria onde pegar para mover a peça, então o enquadramento entra e
     sai por botão: ligado, a moldura ganha o data-save-url e o portrait.js
     passa a tratá-la como editor. */
  quadro.querySelectorAll('[data-enquadrar]').forEach((botao) => {
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
  });
})();

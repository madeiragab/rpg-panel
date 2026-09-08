/* Uma barra, um valor — em toda parte ao mesmo tempo.

   A mesma vida aparece em três lugares: na ficha do jogador, na ficha aberta
   pelo mestre e na peça do quadro. Antes, cada página só sabia do clique que
   ela mesma tinha dado: o mestre tirava cinco de vida no quadro e o jogador
   continuava a sessão inteira olhando o número velho, até apertar F5.

   O jeito certo seria o servidor avisar, e é o que o áudio faz pelo Pusher.
   Aqui não dá para contar com isso: o Pusher é opcional neste projeto e no
   servidor da campanha ele não está configurado. Então a página pergunta, de
   poucos em poucos segundos, e só pelo que está na tela dela.

   Duas economias importam. Aba escondida não pergunta nada — a sessão fica
   horas aberta atrás de outra janela; e o valor que acabou de voltar de um
   clique já é aplicado na hora, sem esperar a próxima rodada.

   O banco é a fonte da verdade. Esta resposta nunca inventa nada: ela repete
   o que o servidor respondeu, e é por isso que os três lugares acabam
   idênticos mesmo quando dois deles mexeram na mesma barra. */
(() => {
  const INTERVALO = 4000;

  const entre = (n, min, max) => Math.min(Math.max(n, min), max);

  /* Cada barra é achada por tipo + id: o id sozinho não distingue a barra 3 de
     um personagem da barra 3 de um inimigo, e no quadro as duas convivem. */
  function elementos(tipo, id) {
    return document.querySelectorAll(
      `[data-bar-kind="${tipo}"][data-bar-id="${id}"]`,
    );
  }

  /* Onde o retrato do personagem troca de cara. As duas frações são as mesmas
     do `estado_do_retrato` no models.py: metade da vida deixa o personagem
     ferido, um quarto o deixa gravemente ferido. A conta existe também aqui
     para o rosto mudar no mesmo clique que tirou a vida — sem isso ele só
     mudaria no F5 seguinte. */
  const FRACAO_DE_FERIDO = 0.5;
  const FRACAO_DE_GRAVE = 0.25;

  function trocarRetratoDaVida(elo, atual, teto) {
    const moldura = document.querySelector('[data-retrato-principal] [data-portrait-frame]');
    const foto = moldura && moldura.querySelector('img');
    if (!foto) return;   // ficha sem retrato: não há rosto para trocar

    // Vida temporária passa do máximo, e aí a fração passa de 1: ninguém fica
    // ferido por ganhar vida.
    const fracao = teto > 0 ? atual / teto : 1;
    let url = elo.dataset.retratoInteiro;
    if (fracao <= FRACAO_DE_GRAVE) url = elo.dataset.retratoGrave;
    else if (fracao <= FRACAO_DE_FERIDO) url = elo.dataset.retratoFerido;

    if (!url || foto.getAttribute('src') === url) return;
    foto.src = url;
    if (window.hudPortrait) window.hudPortrait.preparar(moldura);
  }

  /* As duas fatias do trilho, na mesma conta do `BarraDeFicha` do models.py.

     O valor atual pode passar do máximo — a habilidade que dá vida temporária
     deixa o personagem em 15/12 — e nesse caso o trilho passa a valer 15: os
     12 de vida de verdade ocupam 80% dele e os 3 de sobra ocupam o resto, na
     cor oposta que o servidor já escolheu. */
  function fatias(atual, teto) {
    const total = Math.max(atual, teto, 1);
    return {
      base: (entre(Math.min(atual, teto), 0, total) * 100) / total,
      extra: (Math.max(atual - teto, 0) * 100) / total,
    };
  }

  function pintar(barra, atual, maximo) {
    const teto = Number(maximo) || 1;

    // O elo entre a barra de vida e o retrato da ficha: ele não desenha barra
    // nenhuma, só diz qual cara o personagem tem agora.
    if (barra.hasAttribute('data-retrato-de-vida')) {
      trocarRetratoDaVida(barra, Number(atual), teto);
      return;
    }

    const { base, extra } = fatias(Number(atual), teto);

    // A peça do quadro.
    const valor = barra.querySelector('.peca-barra-valor');
    const cheia = barra.querySelector('.peca-barra-cheia');
    const sobra = barra.querySelector('.peca-barra-extra');
    if (valor) {
      valor.dataset.max = String(teto);
      valor.textContent = `${atual} / ${teto}`;
    }
    if (cheia) cheia.style.width = `${base}%`;
    if (sobra) sobra.style.width = `${extra}%`;

    // A barra da ficha.
    const mostrador = barra.querySelector('.bar-display');
    const enchimento = barra.querySelector('.bar-fill');
    const excedente = barra.querySelector('.bar-extra');
    if (mostrador) {
      mostrador.dataset.current = String(atual);
      mostrador.dataset.max = String(teto);
      mostrador.textContent = `${atual} / ${teto}`;
    }
    if (enchimento) enchimento.style.width = `${base}%`;
    if (excedente) excedente.style.width = `${extra}%`;
  }

  /* O que os botões chamam depois do POST: o servidor já disse o valor novo,
     e todas as cópias daquela barra na página passam a mostrá-lo.

     O máximo vem por parâmetro sempre que dá, porque nem toda cópia da barra
     tem um mostrador de onde tirá-lo: o elo do retrato, por exemplo, é uma
     div vazia. Quando não vem, vale o que qualquer uma das outras diz. */
  function aplicarUm(tipo, id, atual, maximo) {
    const alvos = elementos(tipo, id);
    let teto = maximo === undefined || maximo === null ? null : Number(maximo);
    if (teto === null) {
      alvos.forEach((barra) => {
        const dito = barra.querySelector('.peca-barra-valor, .bar-display');
        if (teto === null && dito) teto = Number(dito.dataset.max);
      });
      if (teto === null) teto = 100;
    }
    alvos.forEach((barra) => pintar(barra, Number(atual), teto));
  }

  const raiz = document.querySelector('[data-barras-url]');
  if (!raiz) {
    window.hudBarras = { aplicarUm, sincronizar: () => {} };
    return;
  }

  const url = raiz.dataset.barrasUrl;
  let buscando = false;

  function sincronizar() {
    if (buscando) return;
    buscando = true;
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then((r) => (r.ok ? r.json() : null))
      .then((dados) => {
        if (!dados || !dados.bars) return;
        Object.keys(dados.bars).forEach((chave) => {
          const [tipo, id] = chave.split(':');
          const barra = dados.bars[chave];
          elementos(tipo, id).forEach((el) => pintar(el, barra.current, barra.max));
        });
      })
      .catch(() => {})
      .finally(() => {
        buscando = false;
      });
  }

  setInterval(() => {
    if (!document.hidden) sincronizar();
  }, INTERVALO);

  /* Quem volta para a aba quer o número de agora, não o de quando saiu. */
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) sincronizar();
  });

  window.hudBarras = { aplicarUm, sincronizar };
})();

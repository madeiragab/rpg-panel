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

  function pintar(barra, atual, maximo) {
    const teto = Number(maximo) || 1;

    // A peça do quadro.
    const valor = barra.querySelector('.peca-barra-valor');
    const cheia = barra.querySelector('.peca-barra-cheia');
    if (valor) {
      valor.dataset.max = String(teto);
      valor.textContent = `${atual} / ${teto}`;
    }
    if (cheia) cheia.style.width = `${entre((atual / teto) * 100, 0, 100)}%`;

    // A barra da ficha.
    const mostrador = barra.querySelector('.bar-display');
    const enchimento = barra.querySelector('.bar-fill');
    if (mostrador) {
      mostrador.dataset.current = String(atual);
      mostrador.dataset.max = String(teto);
      mostrador.textContent = `${atual} / ${teto}`;
    }
    if (enchimento) enchimento.style.width = `${entre((atual / teto) * 100, 0, 100)}%`;
  }

  /* O que os botões chamam depois do POST: o servidor já disse o valor novo,
     e todas as cópias daquela barra na página passam a mostrá-lo. */
  function aplicarUm(tipo, id, atual, maximo) {
    elementos(tipo, id).forEach((barra) => {
      const dito = barra.querySelector('.peca-barra-valor, .bar-display');
      const teto = maximo !== undefined && maximo !== null
        ? maximo
        : (dito && Number(dito.dataset.max)) || 100;
      pintar(barra, Number(atual), teto);
    });
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

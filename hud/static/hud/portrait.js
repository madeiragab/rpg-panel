/* Enquadramento de imagem: a moldura fica cheia, a pessoa escolhe o pedaço.

   Portado da ficha de Ascensão dos Semideuses, com uma diferença: lá o corte
   morava no navegador de quem preenchia, aqui ele vai para o banco. A moldura
   é a mesma para o mestre e para o jogador, então o pedaço escolhido precisa
   viajar junto com a imagem.

   A moldura tem proporção fixa e fica sempre cheia. A imagem entra no menor
   tamanho que a cobre e sobe até 4x pelo zoom; o arraste escolhe qual pedaço
   aparece. object-fit não serve: "cover" corta sempre pelo meio e "contain"
   deixa tarja. Largura e altura saem do mesmo fator, então a proporção nunca
   muda.

   Uma página tem várias molduras — o retrato da ficha, o avatar da barra de
   cima, cada item do inventário — então tudo aqui trabalha por elemento, e não
   por id. O estado de cada uma mora no próprio dataset: quem só mostra não tem
   `data-save-url` e nunca vira editor. */
(() => {
  const ZOOM_MINIMO = 100;
  const ZOOM_MAXIMO = 400;
  const SELETOR = '[data-portrait-frame]';
  const preparadas = new WeakSet();

  const entre = (n, min, max) => Math.min(Math.max(n, min), max);

  function estado(moldura) {
    return {
      zoom: entre(Number(moldura.dataset.zoom) || ZOOM_MINIMO, ZOOM_MINIMO, ZOOM_MAXIMO),
      x: entre(Number(moldura.dataset.focusX) || 0, 0, 1),
      y: entre(Number(moldura.dataset.focusY) || 0, 0, 1),
    };
  }

  function tamanho(moldura, foto) {
    const { zoom } = estado(moldura);
    const cobre = Math.max(
      moldura.clientWidth / foto.naturalWidth,
      moldura.clientHeight / foto.naturalHeight,
    );
    const fator = cobre * (zoom / 100);
    return { l: foto.naturalWidth * fator, a: foto.naturalHeight * fator };
  }

  function posicionar(moldura) {
    const foto = moldura.querySelector('img');
    if (!foto || !foto.naturalWidth || !moldura.clientWidth) return;
    const { x, y } = estado(moldura);
    const { l, a } = tamanho(moldura, foto);
    foto.style.width = `${l.toFixed(2)}px`;
    foto.style.height = `${a.toFixed(2)}px`;
    foto.style.left = `${(-(l - moldura.clientWidth) * x).toFixed(2)}px`;
    foto.style.top = `${(-(a - moldura.clientHeight) * y).toFixed(2)}px`;
  }

  function csrf() {
    if (window.hudConfig && window.hudConfig.csrfToken) return window.hudConfig.csrfToken;
    const campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
  }

  /* O arraste dispara dezenas de eventos por segundo. Sem a espera, cada pixel
     viraria um POST; com ela, o servidor recebe o enquadramento que ficou. */
  function agendarSalvar(moldura) {
    const url = moldura.dataset.saveUrl;
    const token = csrf();
    if (!url || !token) return;
    clearTimeout(moldura._salvando);
    moldura._salvando = setTimeout(() => {
      const { zoom, x, y } = estado(moldura);
      const corpo = new URLSearchParams();
      corpo.append('zoom', String(zoom));
      corpo.append('focus_x', x.toFixed(4));
      corpo.append('focus_y', y.toFixed(4));
      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': token, 'X-Requested-With': 'XMLHttpRequest' },
        body: corpo,
      }).catch(() => {});
    }, 500);
  }

  function controles(moldura) {
    const caixa = moldura.closest('.portrait-wrap') || moldura.parentElement;
    if (!caixa) return {};
    return {
      zoom: caixa.querySelector('[data-portrait-zoom]'),
      centrar: caixa.querySelector('[data-portrait-center]'),
    };
  }

  /* Os handlers ficam presos de uma vez só e conferem o data-save-url a cada
     evento, em vez de serem ligados só para quem já nasce editável: a moldura
     do painel de item troca de dono a cada clique, e às vezes o dono novo pode
     ser editado e o anterior não. */
  function ligarEdicao(moldura) {
    const { zoom: controleZoom, centrar } = controles(moldura);

    if (controleZoom) {
      controleZoom.addEventListener('input', () => {
        if (!moldura.dataset.saveUrl) return;
        moldura.dataset.zoom = String(
          entre(Number(controleZoom.value) || ZOOM_MINIMO, ZOOM_MINIMO, ZOOM_MAXIMO),
        );
        posicionar(moldura);
        agendarSalvar(moldura);
      });
    }

    if (centrar) {
      centrar.addEventListener('click', () => {
        if (!moldura.dataset.saveUrl) return;
        moldura.dataset.zoom = String(ZOOM_MINIMO);
        moldura.dataset.focusX = '0.5';
        moldura.dataset.focusY = '0.5';
        if (controleZoom) controleZoom.value = String(ZOOM_MINIMO);
        posicionar(moldura);
        agendarSalvar(moldura);
      });
    }

    /* O arraste move o ponto visível. Ele anda em fração da sobra, não em
       pixels: assim o mesmo ponto vale em qualquer tamanho de moldura, e sem
       sobra (zoom 100 numa imagem que cabe exata) não há para onde arrastar. */
    let arrasto = null;

    moldura.addEventListener('pointerdown', (e) => {
      const foto = moldura.querySelector('img');
      if (!moldura.dataset.saveUrl || !foto || !foto.naturalWidth) return;
      const { x, y } = estado(moldura);
      arrasto = { x: e.clientX, y: e.clientY, px: x, py: y };
      moldura.setPointerCapture(e.pointerId);
      moldura.classList.add('arrastando');
    });

    moldura.addEventListener('pointermove', (e) => {
      if (!arrasto) return;
      const foto = moldura.querySelector('img');
      const { l, a } = tamanho(moldura, foto);
      const sobraL = l - moldura.clientWidth;
      const sobraA = a - moldura.clientHeight;
      if (sobraL > 0) {
        moldura.dataset.focusX = String(entre(arrasto.px - (e.clientX - arrasto.x) / sobraL, 0, 1));
      }
      if (sobraA > 0) {
        moldura.dataset.focusY = String(entre(arrasto.py - (e.clientY - arrasto.y) / sobraA, 0, 1));
      }
      posicionar(moldura);
      e.preventDefault();
    });

    const soltar = () => {
      if (!arrasto) return;
      arrasto = null;
      moldura.classList.remove('arrastando');
      agendarSalvar(moldura);
    };
    moldura.addEventListener('pointerup', soltar);
    moldura.addEventListener('pointercancel', soltar);
  }

  function preparar(moldura) {
    if (!moldura) return;
    if (!preparadas.has(moldura)) {
      preparadas.add(moldura);
      // naturalWidth só existe depois que a imagem carrega, e uma que veio do
      // cache já chega pronta: os dois casos precisam do posicionamento.
      const foto = moldura.querySelector('img');
      if (foto) foto.addEventListener('load', () => posicionar(moldura));
      ligarEdicao(moldura);
    }
    moldura.classList.toggle('editavel', !!moldura.dataset.saveUrl);
    posicionar(moldura);
  }

  function prepararTodas(raiz) {
    (raiz || document).querySelectorAll(SELETOR).forEach(preparar);
  }

  prepararTodas();
  window.addEventListener('resize', () => prepararTodas());

  /* Quem troca a imagem de uma moldura por JS — o slot que recebe um item, o
     painel de detalhe que muda de item — mexe no src e nos data-* e chama isto
     para a moldura se recolocar. */
  window.hudPortrait = { preparar, prepararTodas, posicionar };
})();

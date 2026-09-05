/* Enquadramento do retrato da ficha.

   Portado da ficha de Ascensão dos Semideuses, com uma diferença: lá o corte
   morava no navegador de quem preenchia, aqui ele vai para o banco. A moldura
   é a mesma para o mestre e para o jogador, então o pedaço escolhido precisa
   viajar junto com a foto.

   A moldura tem proporção fixa e fica sempre cheia. A foto entra no menor
   tamanho que a cobre e sobe até 4x pelo zoom; o arraste escolhe qual pedaço
   aparece. object-fit não serve: "cover" corta sempre pelo meio e "contain"
   deixa tarja. Largura e altura saem do mesmo fator, então a proporção da
   imagem nunca muda. */
(() => {
  const dados = document.getElementById('portrait-framing');
  const moldura = document.getElementById('portrait-frame');
  const foto = moldura && moldura.querySelector('img');
  if (!dados || !moldura || !foto) return;

  const config = JSON.parse(dados.textContent);
  const ZOOM_MINIMO = 100;
  const ZOOM_MAXIMO = 400;

  let zoom = Number(config.zoom) || ZOOM_MINIMO;
  const ponto = { x: Number(config.x) || 0, y: Number(config.y) || 0 };

  function tamanho() {
    const cobre = Math.max(
      moldura.clientWidth / foto.naturalWidth,
      moldura.clientHeight / foto.naturalHeight,
    );
    const fator = cobre * (zoom / 100);
    return { l: foto.naturalWidth * fator, a: foto.naturalHeight * fator };
  }

  function posicionar() {
    if (!foto.naturalWidth || !moldura.clientWidth) return;
    const { l, a } = tamanho();
    foto.style.width = `${l.toFixed(2)}px`;
    foto.style.height = `${a.toFixed(2)}px`;
    foto.style.left = `${(-(l - moldura.clientWidth) * ponto.x).toFixed(2)}px`;
    foto.style.top = `${(-(a - moldura.clientHeight) * ponto.y).toFixed(2)}px`;
  }

  // naturalWidth só existe depois que a imagem carrega, e uma foto vinda do
  // cache já chega pronta: os dois casos precisam do primeiro posicionamento.
  if (foto.complete) posicionar();
  foto.addEventListener('load', posicionar);
  window.addEventListener('resize', posicionar);

  if (!config.saveUrl) return;   // jogador só olha

  /* ---------- daqui para baixo, só quem edita a ficha ---------- */

  const csrf =
    (window.hudConfig && window.hudConfig.csrfToken) ||
    (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value;
  const controleZoom = document.getElementById('portrait-zoom');
  const botaoCentrar = document.getElementById('portrait-center');
  let agendado = null;

  // O arraste dispara dezenas de eventos por segundo. Sem a espera, cada pixel
  // viraria um POST; com ela, o servidor recebe o enquadramento que ficou.
  function salvarDepois() {
    if (!csrf) return;
    clearTimeout(agendado);
    agendado = setTimeout(salvar, 500);
  }

  function salvar() {
    const corpo = new URLSearchParams();
    corpo.append('zoom', String(zoom));
    corpo.append('focus_x', ponto.x.toFixed(4));
    corpo.append('focus_y', ponto.y.toFixed(4));

    fetch(config.saveUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      body: corpo,
    }).catch(() => {});
  }

  moldura.classList.add('editavel');

  if (controleZoom) {
    controleZoom.addEventListener('input', () => {
      zoom = Math.min(Math.max(Number(controleZoom.value) || ZOOM_MINIMO, ZOOM_MINIMO), ZOOM_MAXIMO);
      posicionar();
      salvarDepois();
    });
  }

  if (botaoCentrar) {
    botaoCentrar.addEventListener('click', () => {
      zoom = ZOOM_MINIMO;
      ponto.x = 0.5;
      ponto.y = 0.5;
      if (controleZoom) controleZoom.value = String(zoom);
      posicionar();
      salvarDepois();
    });
  }

  /* O arraste move o ponto visível. Ele anda em fração da sobra, não em
     pixels: assim o mesmo ponto vale em qualquer tamanho de moldura, e sem
     sobra (zoom 100 numa foto que cabe exata) não há para onde arrastar. */
  let arrasto = null;

  function sobra() {
    const { l, a } = tamanho();
    return { l: l - moldura.clientWidth, a: a - moldura.clientHeight };
  }

  moldura.addEventListener('pointerdown', (e) => {
    if (!foto.naturalWidth) return;
    arrasto = { x: e.clientX, y: e.clientY, px: ponto.x, py: ponto.y };
    moldura.setPointerCapture(e.pointerId);
    moldura.classList.add('arrastando');
  });

  moldura.addEventListener('pointermove', (e) => {
    if (!arrasto) return;
    const s = sobra();
    if (s.l > 0) ponto.x = Math.min(1, Math.max(0, arrasto.px - (e.clientX - arrasto.x) / s.l));
    if (s.a > 0) ponto.y = Math.min(1, Math.max(0, arrasto.py - (e.clientY - arrasto.y) / s.a));
    posicionar();
    e.preventDefault();
  });

  function soltar() {
    if (!arrasto) return;
    arrasto = null;
    moldura.classList.remove('arrastando');
    salvarDepois();
  }

  moldura.addEventListener('pointerup', soltar);
  moldura.addEventListener('pointercancel', soltar);
})();

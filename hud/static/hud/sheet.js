/* O lápis da ficha.

   A ficha vivia com todos os formulários abertos ao mesmo tempo: o de criar
   perícia, o de criar atributo, o de trocar a foto, o de criar barra. Quem só
   queria olhar a ficha via um formulário atrás do outro.

   Agora tudo isso mora atrás de um botão. Fora do modo de edição a ficha é só
   a ficha; com o lápis ligado aparecem os formulários e cada perícia, atributo
   e habilidade ganha o par reescrever/apagar.

   A escolha fica no navegador de quem abriu: o mestre que está montando a
   sessão não quer reapertar o lápis a cada ficha, e o que está só conduzindo
   não quer ver formulário nenhum. */
(() => {
  const ficha = document.querySelector('[data-ficha]');
  const lapis = document.getElementById('alternar-edicao');
  if (!ficha || !lapis) return;

  const CHAVE = 'hud:editando-ficha';

  function aplicar(ligado) {
    ficha.classList.toggle('editando', ligado);
    lapis.classList.toggle('ligado', ligado);
    lapis.setAttribute('aria-pressed', String(ligado));
    lapis.title = ligado ? 'Sair do modo de edição' : 'Editar a ficha';
    // Molduras dentro de bloco escondido têm largura zero; agora que o bloco
    // apareceu, elas precisam se recolocar.
    if (ligado && window.hudPortrait) window.hudPortrait.prepararTodas();
  }

  let ligado = false;
  try {
    ligado = localStorage.getItem(CHAVE) === '1';
  } catch (e) {
    ligado = false;
  }
  aplicar(ligado);

  lapis.addEventListener('click', () => {
    ligado = !ligado;
    aplicar(ligado);
    try {
      localStorage.setItem(CHAVE, ligado ? '1' : '0');
    } catch (e) {
      /* navegador sem armazenamento: vale só nesta página, e tudo bem */
    }
  });

  /* ------------------------------------------ reescrever e apagar linhas -- */

  function csrf() {
    if (window.hudConfig && window.hudConfig.csrfToken) return window.hudConfig.csrfToken;
    const campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
  }

  function mandar(url, corpo) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' },
      body: corpo,
    }).then((r) => r.json().then((dados) => ({ ok: r.ok, dados })));
  }

  ficha.addEventListener('click', (e) => {
    const editar = e.target.closest('[data-editar-linha]');
    const apagar = e.target.closest('[data-apagar-linha]');
    if (!editar && !apagar) return;

    const linha = e.target.closest('[data-linha]');
    if (!linha) return;

    if (apagar) {
      if (!confirm('Apagar isto da ficha?')) return;
      mandar(apagar.dataset.apagarLinha, new URLSearchParams())
        .then(({ ok, dados }) => {
          if (!ok || !dados.ok) {
            alert(dados.erro || 'Não foi possível apagar.');
            return;
          }
          linha.remove();
        })
        .catch(() => alert('Não foi possível falar com o servidor.'));
      return;
    }

    const nome = prompt('Nome:', linha.dataset.nome || '');
    if (nome === null) return;
    const corpo = new URLSearchParams();
    corpo.append('name', nome);
    if (editar.dataset.comValor) {
      const valor = prompt('Valor:', linha.dataset.valor || '');
      if (valor === null) return;
      corpo.append('value', valor);
    }

    mandar(editar.dataset.editarLinha, corpo)
      .then(({ ok, dados }) => {
        if (!ok || !dados.ok) {
          alert(dados.erro || 'Não foi possível salvar.');
          return;
        }
        linha.dataset.nome = dados.name;
        linha.dataset.valor = dados.value;
        const alvoNome = linha.querySelector('.etiqueta-nome, .attribute-nome');
        const alvoValor = linha.querySelector('.etiqueta-valor, .attribute-valor');
        if (alvoNome) alvoNome.textContent = dados.name;
        if (alvoValor) alvoValor.textContent = dados.value;
      })
      .catch(() => alert('Não foi possível falar com o servidor.'));
  });
})();

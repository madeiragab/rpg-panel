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

    if (editar.dataset.comDano) {
      abrirEditorDeHabilidade(linha, editar.dataset.editarLinha);
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

  /* ------------------------------------------------ o editor da habilidade -- */

  /* Perícia e atributo têm dois campos e cabem num prompt. Habilidade não: tem
     nome, dano e quantos campos a pessoa quiser criar, e um prompt por campo
     seria insuportável. Então ela abre uma caixinha embaixo da etiqueta. */
  function abrirEditorDeHabilidade(etiqueta, url) {
    if (etiqueta.nextElementSibling && etiqueta.nextElementSibling.classList.contains('editor-habilidade')) {
      etiqueta.nextElementSibling.remove();
      return;
    }
    document.querySelectorAll('.editor-habilidade').forEach((e) => e.remove());

    let extras = [];
    try {
      extras = JSON.parse(etiqueta.dataset.extras || '[]');
    } catch (e) {
      extras = [];
    }

    const caixa = document.createElement('div');
    caixa.className = 'editor-habilidade';
    caixa.innerHTML =
      '<label>Nome<input type="text" data-campo="name"></label>' +
      '<label>Dano<input type="text" data-campo="damage" placeholder="Ex.: 2d6+3"></label>' +
      '<label>Descrição<textarea data-campo="description" rows="3" placeholder="O que a habilidade faz"></textarea></label>' +
      '<div data-extras></div>' +
      '<div class="editor-acoes">' +
      '<button type="button" class="hud-button ghost" data-mais>+ campo</button>' +
      '<button type="button" class="hud-button" data-salvar>Salvar</button>' +
      '<button type="button" class="hud-button ghost" data-cancelar>Cancelar</button>' +
      '</div>';

    caixa.querySelector('[data-campo="name"]').value = etiqueta.dataset.nome || '';
    caixa.querySelector('[data-campo="damage"]').value = etiqueta.dataset.dano || '';
    caixa.querySelector('[data-campo="description"]').value = etiqueta.dataset.descricao || '';

    const listaExtras = caixa.querySelector('[data-extras]');

    function novaLinha(rotulo, valor) {
      const linha = document.createElement('div');
      linha.className = 'editor-extra';
      linha.innerHTML =
        '<input type="text" data-rotulo placeholder="campo">' +
        '<input type="text" data-valor placeholder="valor">' +
        '<button type="button" class="etiqueta-botao apagar" data-tirar title="Tirar campo">×</button>';
      linha.querySelector('[data-rotulo]').value = rotulo || '';
      linha.querySelector('[data-valor]').value = valor || '';
      linha.querySelector('[data-tirar]').addEventListener('click', () => linha.remove());
      listaExtras.appendChild(linha);
      return linha;
    }

    extras.forEach((par) => novaLinha(par[0], par[1]));
    caixa.querySelector('[data-mais]').addEventListener('click', () => {
      novaLinha('', '').querySelector('[data-rotulo]').focus();
    });
    caixa.querySelector('[data-cancelar]').addEventListener('click', () => caixa.remove());

    caixa.querySelector('[data-salvar]').addEventListener('click', () => {
      const corpo = new URLSearchParams();
      corpo.append('name', caixa.querySelector('[data-campo="name"]').value);
      corpo.append('damage', caixa.querySelector('[data-campo="damage"]').value);
      corpo.append('description', caixa.querySelector('[data-campo="description"]').value);
      const pares = [];
      listaExtras.querySelectorAll('.editor-extra').forEach((linha) => {
        const rotulo = linha.querySelector('[data-rotulo]').value.trim();
        if (rotulo) pares.push([rotulo, linha.querySelector('[data-valor]').value]);
      });
      corpo.append('extras', JSON.stringify(pares));

      mandar(url, corpo)
        .then(({ ok, dados }) => {
          if (!ok || !dados.ok) {
            alert(dados.erro || 'Não foi possível salvar.');
            return;
          }
          // Redesenhar a etiqueta à mão duplicaria o template; recarregar a
          // ficha inteira era o que estamos tirando. O meio-termo é reescrever
          // só o que mudou.
          etiqueta.dataset.nome = dados.name;
          etiqueta.dataset.dano = dados.damage;
          etiqueta.dataset.descricao = dados.description || '';
          etiqueta.dataset.extras = JSON.stringify(dados.extras || []);
          etiqueta.querySelector('.etiqueta-nome').textContent = dados.name;
          const campos = etiqueta.querySelector('.etiqueta-campos');
          if (campos) {
            const pedacos = [];
            if (dados.damage) pedacos.push(['dano', dados.damage]);
            (dados.extras || []).forEach((par) => pedacos.push(par));
            campos.textContent = '';
            pedacos.forEach((par) => {
              const chip = document.createElement('span');
              chip.className = 'etiqueta-campo';
              const rotulo = document.createElement('b');
              rotulo.textContent = par[0];
              chip.appendChild(rotulo);
              chip.appendChild(document.createTextNode(par[1]));
              campos.appendChild(chip);
            });
          }
          caixa.remove();
        })
        .catch(() => alert('Não foi possível falar com o servidor.'));
    });

    etiqueta.insertAdjacentElement('afterend', caixa);
    caixa.querySelector('[data-campo="name"]').focus();
  }

  /* --------------------------------------------- arrastar para reordenar -- */

  /* Vai a lista inteira de ids na ordem em que ficaram, e não "essa subiu uma":
     duas pessoas arrastando ao mesmo tempo com movimentos relativos acabariam
     com ordens diferentes das que cada uma viu. */
  function ligarReordenacao(grade) {
    const url = grade.dataset.reordenarUrl;
    if (!url) return;
    let arrastada = null;

    grade.querySelectorAll('[data-linha]').forEach((caixa) => {
      caixa.draggable = true;
      caixa.addEventListener('dragstart', (e) => {
        if (!ficha.classList.contains('editando')) {
          e.preventDefault();
          return;
        }
        arrastada = caixa;
        caixa.classList.add('arrastando');
        e.dataTransfer.effectAllowed = 'move';
        // O Firefox não começa o arraste sem algum dado carregado.
        e.dataTransfer.setData('text/plain', '');
      });
      caixa.addEventListener('dragend', () => {
        caixa.classList.remove('arrastando');
        arrastada = null;
        guardarOrdem();
      });
      caixa.addEventListener('dragover', (e) => {
        if (!arrastada || arrastada === caixa) return;
        e.preventDefault();
        const meio = caixa.getBoundingClientRect();
        const depois = e.clientY > meio.top + meio.height / 2
          || (e.clientX > meio.left + meio.width / 2 && Math.abs(e.clientY - (meio.top + meio.height / 2)) < meio.height / 2);
        caixa.parentNode.insertBefore(arrastada, depois ? caixa.nextSibling : caixa);
      });
    });

    function guardarOrdem() {
      const ids = [];
      grade.querySelectorAll('[data-linha]').forEach((caixa) => {
        const botao = caixa.querySelector('[data-apagar-linha]');
        if (!botao) return;
        const partes = botao.dataset.apagarLinha.split('/').filter(Boolean);
        ids.push(Number(partes[partes.length - 2]));
      });
      if (!ids.length) return;
      const corpo = new URLSearchParams();
      corpo.append('ids', JSON.stringify(ids));
      mandar(url, corpo).catch(() => {});
    }
  }

  document.querySelectorAll('[data-reordenavel]').forEach(ligarReordenacao);
})();

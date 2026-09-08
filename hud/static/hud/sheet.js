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

  /* ------------------------------------------------ reescrever a barra ---- */

  /* Nome, máximo e cor de uma barra, no lugar. O formulário de criar barra já
     pede os três; sem isto, mudar qualquer um deles obrigava a apagar a barra
     e criar outra — perdendo o valor atual junto.

     O valor atual não entra aqui de propósito: ele tem os botões de mais e
     menos, e é o que mais muda durante a sessão. */
  function abrirEditorDeBarra(lapis) {
    const barra = lapis.closest('.character-bar');
    if (!barra) return;
    if (barra.nextElementSibling && barra.nextElementSibling.classList.contains('editor-habilidade')) {
      barra.nextElementSibling.remove();
      return;
    }
    document.querySelectorAll('.editor-habilidade').forEach((e) => e.remove());

    const caixa = document.createElement('div');
    caixa.className = 'editor-habilidade';
    caixa.innerHTML =
      '<label>Nome<input type="text" data-campo="name"></label>' +
      '<label>Máximo<input type="number" min="1" data-campo="max"></label>' +
      '<label>Cor<input type="color" data-campo="color"></label>' +
      '<div class="editor-acoes">' +
      '<button type="button" class="hud-button" data-salvar>Salvar</button>' +
      '<button type="button" class="hud-button ghost" data-cancelar>Cancelar</button>' +
      '</div>';

    caixa.querySelector('[data-campo="name"]').value = lapis.dataset.nome || '';
    caixa.querySelector('[data-campo="max"]').value = lapis.dataset.maximo || '';
    caixa.querySelector('[data-campo="color"]').value = lapis.dataset.cor || '#ff4444';
    caixa.querySelector('[data-cancelar]').addEventListener('click', () => caixa.remove());

    caixa.querySelector('[data-salvar]').addEventListener('click', () => {
      const corpo = new URLSearchParams();
      corpo.append('name', caixa.querySelector('[data-campo="name"]').value);
      corpo.append('max_value', caixa.querySelector('[data-campo="max"]').value);
      corpo.append('color', caixa.querySelector('[data-campo="color"]').value);

      mandar(lapis.dataset.editarBarra, corpo)
        .then(({ ok, dados }) => {
          if (!ok || !dados.success) {
            alert(dados.error || 'Não foi possível salvar.');
            return;
          }
          lapis.dataset.nome = dados.name;
          lapis.dataset.maximo = String(dados.max);
          lapis.dataset.cor = dados.color;

          const nome = barra.querySelector('.bar-nome');
          if (nome) nome.textContent = dados.name;
          // As duas cores vêm do servidor: a oposta é conta dele, e refazê-la
          // aqui seria a segunda cópia da mesma fórmula.
          const cheia = barra.querySelector('.bar-fill');
          const sobra = barra.querySelector('.bar-extra');
          if (cheia) cheia.style.background = dados.color;
          if (sobra) sobra.style.background = dados.cor_excedente;
          // As larguras e o retrato saem do mesmo lugar de sempre: o máximo
          // mudou, e com ele a fração de vida que decide a cara da ficha.
          if (window.hudBarras) {
            window.hudBarras.aplicarUm(
              barra.dataset.barKind, barra.dataset.barId, dados.current, dados.max,
            );
          }
          caixa.remove();
        })
        .catch(() => alert('Não foi possível falar com o servidor.'));
    });

    barra.insertAdjacentElement('afterend', caixa);
    caixa.querySelector('[data-campo="name"]').focus();
  }

  ficha.addEventListener('click', (e) => {
    const lapis = e.target.closest('[data-editar-barra]');
    if (lapis) abrirEditorDeBarra(lapis);
  });

  /* --------------------------------------------- arrastar para reordenar -- */

  /* Vai a lista inteira de ids na ordem em que ficaram, e não "essa subiu uma":
     duas pessoas arrastando ao mesmo tempo com movimentos relativos acabariam
     com ordens diferentes das que cada uma viu. */
  const jaArrastaveis = new WeakSet();

  function ligarReordenacao(grade) {
    const url = grade.dataset.reordenarUrl;
    if (!url) return;
    let arrastada = null;

    grade.querySelectorAll('[data-linha]').forEach((caixa) => {
      // Barra criada sem recarregar entra na lista depois; religar a lista
      // inteira não pode ligar duas vezes quem já estava.
      if (jaArrastaveis.has(caixa)) return;
      jaArrastaveis.add(caixa);
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
        // A barra diz o id na cara; a perícia e o atributo só o têm dentro da
        // rota do botão de apagar, e é de lá que ele sai.
        if (caixa.dataset.linhaId) {
          ids.push(Number(caixa.dataset.linhaId));
          return;
        }
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

  function ligarTudoQueArrasta() {
    document.querySelectorAll('[data-reordenavel]').forEach(ligarReordenacao);
  }

  ligarTudoQueArrasta();

  /* Quem cria uma barra sem recarregar a página chama isto para a barra nova
     poder ser arrastada como as outras. */
  window.hudFicha = { religar: ligarTudoQueArrasta };

  /* ------------------------------------------- os dois enquadramentos ----- */

  /* A mesma imagem aparece em duas molduras de formato diferente: a da ficha,
     alta, e a do card na lista, larga e baixa. Um corte so nunca serve para as
     duas, entao sao dois — e este seletor diz qual deles o zoom e o arraste
     estao mexendo agora. */
  const alvos = document.querySelector('[data-portrait-alvos]');
  if (alvos) {
    /* A moldura é a que está marcada como principal, e não a primeira da
       página: o avatar do jogador no cabeçalho vem antes do retrato na ordem
       do documento, e era nele que o seletor estava mexendo. A marca também
       aguenta o seletor mudar de lugar no template, o que a vizinhança do
       elemento anterior não aguentava. */
    const caixa = document.querySelector('[data-retrato-principal]');
    const moldura = caixa && caixa.querySelector('[data-portrait-frame]');
    const controle = caixa && caixa.querySelector('[data-portrait-zoom]');

    function trocarAlvo(qual) {
      if (!moldura) return;   // template mudou de forma; melhor não fazer nada
      // O que estava na tela volta para o seu lugar antes de a outra entrar:
      // senao o corte recem-arrastado se perderia ao alternar.
      const anterior = alvos.dataset.atual || 'ficha';
      alvos.dataset[`${anterior}Zoom`] = moldura.dataset.zoom;
      alvos.dataset[`${anterior}X`] = moldura.dataset.focusX;
      alvos.dataset[`${anterior}Y`] = moldura.dataset.focusY;

      moldura.dataset.zoom = alvos.dataset[`${qual}Zoom`];
      moldura.dataset.focusX = alvos.dataset[`${qual}X`];
      moldura.dataset.focusY = alvos.dataset[`${qual}Y`];
      moldura.dataset.saveUrl = alvos.dataset[`${qual}Url`];
      moldura.dataset.alvo = qual;
      alvos.dataset.atual = qual;

      /* A moldura toma o formato de onde o corte vai valer. Sem isto a
         pessoa acertaria o corte do card olhando uma moldura alta, e o
         ponto escolhido — que é fração da sobra — sairia diferente na
         moldura larga e baixa do card. */
      moldura.classList.toggle('formato-menu', qual === 'menu');

      if (controle) controle.value = moldura.dataset.zoom;
      alvos.querySelectorAll('[data-alvo]').forEach((b) => {
        b.classList.toggle('ligado', b.dataset.alvo === qual);
      });
      if (window.hudPortrait) window.hudPortrait.preparar(moldura);
    }

    alvos.dataset.atual = 'ficha';
    alvos.querySelectorAll('[data-alvo]').forEach((botao) => {
      botao.addEventListener('click', () => trocarAlvo(botao.dataset.alvo));
    });
  }

})();

    function trocarRetrato(url) {
      const moldura = molduraDoRetrato;
      if (!moldura) return;   // template mudou de forma; melhor não fazer nada
      let foto = moldura.querySelector('img');
      if (!url) {
        if (foto) foto.remove();
        moldura.classList.add('empty');
        return;
      }
      if (!foto) {
        /* A ficha estava sem retrato nenhum: a moldura nasceu vazia e o
           portrait.js só liga o `load` de quem já tinha imagem. */
        foto = document.createElement('img');
        foto.addEventListener('load', () => {
          if (window.hudPortrait) window.hudPortrait.posicionar(moldura);
        });
        moldura.appendChild(foto);
      }
      moldura.classList.remove('empty');
      foto.src = url;
      if (window.hudPortrait) window.hudPortrait.preparar(moldura);
    }

    estados.querySelectorAll('[data-estado]').forEach((botao) => {
      botao.addEventListener('click', () => {
        const corpo = new URLSearchParams();
        corpo.append('estado', botao.dataset.estado);
        mandar(estados.dataset.url, corpo)
          .then(({ ok, dados }) => {
            if (!ok || !dados.success) return;
            estados.querySelectorAll('[data-estado]').forEach((b) => {
              b.classList.toggle('ligado', b.dataset.estado === dados.estado);
            });
            trocarRetrato(dados.imagem);
          })
          .catch(() => {});
      });
    });
  }
})();

/* Formulários que não recarregam a página.

   Marque o form com `data-ajax` e ele passa a ser enviado por fetch. O que
   volta é HTML montado pelo próprio servidor, não um JSON que o JavaScript
   teria de virar markup: o card que nasce agora precisa ser idêntico ao que
   já estava na tela, e duas cópias do mesmo layout — uma no template, outra
   aqui — divergem na primeira mudança.

   Atributos:
     data-alvo="#grade"     onde enfiar o HTML que voltou
     data-onde="afterbegin" posição (padrão: beforeend)
     data-remover=".peca"   em vez de inserir, apaga o ancestral que casar
     data-confirmar="..."   pergunta antes de mandar
     data-fechar="#painel"  esconde este elemento depois do sucesso

   Sem JavaScript o form continua sendo um POST comum e a página recarrega —
   é o mesmo endpoint dos dois lados. */
(() => {
  const ligadas = new WeakSet();

  function csrf(form) {
    const campo = form.querySelector('[name=csrfmiddlewaretoken]');
    if (campo) return campo.value;
    if (window.hudConfig && window.hudConfig.csrfToken) return window.hudConfig.csrfToken;
    return '';
  }

  function inserir(form, html) {
    const alvo = document.querySelector(form.dataset.alvo);
    if (!alvo || !html) return null;
    // A frase de "nenhum item ainda" some quando o primeiro chega.
    const vazio = alvo.querySelector('[data-vazio]');
    if (vazio) vazio.remove();
    const onde = form.dataset.onde || 'beforeend';
    alvo.insertAdjacentHTML(onde, html);
    return onde === 'afterbegin' ? alvo.firstElementChild : alvo.lastElementChild;
  }

  function avisarQueChegou(elemento) {
    if (!elemento) return;
    // Molduras e peças novas precisam ser apresentadas a quem cuida delas: os
    // scripts prendem os eventos no carregamento e não sabem do que nasceu
    // depois.
    if (window.hudPortrait) window.hudPortrait.prepararTodas(elemento.parentElement);
    if (window.hudQuadro) window.hudQuadro.registrar(elemento);
    // O card que nasceu traz o proprio form de apagar, e ele tambem nao pode
    // recarregar a pagina.
    elemento.querySelectorAll("form[data-ajax]").forEach(ligar);
    elemento.classList.add('recem-chegado');
    setTimeout(() => elemento.classList.remove('recem-chegado'), 900);
  }

  function ligar(form) {
    if (ligadas.has(form)) return;
    ligadas.add(form);
    form.addEventListener('submit', (e) => {
      if (form.dataset.confirmar && !confirm(form.dataset.confirmar)) {
        e.preventDefault();
        return;
      }
      e.preventDefault();

      const botoes = form.querySelectorAll('button[type=submit]');
      botoes.forEach((b) => { b.disabled = true; });

      fetch(form.action || window.location.href, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf(form), 'X-Requested-With': 'XMLHttpRequest' },
        body: new FormData(form),
      })
        .then((r) => r.json().then((dados) => ({ ok: r.ok, dados })))
        .then(({ ok, dados }) => {
          if (!ok || !dados.ok) {
            // Erro de formulário volta como texto e vira alerta: o caso comum
            // é campo obrigatório em branco, e recarregar para mostrar isso
            // seria justamente o que estamos evitando.
            alert(dados.erro || 'Não foi possível salvar. Confira os campos.');
            return;
          }
          if (form.dataset.remover) {
            const alvo = form.closest(form.dataset.remover);
            if (alvo) alvo.remove();
            return;
          }
          avisarQueChegou(inserir(form, dados.html));
          form.reset();
          if (form.dataset.fechar) {
            const painel = document.querySelector(form.dataset.fechar);
            if (painel) painel.style.display = 'none';
          }
        })
        .catch(() => {
          alert('Não foi possível falar com o servidor.');
        })
        .finally(() => {
          botoes.forEach((b) => { b.disabled = false; });
        });
    });
  }

  document.querySelectorAll('form[data-ajax]').forEach(ligar);

  window.hudAjax = {
    ligar,
    ligarTodos: (raiz) => (raiz || document).querySelectorAll('form[data-ajax]').forEach(ligar),
  };
})();

/* O nome do arquivo escolhido aparece ao lado do botão. Sem isto o campo de
   imagem não dá sinal nenhum de que alguma coisa foi escolhida — o <input>
   está escondido, e é ele que normalmente mostraria o nome. */
(() => {
  document.addEventListener('change', (e) => {
    const entrada = e.target;
    if (!entrada.matches || !entrada.matches('.campo-imagem input[type=file]')) return;
    const campo = entrada.closest('[data-campo-imagem]');
    const nome = campo && campo.querySelector('[data-nome-do-arquivo]');
    if (!nome) return;
    nome.textContent = entrada.files && entrada.files[0]
      ? entrada.files[0].name
      : 'Nenhum arquivo escolhido';
  });
})();

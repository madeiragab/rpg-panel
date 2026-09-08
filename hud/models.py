from __future__ import annotations

import colorsys
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


# Os estados do retrato, e a fração de vida em que cada um começa. Quem manda
# é a **primeira barra da ficha**: ela é a vida, por convenção, e é por isso
# que as barras podem ser arrastadas — mudar qual delas vem primeiro é como se
# escolhe qual conta para o retrato.
ESTADO_INTEIRO = "INTEIRO"
ESTADO_FERIDO = "FERIDO"
ESTADO_GRAVE = "GRAVE"
FRACAO_DE_FERIDO = 0.5
FRACAO_DE_GRAVE = 0.25

INVENTORY_ROWS = 4
INVENTORY_COLUMNS = 4
TOTAL_SLOTS = INVENTORY_ROWS * INVENTORY_COLUMNS


class Campaign(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    banner = models.ImageField(upload_to="campaigns/", null=True, blank=True)
    master = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="campaigns_as_master",
    )
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="campaigns_as_player",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name


class RetratoEnquadrado(models.Model):
    """O zoom e o pedaço da foto que aparece dentro da moldura da ficha.

    A moldura tem proporção fixa. Guardar só o arquivo obriga a escolher entre
    mostrar a foto inteira (com tarja em volta) ou cortar pelo centro — e o
    centro geométrico quase nunca é o rosto. Estes três números dizem qual
    pedaço o mestre escolheu, e ficam no banco porque o corte tem que ser o
    mesmo para o jogador que abre a ficha do outro lado da mesa.

    O ponto vai de 0 (borda esquerda/topo) a 1 (direita/base), como fração da
    sobra que o zoom criou: assim ele continua valendo se a moldura mudar de
    tamanho na tela do outro.
    """

    ZOOM_MINIMO = 100
    ZOOM_MAXIMO = 400

    image_zoom = models.PositiveSmallIntegerField(default=100)
    image_focus_x = models.FloatField(default=0.5)
    image_focus_y = models.FloatField(default=0.5)

    class Meta:
        abstract = True

    def clamp_framing(self) -> None:
        zoom = self.image_zoom if self.image_zoom is not None else 100
        self.image_zoom = min(max(int(zoom), self.ZOOM_MINIMO), self.ZOOM_MAXIMO)
        for campo in ("image_focus_x", "image_focus_y"):
            ponto = getattr(self, campo)
            ponto = 0.5 if ponto is None else float(ponto)
            setattr(self, campo, min(max(ponto, 0.0), 1.0))

    def reset_framing(self) -> None:
        """Foto nova, enquadramento novo: o corte antigo não vale para outra imagem."""
        self.image_zoom = 100
        self.image_focus_x = 0.5
        self.image_focus_y = 0.5


class UserProfile(RetratoEnquadrado):
    ROLE_MASTER = "MASTER"
    ROLE_PLAYER = "PLAYER"
    ROLE_CHOICES = (
        (ROLE_MASTER, "Master"),
        (ROLE_PLAYER, "Player"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_PLAYER)
    display_name = models.CharField(max_length=120, blank=True)  # Nome
    nickname = models.CharField(max_length=60, blank=True)  # Apelido
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.user.username} ({self.role})"

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        return super().save(*args, **kwargs)

    @property
    def is_master(self) -> bool:
        return self.role == self.ROLE_MASTER

    @property
    def is_player(self) -> bool:
        return self.role == self.ROLE_PLAYER


class RetratoNoMenu(models.Model):
    """O segundo enquadramento da mesma imagem: o do card na lista.

    A moldura da ficha é alta e a do card é larga e baixa. Um corte só nunca
    serve para as duas — o que enquadra bem um corpo inteiro na ficha vira uma
    tarja no card, e o que fica bom no card decepa a ficha. São os mesmos três
    números de `RetratoEnquadrado`, guardados em outro lugar.
    """

    card_zoom = models.PositiveSmallIntegerField(default=100)
    card_focus_x = models.FloatField(default=0.5)
    card_focus_y = models.FloatField(default=0.5)

    class Meta:
        abstract = True

    def clamp_card(self) -> None:
        zoom = self.card_zoom if self.card_zoom is not None else 100
        self.card_zoom = min(max(int(zoom), 100), 400)
        for campo in ("card_focus_x", "card_focus_y"):
            ponto = getattr(self, campo)
            ponto = 0.5 if ponto is None else float(ponto)
            setattr(self, campo, min(max(ponto, 0.0), 1.0))

    def reset_card(self) -> None:
        self.card_zoom = 100
        self.card_focus_x = 0.5
        self.card_focus_y = 0.5


class PecaDoQuadro(models.Model):
    """Onde a peça está no quadro da campanha.

    A posição é fração do quadro (0 a 1), e não pixel: o mestre arruma a mesa
    no monitor grande e o mesmo arranjo continua de pé no notebook.

    Nulo quer dizer "nunca foi arrastada". O quadro distribui essas em grade ao
    abrir, em vez de empilhar todas no mesmo canto — e só quando alguém arrasta
    é que a posição vira um número no banco.
    """

    board_x = models.FloatField(null=True, blank=True)
    board_y = models.FloatField(null=True, blank=True)

    class Meta:
        abstract = True

    def clamp_board(self) -> None:
        for campo in ("board_x", "board_y"):
            valor = getattr(self, campo)
            if valor is not None:
                setattr(self, campo, min(max(float(valor), 0.0), 1.0))


class NPC(RetratoEnquadrado, RetratoNoMenu, PecaDoQuadro):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="npcs",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="npcs/", null=True, blank=True)
    hp_max = models.PositiveIntegerField(default=10)
    hp_current = models.PositiveIntegerField(default=10)
    sp_max = models.PositiveIntegerField(default=10)
    sp_current = models.PositiveIntegerField(default=10)
    inventory_capacity = models.PositiveIntegerField(default=16)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_npcs",
    )
    assigned_to_character = models.ForeignKey(
        "Character",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="npcs",
    )
    visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def clamp_stats(self) -> None:
        self.hp_current = min(self.hp_current, self.hp_max)
        self.sp_current = min(self.sp_current, self.sp_max)

    @property
    def retrato_atual(self):
        """O retrato, sem mais. Existe com o mesmo nome do de `Character`
        porque as peças do quadro passam pelo mesmo template: só o personagem
        tem estados, e o template não precisa saber disso."""
        return self.image

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_stats()
        self.clamp_framing()
        self.clamp_card()
        self.clamp_board()
        return super().save(*args, **kwargs)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("position", flat=True))
        # Cria slots faltantes
        missing = [pos for pos in range(1, self.inventory_capacity + 1) if pos not in existing]
        NPCInventorySlot.objects.bulk_create(
            [NPCInventorySlot(npc=self, position=pos) for pos in missing],
            ignore_conflicts=True,
        )
        # Remove slots excedentes (quando capacidade diminui)
        self.slots.filter(position__gt=self.inventory_capacity).delete()


class Character(RetratoEnquadrado, RetratoNoMenu, PecaDoQuadro):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="characters",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="characters/", null=True, blank=True)
    # O mesmo personagem em três estados. A arte de ferido é a mesma pessoa com
    # outra cara, e não outra ficha: por isso são campos aqui e não um modelo à
    # parte com nome, barras e inventário repetidos.
    image_ferido = models.ImageField(upload_to="characters/", null=True, blank=True)
    image_grave = models.ImageField(upload_to="characters/", null=True, blank=True)
    hp_max = models.PositiveIntegerField(default=10)
    hp_current = models.PositiveIntegerField(default=10)
    sp_max = models.PositiveIntegerField(default=10)
    sp_current = models.PositiveIntegerField(default=10)
    inventory_capacity = models.PositiveIntegerField(default=16)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_characters",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="characters",
    )
    visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def clamp_stats(self) -> None:
        self.hp_current = min(self.hp_current, self.hp_max)
        self.sp_current = min(self.sp_current, self.sp_max)

    # Os três retratos, cada um caindo para o de cima quando não existe. Assim
    # dá para subir só a arte de ferido e o gravemente ferido já mostrar alguma
    # coisa — e uma ficha antiga, que só tem o retrato normal, continua igual
    # ao que sempre foi.
    @property
    def retrato_inteiro(self):
        return self.image

    @property
    def retrato_ferido(self):
        return self.image_ferido or self.image

    @property
    def retrato_grave(self):
        return self.image_grave or self.image_ferido or self.image

    @property
    def barra_de_vida(self):
        """A primeira barra da ficha, que é a vida por convenção.

        Não há campo dizendo "esta é a vida" porque não haveria como preenchê-lo
        sozinho nas fichas que já existem, e porque a ordem já é uma escolha que
        o mestre faz na tela: ele arrasta para o topo a barra que conta.

        Vai por `next(iter(...))` e não por `.first()`: com as barras já
        carregadas — e a ficha carrega todas para desenhá-las — o `.first()`
        faria uma segunda consulta ao banco para buscar a que já está na mão.
        """
        return next(iter(self.bars.all()), None)

    @property
    def estado_do_retrato(self) -> str:
        """Inteiro, ferido ou gravemente ferido, pela barra de vida."""
        barra = self.barra_de_vida
        if barra is None or barra.max_value <= 0:
            return ESTADO_INTEIRO
        # Vida temporária passa do máximo, e nesse caso a fração passa de 1:
        # ninguém fica ferido por ganhar vida.
        fracao = barra.current / barra.max_value
        if fracao <= FRACAO_DE_GRAVE:
            return ESTADO_GRAVE
        if fracao <= FRACAO_DE_FERIDO:
            return ESTADO_FERIDO
        return ESTADO_INTEIRO

    @property
    def retrato_atual(self):
        """A imagem que vale para a vida de agora."""
        estado = self.estado_do_retrato
        if estado == ESTADO_GRAVE:
            return self.retrato_grave
        if estado == ESTADO_FERIDO:
            return self.retrato_ferido
        return self.retrato_inteiro

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_stats()
        self.clamp_framing()
        self.clamp_card()
        self.clamp_board()
        return super().save(*args, **kwargs)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("position", flat=True))
        # Cria slots faltantes
        missing = [pos for pos in range(1, self.inventory_capacity + 1) if pos not in existing]
        InventorySlot.objects.bulk_create(
            [InventorySlot(character=self, position=pos) for pos in missing],
            ignore_conflicts=True,
        )
        # Remove slots excedentes (quando capacidade diminui)
        self.slots.filter(position__gt=self.inventory_capacity).delete()


class HabilidadeComCampos(models.Model):
    """Uma habilidade e o que ela faz.

    Dano é campo de primeira classe porque é o que se olha primeiro numa mesa
    de combate — e o resto varia demais entre sistemas para virar coluna:
    alcance, custo, recarga, tipo, teste. Esses moram em `extras`, na ordem em
    que a pessoa criou, e não numa tabela nova por ficha.

    `extras` é uma lista de pares e não um dicionário: dicionário perderia a
    ordem, e a ordem é a única organização que a pessoa deu aos campos dela.
    """

    LIMITE_DE_CAMPOS = 12

    name = models.CharField(max_length=80)
    damage = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)
    extras = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def clamp_extras(self) -> None:
        """Deixa em `extras` só pares de texto, aparados e em número sensato."""
        limpos = []
        for par in self.extras if isinstance(self.extras, list) else []:
            if not isinstance(par, (list, tuple)) or len(par) != 2:
                continue
            rotulo = str(par[0]).strip()[:40]
            valor = str(par[1]).strip()[:80]
            if rotulo:
                limpos.append([rotulo, valor])
        self.extras = limpos[: self.LIMITE_DE_CAMPOS]

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_extras()
        return super().save(*args, **kwargs)


class CharacterSkill(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class CharacterAbility(HabilidadeComCampos):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="abilities")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


def cor_oposta(cor: str) -> str:
    """A cor do outro lado do círculo — outra cor, e não outro tom da mesma.

    O pedaço que passa do máximo tem que se ler de relance como outra coisa:
    uma barra vermelha com um naco vermelho-claro na ponta parece a mesma vida,
    e é justamente o contrário do que ela quer dizer. Girar 180° na matiz dá
    isso para qualquer cor que o mestre escolha, sem tabela de exceções.

    Saturação e luminosidade são forçadas para baixo de um piso porque a
    oposta de um cinza é outro cinza, e a de um quase-preto é outro
    quase-preto: nos dois casos o naco sumiria dentro do trilho.
    """
    texto = (cor or "").strip().lstrip("#")
    if len(texto) == 3:
        texto = "".join(letra * 2 for letra in texto)
    try:
        vermelho, verde, azul = (int(texto[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        # A cor veio de um campo de texto livre; um azul serve de padrão.
        return "#3aa0ff"

    matiz, luz, saturacao = colorsys.rgb_to_hls(vermelho, verde, azul)
    matiz = (matiz + 0.5) % 1.0
    saturacao = max(saturacao, 0.7)
    luz = min(max(luz, 0.5), 0.62)
    vermelho, verde, azul = colorsys.hls_to_rgb(matiz, luz, saturacao)
    return "#%02x%02x%02x" % (
        round(vermelho * 255), round(verde * 255), round(azul * 255)
    )


class BarraDeFicha:
    """O que toda barra sabe dizer de si, seja de personagem, NPC ou inimigo.

    É um mixin de propriedades, e não uma classe abstrata de modelo: as três
    tabelas já existem com estas colunas, e transformá-las em herança mexeria
    nas migrações para não mudar uma linha do banco.

    O valor atual pode **passar do máximo** — a habilidade que dá vida
    temporária deixa o personagem em 15/12, e cortar em 12 apagaria justamente
    o que a habilidade fez. O trilho estica: com 15/12 ele passa a valer 15, os
    12 de vida de verdade ocupam 80% dele e os 3 de sobra ocupam o resto, na
    cor oposta.
    """

    @property
    def excedente(self) -> int:
        """O que passou do máximo, que é a vida temporária."""
        return max(self.current - self.max_value, 0)

    @property
    def total_na_barra(self) -> int:
        """Quanto o trilho inteiro representa. Sem excedente, é o máximo."""
        return max(self.current, self.max_value, 1)

    @property
    def fatia_base(self) -> float:
        """Porcentagem do trilho ocupada pela vida de verdade."""
        return round(max(min(self.current, self.max_value), 0) * 100 / self.total_na_barra, 2)

    @property
    def fatia_excedente(self) -> float:
        """Porcentagem do trilho ocupada pelo que passou do máximo."""
        return round(self.excedente * 100 / self.total_na_barra, 2)

    @property
    def cor_do_excedente(self) -> str:
        return cor_oposta(self.color)


class CharacterBar(BarraDeFicha, models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#ff4444")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class CharacterAttribute(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name} = {self.value}"


class NPCSkill(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCAbility(HabilidadeComCampos):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="abilities")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCBar(BarraDeFicha, models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#ff4444")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class NPCAttribute(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name} = {self.value}"


class Enemy(RetratoEnquadrado, RetratoNoMenu, PecaDoQuadro):
    """A ficha do inimigo: a mesma do personagem, sem inventário.

    Inimigo não carrega mochila. O que ele deixa cair vira item da campanha
    pela mão do mestre, então não há `InventorySlot` aqui — e é só isso que o
    separa do NPC. Também não tem os campos `hp_*`/`sp_*`: eles existem em
    `Character` e `NPC` por compatibilidade com os dados de antes das barras, e
    uma ficha nova não precisa herdar essa dívida.

    Nasce escondido. Quem revela é o mestre, quando quer que a mesa veja a
    barra de vida do que está na frente dela.
    """

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="enemies",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="enemies/", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_enemies",
    )
    visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    @property
    def retrato_atual(self):
        """O retrato, sem mais. Existe com o mesmo nome do de `Character`
        porque as peças do quadro passam pelo mesmo template: só o personagem
        tem estados, e o template não precisa saber disso."""
        return self.image

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        self.clamp_card()
        self.clamp_board()
        return super().save(*args, **kwargs)


class EnemySkill(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyAbility(HabilidadeComCampos):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="abilities")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyBar(BarraDeFicha, models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="bars")
    name = models.CharField(max_length=80)
    current = models.IntegerField(default=0)
    max_value = models.IntegerField(default=100)
    color = models.CharField(max_length=20, default="#e11d2e")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class EnemyAttribute(models.Model):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=80)
    value = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name} = {self.value}"


class Polaroid(RetratoEnquadrado, PecaDoQuadro):
    """Uma foto pregada no quadro da campanha.

    Não é ficha de ninguém: é o mapa da masmorra, o bilhete que o ladrão
    deixou, a cara do sujeito que os jogadores só viram de longe. Por isso não
    tem barra nem atributo — só imagem, legenda e o lugar onde foi pregada.

    A inclinação fica no banco em vez de sair de um random no CSS: um quadro
    que embaralha os ângulos a cada F5 cansa de olhar.
    """

    INCLINACAO_MAXIMA = 8

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="polaroids"
    )
    image = models.ImageField(upload_to="polaroids/", null=True, blank=True)
    caption = models.CharField(max_length=120, blank=True)
    tilt = models.SmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="polaroids",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.caption or f"Polaroid {self.pk}"

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        self.clamp_board()
        self.tilt = min(max(int(self.tilt or 0), -self.INCLINACAO_MAXIMA), self.INCLINACAO_MAXIMA)
        return super().save(*args, **kwargs)


class StickyNote(PecaDoQuadro):
    """Um post-it no quadro: só texto, escrito na hora.

    A polaroid guarda uma imagem; este guarda o que o mestre lembrou no meio da
    sessão e não quer perder — a senha do portão, quem traiu quem, o que o NPC
    prometeu. Por isso nasce vazio e é editado no lugar, sem formulário: o
    caminho entre lembrar e escrever tem que ser um clique.

    A cor e a inclinação ficam no banco pelo mesmo motivo da polaroid: um
    quadro que embaralha os dois a cada F5 cansa de olhar.
    """

    INCLINACAO_MAXIMA = 6
    # Não é um limite de escrita, é um freio contra abuso. Quinhentos caracteres
    # eram: um mestre que colava a profecia inteira batia neles no meio da
    # sessão e perdia o resto sem aviso. Vinte mil são umas cinco páginas — quem
    # chegar lá não está escrevendo um post-it, está tentando encher o banco.
    LIMITE_DO_TEXTO = 20000
    CORES = ["#f2e06a", "#f3a6b8", "#a8dfa0", "#9fd2f0"]

    # O tamanho fica no banco pelo mesmo motivo da cor e da inclinação: o quadro
    # é a campanha vista de cima, e o post-it que o mestre esticou para caber a
    # profecia inteira tem que estar esticado do outro lado da mesa também. Um
    # tamanho que só vive no navegador de quem arrastou não é um quadro
    # compartilhado, é um desenho particular.
    LARGURA_PADRAO = 180
    ALTURA_PADRAO = 118
    # Os limites não são gosto, são o que impede um arrastão perdido de deixar
    # uma peça de três pixels (impossível de pegar de volta) ou uma que cobre o
    # quadro inteiro. Dentro deles, qualquer tamanho serve.
    LARGURA_MINIMA = 120
    ALTURA_MINIMA = 72
    TAMANHO_MAXIMO = 900

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="notes"
    )
    text = models.TextField(blank=True, max_length=LIMITE_DO_TEXTO)
    color = models.CharField(max_length=20, default=CORES[0])
    tilt = models.SmallIntegerField(default=0)
    width = models.PositiveSmallIntegerField(default=LARGURA_PADRAO)
    height = models.PositiveSmallIntegerField(default=ALTURA_PADRAO)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notes",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return (self.text[:40] or f"Post-it {self.pk}")

    def clamp_tamanho(self) -> None:
        self.width = min(
            max(int(self.width or self.LARGURA_PADRAO), self.LARGURA_MINIMA),
            self.TAMANHO_MAXIMO,
        )
        self.height = min(
            max(int(self.height or self.ALTURA_PADRAO), self.ALTURA_MINIMA),
            self.TAMANHO_MAXIMO,
        )

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_board()
        self.clamp_tamanho()
        self.text = (self.text or "")[: self.LIMITE_DO_TEXTO]
        if self.color not in self.CORES:
            self.color = self.CORES[0]
        self.tilt = min(max(int(self.tilt or 0), -self.INCLINACAO_MAXIMA), self.INCLINACAO_MAXIMA)
        return super().save(*args, **kwargs)


class CharacterAttack(HabilidadeComCampos):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="attacks")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name}: {self.name}"


class EnemyAttack(HabilidadeComCampos):
    enemy = models.ForeignKey(Enemy, on_delete=models.CASCADE, related_name="attacks")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.enemy.name}: {self.name}"


class NPCAttack(HabilidadeComCampos):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="attacks")

    class Meta(HabilidadeComCampos.Meta):
        abstract = False

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name}: {self.name}"


class Item(RetratoEnquadrado):
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="items",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    image = models.ImageField(upload_to="items/", null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="items",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.name

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.clamp_framing()
        return super().save(*args, **kwargs)


class InventorySlot(models.Model):
    character = models.ForeignKey(Character, on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveIntegerField()
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="slots")

    class Meta:
        ordering = ["position"]
        unique_together = ("character", "position")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.character.name} slot {self.position}"

    @property
    def label(self) -> str:
        return f"Slot {self.position}"

    @property
    def row(self) -> int:
        return (self.position - 1) // INVENTORY_COLUMNS

    @property
    def col(self) -> int:
        return (self.position - 1) % INVENTORY_COLUMNS


class NPCInventorySlot(models.Model):
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveIntegerField()
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="npc_slots")

    class Meta:
        ordering = ["position"]
        unique_together = ("npc", "position")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.npc.name} slot {self.position}"

    @property
    def label(self) -> str:
        return f"Slot {self.position}"

    @property
    def row(self) -> int:
        return (self.position - 1) // INVENTORY_COLUMNS

    @property
    def col(self) -> int:
        return (self.position - 1) % INVENTORY_COLUMNS


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):  # noqa: ANN001
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=Character)
def create_character_slots(sender, instance: Character, created: bool, **kwargs):  # noqa: ANN001
    if created:
        instance.ensure_slots()


@receiver(post_save, sender=NPC)
def create_npc_slots(sender, instance: NPC, created: bool, **kwargs):  # noqa: ANN001
    if created:
        instance.ensure_slots()


class PasswordResetToken(models.Model):
    """O que fica guardado é o hash do token, nunca o token em si.

    O valor sorteado só existe dentro do link que vai por e-mail. Guardar ele
    cru no banco significaria que qualquer cópia do db.sqlite3 — backup,
    download, olhada no admin — vira senha de todo mundo.

    SHA-256 puro basta aqui: o token tem 32 bytes de aleatoriedade real, então
    não há o que adivinhar por força bruta. Senha de usuário é outra história e
    continua no hasher do Django.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Reset token for {self.user.username}"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def emitir(cls, user, validade: timedelta) -> str:
        """Cria o registro e devolve o token cru, que só o e-mail vê."""
        raw_token = secrets.token_urlsafe(32)
        cls.objects.create(
            user=user,
            token=cls.hash_token(raw_token),
            expires_at=timezone.now() + validade,
        )
        return raw_token


class AudioTrack(models.Model):
    """Uma faixa da trilha da campanha, apontando para um vídeo do YouTube.

    Guardamos o id de onze caracteres, não a URL inteira. A mesma faixa chega
    de cinco formatos diferentes (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`,
    com lista e tempo pendurados atrás), e normalizar na entrada evita ter a
    mesma música quatro vezes na lista por causa do formato do link.
    """

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="tracks"
    )
    youtube_id = models.CharField(max_length=20)
    title = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracks_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = ("campaign", "youtube_id")

    def __str__(self) -> str:  # pragma: no cover - simple display
        return self.title or self.youtube_id


class PlaybackState(models.Model):
    """O que está tocando numa campanha, agora.

    Ninguém transmite áudio: cada navegador toca o vídeo por conta própria e usa
    esta linha para saber o quê, de onde e se está rodando. Por isso
    `position_seconds` sozinho não basta — ele é a posição no instante
    `updated_at`. Quem chega depois calcula onde a faixa deveria estar somando o
    tempo decorrido, senão todo mundo entraria atrasado pelo tanto que demorou
    para pedir.
    """

    LOOP_OFF = "OFF"
    LOOP_ONE = "ONE"
    LOOP_ALL = "ALL"
    LOOP_CHOICES = (
        (LOOP_OFF, "Sem repetição"),
        (LOOP_ONE, "Repetir a faixa"),
        (LOOP_ALL, "Repetir a lista"),
    )

    # Depois deste tempo sem notícia do mestre, o estado não vale mais: a aba
    # dele caiu, fechou ou dormiu. Sem isso os jogadores ficariam tocando
    # sozinhos uma trilha que o mestre parou de ouvir faz meia hora.
    SEGUNDOS_ATE_ESFRIAR = 90

    campaign = models.OneToOneField(
        Campaign, on_delete=models.CASCADE, related_name="playback"
    )
    track = models.ForeignKey(
        AudioTrack, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_playing = models.BooleanField(default=False)
    position_seconds = models.FloatField(default=0)
    loop_mode = models.CharField(max_length=3, choices=LOOP_CHOICES, default=LOOP_OFF)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.campaign.name}: {self.track or 'nada'}"

    @property
    def esfriou(self) -> bool:
        idade = (timezone.now() - self.updated_at).total_seconds()
        return idade > self.SEGUNDOS_ATE_ESFRIAR

    def posicao_agora(self) -> float:
        """Onde a faixa está neste instante, não onde estava quando salvamos."""
        if not self.is_playing or self.esfriou:
            return self.position_seconds
        decorrido = (timezone.now() - self.updated_at).total_seconds()
        return self.position_seconds + max(decorrido, 0)


class AudioListener(models.Model):
    """Quem está com o áudio ligado nesta campanha, agora.

    A mesa quer ver quem está ouvindo, e o navegador não tem como avisar que
    fechou: aba que cai, notebook que dorme e internet que some são a regra, não
    a exceção. Por isso a presença não é um liga/desliga guardado no banco — é um
    horário. Quem está ouvindo diz "ainda estou aqui" de tempos em tempos, e quem
    parou de dizer some sozinho.

    O `unique_together` é o que impede a mesma pessoa de aparecer duas vezes por
    ter a campanha aberta em duas abas: a linha é da pessoa na mesa, não da aba.
    """

    # O batimento é a própria volta do polling, de dez em dez segundos — quem
    # está no áudio busca o estado pelo endereço da presença. Quatro voltas de
    # folga: menos que isso e a pessoa piscaria na roda toda vez que um pedido
    # demorasse; muito mais e um fone tirado no meio da sessão continuaria ali.
    SEGUNDOS_ATE_SUMIR = 45

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="listeners"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="audio_presence",
    )
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("campaign", "user")
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - simple display
        return f"{self.user} ouvindo {self.campaign.name}"

    @classmethod
    def limite(cls):
        return timezone.now() - timedelta(seconds=cls.SEGUNDOS_ATE_SUMIR)

    @classmethod
    def ativos(cls, campaign):
        """Só quem deu notícia há pouco. A linha velha continua lá, mas não conta."""
        return (
            cls.objects.filter(campaign=campaign, last_seen__gte=cls.limite())
            .select_related("user", "user__profile")
            .order_by("id")
        )

    @property
    def ativo(self) -> bool:
        return self.last_seen >= self.limite()


@receiver(post_save, sender=Campaign)
def create_playback_state(sender, instance: Campaign, created: bool, **kwargs):  # noqa: ANN001
    if created:
        PlaybackState.objects.create(campaign=instance)

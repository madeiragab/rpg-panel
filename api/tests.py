"""Testes da API.

Três coisas aqui que quebram calado se ninguém olhar:

  1. o token — quem entra, quem não entra, e o refresh que não pode valer duas
     vezes depois de rotacionado;
  2. o escopo — id de outra mesa tem que dar 404, não 403, porque o 403 já
     confirmaria que aquele id existe;
  3. o papel — o jogador atribuído mexe nos status da ficha dele e em nada mais.

Os testes que não são de token usam `force_authenticate` em vez de pedir token de
verdade. É de propósito: cada passada por `/api/token/` gasta cota do freio, e um
teste que falha porque outro teste gastou a cota não diz nada sobre a regra.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from hud.models import Campaign, Character, Item, NPC

User = get_user_model()

SENHA = "SenhaForte!2026"

# O CI roda com DEBUG desligado, que é onde o SECURE_SSL_REDIRECT liga. O
# cliente de teste fala http: sem isto toda chamada vira 301 antes de chegar
# na view e o teste mede o redirecionamento em vez da regra.
SEM_REDIRECT_HTTPS = override_settings(SECURE_SSL_REDIRECT=False)


def make_user(username):
    return User.objects.create_user(username=username, password=SENHA)


@SEM_REDIRECT_HTTPS
class BaseAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.mestre = make_user("mestre")
        self.jogador = make_user("jogador")
        self.estranho = make_user("estranho")
        self.campanha = Campaign.objects.create(name="Ossos", master=self.mestre)
        self.campanha.players.add(self.mestre, self.jogador)

    def tearDown(self):
        cache.clear()

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)


@SEM_REDIRECT_HTTPS
class TokenTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.ana = make_user("ana")

    def tearDown(self):
        cache.clear()

    def test_senha_certa_devolve_par_de_tokens(self):
        resposta = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("access", resposta.data)
        self.assertIn("refresh", resposta.data)

    def test_senha_errada_nao_devolve_token(self):
        resposta = self.client.post(
            reverse("api_token"), {"username": "ana", "password": "chute"}, format="json"
        )

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("access", resposta.data)

    def test_sem_token_a_api_responde_401(self):
        resposta = self.client.get(reverse("campaign-list"))

        self.assertEqual(resposta.status_code, 401)

    def test_com_access_valido_a_api_responde(self):
        access = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        ).data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resposta = self.client.get(reverse("campaign-list"))

        self.assertEqual(resposta.status_code, 200)

    def test_token_de_mentira_nao_passa(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer isso-nao-e-um-jwt")

        resposta = self.client.get(reverse("campaign-list"))

        self.assertEqual(resposta.status_code, 401)

    def test_refresh_devolve_access_novo(self):
        refresh = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        ).data["refresh"]

        resposta = self.client.post(
            reverse("api_token_refresh"), {"refresh": refresh}, format="json"
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("access", resposta.data)

    def test_refresh_usado_duas_vezes_e_recusado(self):
        """ROTATE + BLACKLIST_AFTER_ROTATION: o refresh antigo morre no uso."""
        refresh = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        ).data["refresh"]

        primeira = self.client.post(
            reverse("api_token_refresh"), {"refresh": refresh}, format="json"
        )
        segunda = self.client.post(
            reverse("api_token_refresh"), {"refresh": refresh}, format="json"
        )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 401)

    def test_logout_mata_o_refresh(self):
        refresh = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        ).data["refresh"]

        saida = self.client.post(
            reverse("api_token_logout"), {"refresh": refresh}, format="json"
        )
        depois = self.client.post(
            reverse("api_token_refresh"), {"refresh": refresh}, format="json"
        )

        self.assertIn(saida.status_code, (200, 205))
        self.assertEqual(depois.status_code, 401)

    def test_o_endereco_de_token_tem_freio(self):
        for _ in range(10):
            self.client.post(
                reverse("api_token"),
                {"username": "ana", "password": "chute"},
                format="json",
            )

        resposta = self.client.post(
            reverse("api_token"), {"username": "ana", "password": SENHA}, format="json"
        )

        self.assertEqual(resposta.status_code, 429)


class EscopoDeCampanhaTests(BaseAPITests):
    def test_a_lista_traz_so_as_minhas_campanhas(self):
        Campaign.objects.create(name="Alheia", master=self.estranho)
        self.como(self.jogador)

        resposta = self.client.get(reverse("campaign-list"))

        nomes = [c["name"] for c in resposta.data["results"]]
        self.assertEqual(nomes, ["Ossos"])

    def test_campanha_de_outro_da_404_e_nao_403(self):
        alheia = Campaign.objects.create(name="Alheia", master=self.estranho)
        self.como(self.jogador)

        resposta = self.client.get(reverse("campaign-detail", args=[alheia.pk]))

        self.assertEqual(resposta.status_code, 404)

    def test_quem_cria_campanha_fica_mestre_e_jogador(self):
        self.como(self.jogador)

        resposta = self.client.post(
            reverse("campaign-list"), {"name": "Nova"}, format="json"
        )

        self.assertEqual(resposta.status_code, 201)
        nova = Campaign.objects.get(name="Nova")
        self.assertEqual(nova.master, self.jogador)
        self.assertIn(self.jogador, nova.players.all())

    def test_jogador_nao_edita_a_campanha(self):
        self.como(self.jogador)

        resposta = self.client.patch(
            reverse("campaign-detail", args=[self.campanha.pk]),
            {"name": "Renomeada"},
            format="json",
        )

        self.assertEqual(resposta.status_code, 403)
        self.campanha.refresh_from_db()
        self.assertEqual(self.campanha.name, "Ossos")

    def test_mestre_edita_e_apaga_a_campanha(self):
        self.como(self.mestre)

        editar = self.client.patch(
            reverse("campaign-detail", args=[self.campanha.pk]),
            {"name": "Ossos II"},
            format="json",
        )
        self.assertEqual(editar.status_code, 200)

        apagar = self.client.delete(reverse("campaign-detail", args=[self.campanha.pk]))
        self.assertEqual(apagar.status_code, 204)
        self.assertFalse(Campaign.objects.filter(pk=self.campanha.pk).exists())

    def test_mestre_adiciona_e_remove_jogador(self):
        self.como(self.mestre)
        url = reverse("campaign-adicionar-jogador", args=[self.campanha.pk])

        entrar = self.client.post(url, {"user": self.estranho.pk}, format="json")
        self.assertEqual(entrar.status_code, 200)
        self.assertIn(self.estranho, self.campanha.players.all())

        sair = self.client.delete(
            reverse("campaign-remover-jogador", args=[self.campanha.pk, self.estranho.pk])
        )
        self.assertEqual(sair.status_code, 204)
        self.assertNotIn(self.estranho, self.campanha.players.all())

    def test_jogador_sai_e_a_ficha_dele_fica_sem_dono(self):
        personagem = Character.objects.create(
            name="Kai", created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.como(self.jogador)

        resposta = self.client.post(reverse("campaign-sair", args=[self.campanha.pk]))

        self.assertEqual(resposta.status_code, 204)
        personagem.refresh_from_db()
        self.assertIsNone(personagem.assigned_to)
        self.assertNotIn(self.jogador, self.campanha.players.all())

    def test_o_mestre_nao_sai_da_propria_campanha(self):
        self.como(self.mestre)

        resposta = self.client.post(reverse("campaign-sair", args=[self.campanha.pk]))

        self.assertEqual(resposta.status_code, 400)


class PersonagemTests(BaseAPITests):
    def setUp(self):
        super().setUp()
        self.personagem = Character.objects.create(
            name="Kai", created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador, hp_max=20, hp_current=20,
        )
        self.escondido = Character.objects.create(
            name="Segredo", created_by=self.mestre, campaign=self.campanha, visible=False
        )

    def test_jogador_nao_ve_o_personagem_escondido_dos_outros(self):
        self.como(self.jogador)

        resposta = self.client.get(reverse("character-list"))

        nomes = [p["name"] for p in resposta.data["results"]]
        self.assertIn("Kai", nomes)
        self.assertNotIn("Segredo", nomes)

    def test_mestre_ve_tudo(self):
        self.como(self.mestre)

        resposta = self.client.get(reverse("character-list"))

        nomes = [p["name"] for p in resposta.data["results"]]
        self.assertEqual(sorted(nomes), ["Kai", "Segredo"])

    def test_a_ficha_atribuida_aparece_mesmo_escondida(self):
        self.personagem.visible = False
        self.personagem.save()
        self.como(self.jogador)

        resposta = self.client.get(reverse("character-detail", args=[self.personagem.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_dono_muda_a_vida_mas_nao_o_nome(self):
        self.como(self.jogador)

        resposta = self.client.patch(
            reverse("character-detail", args=[self.personagem.pk]),
            {"hp_current": 7, "name": "Renomeado"},
            format="json",
        )

        self.assertEqual(resposta.status_code, 200)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.hp_current, 7)
        self.assertEqual(self.personagem.name, "Kai")

    def test_jogador_sem_vinculo_nao_mexe_na_ficha(self):
        outro = make_user("outro")
        self.campanha.players.add(outro)
        self.como(outro)

        resposta = self.client.patch(
            reverse("character-detail", args=[self.personagem.pk]),
            {"hp_current": 1},
            format="json",
        )

        self.assertEqual(resposta.status_code, 403)

    def test_mestre_cria_personagem_na_campanha_dele(self):
        self.como(self.mestre)

        resposta = self.client.post(
            reverse("character-list"),
            {"campaign": self.campanha.pk, "name": "Novo", "assigned_to": self.jogador.pk},
            format="json",
        )

        self.assertEqual(resposta.status_code, 201)
        criado = Character.objects.get(name="Novo")
        self.assertEqual(criado.created_by, self.mestre)

    def test_ninguem_cria_personagem_em_campanha_alheia(self):
        alheia = Campaign.objects.create(name="Alheia", master=self.estranho)
        self.como(self.mestre)

        resposta = self.client.post(
            reverse("character-list"),
            {"campaign": alheia.pk, "name": "Intruso"},
            format="json",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Character.objects.filter(name="Intruso").exists())

    def test_jogador_nao_apaga_a_propria_ficha(self):
        self.como(self.jogador)

        resposta = self.client.delete(
            reverse("character-detail", args=[self.personagem.pk])
        )

        self.assertEqual(resposta.status_code, 403)


class InventarioAPITests(BaseAPITests):
    def setUp(self):
        super().setUp()
        self.personagem = Character.objects.create(
            name="Kai", created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.item = Item.objects.create(name="Adaga", campaign=self.campanha)
        self.alheia = Campaign.objects.create(name="Alheia", master=self.estranho)
        self.item_alheio = Item.objects.create(name="Relíquia", campaign=self.alheia)
        self.url_slot = reverse("character-atribuir-slot", args=[self.personagem.pk, 1])

    def test_mestre_poe_e_tira_item_do_slot(self):
        self.como(self.mestre)

        por = self.client.put(self.url_slot, {"item": self.item.pk}, format="json")
        self.assertEqual(por.status_code, 200)
        self.assertEqual(self.personagem.slots.get(position=1).item, self.item)

        tirar = self.client.put(self.url_slot, {"item": None}, format="json")
        self.assertEqual(tirar.status_code, 200)
        self.assertIsNone(self.personagem.slots.get(position=1).item)

    def test_item_de_outra_campanha_e_recusado(self):
        self.como(self.mestre)

        resposta = self.client.put(
            self.url_slot, {"item": self.item_alheio.pk}, format="json"
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertIsNone(self.personagem.slots.get(position=1).item)

    def test_jogador_nao_mexe_no_inventario(self):
        self.como(self.jogador)

        resposta = self.client.put(self.url_slot, {"item": self.item.pk}, format="json")

        self.assertEqual(resposta.status_code, 403)

    def test_a_lista_de_itens_nao_vaza_a_de_outra_mesa(self):
        self.como(self.jogador)

        resposta = self.client.get(reverse("item-list"))

        nomes = [i["name"] for i in resposta.data["results"]]
        self.assertEqual(nomes, ["Adaga"])


class BarraAPITests(BaseAPITests):
    def setUp(self):
        super().setUp()
        self.personagem = Character.objects.create(
            name="Kai", created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.url_barras = reverse("character-barras", args=[self.personagem.pk])

    def _criar_barra(self):
        self.como(self.mestre)
        return self.client.post(
            self.url_barras, {"name": "Fúria", "max_value": 10}, format="json"
        )

    def test_mestre_cria_barra(self):
        resposta = self._criar_barra()

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(self.personagem.bars.get().name, "Fúria")

    def test_jogador_nao_cria_barra(self):
        self.como(self.jogador)

        resposta = self.client.post(
            self.url_barras, {"name": "Minha", "max_value": 10}, format="json"
        )

        self.assertEqual(resposta.status_code, 403)

    def test_dono_move_a_barra_mas_nao_muda_o_maximo(self):
        barra_id = self._criar_barra().data["id"]
        url = reverse("character-barra", args=[self.personagem.pk, barra_id])
        self.como(self.jogador)

        mover = self.client.patch(url, {"current": 3}, format="json")
        self.assertEqual(mover.status_code, 200)
        self.assertEqual(mover.data["current"], 3)

        esticar = self.client.patch(url, {"max_value": 999}, format="json")
        self.assertEqual(esticar.status_code, 403)

    def test_valor_acima_do_maximo_e_recusado(self):
        barra_id = self._criar_barra().data["id"]
        url = reverse("character-barra", args=[self.personagem.pk, barra_id])
        self.como(self.jogador)

        resposta = self.client.patch(url, {"current": 99}, format="json")

        self.assertEqual(resposta.status_code, 400)

    def test_so_o_mestre_apaga_barra(self):
        barra_id = self._criar_barra().data["id"]
        url = reverse("character-barra", args=[self.personagem.pk, barra_id])

        self.como(self.jogador)
        self.assertEqual(self.client.delete(url).status_code, 403)

        self.como(self.mestre)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.personagem.bars.count(), 0)


class NPCAPITests(BaseAPITests):
    def setUp(self):
        super().setUp()
        self.personagem = Character.objects.create(
            name="Kai", created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.npc = NPC.objects.create(
            name="Vulto", created_by=self.mestre, campaign=self.campanha
        )

    def test_jogador_nao_ve_npc_sem_vinculo(self):
        self.como(self.jogador)

        resposta = self.client.get(reverse("npc-detail", args=[self.npc.pk]))

        self.assertEqual(resposta.status_code, 404)

    def test_jogador_ve_npc_visivel_vinculado_a_ficha_dele(self):
        self.npc.visible = True
        self.npc.assigned_to_character = self.personagem
        self.npc.save()
        self.como(self.jogador)

        resposta = self.client.get(reverse("npc-detail", args=[self.npc.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_npc_visivel_sem_vinculo_continua_escondido(self):
        self.npc.visible = True
        self.npc.save()
        self.como(self.jogador)

        resposta = self.client.get(reverse("npc-detail", args=[self.npc.pk]))

        self.assertEqual(resposta.status_code, 404)

    def test_jogador_nao_edita_npc_que_ve(self):
        self.npc.visible = True
        self.npc.assigned_to_character = self.personagem
        self.npc.save()
        self.como(self.jogador)

        resposta = self.client.patch(
            reverse("npc-detail", args=[self.npc.pk]), {"name": "Outro"}, format="json"
        )

        self.assertEqual(resposta.status_code, 403)

    def test_mestre_mexe_no_inventario_do_npc(self):
        item = Item.objects.create(name="Adaga", campaign=self.campanha)
        self.como(self.mestre)

        resposta = self.client.put(
            reverse("npc-atribuir-slot", args=[self.npc.pk, 1]),
            {"item": item.pk},
            format="json",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.npc.slots.get(position=1).item, item)


class PerfilAPITests(BaseAPITests):
    def test_me_devolve_o_perfil_de_quem_pediu(self):
        self.como(self.jogador)

        resposta = self.client.get(reverse("api_me"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["username"], "jogador")

    def test_me_deixa_editar_apelido_mas_nao_papel(self):
        self.como(self.jogador)

        resposta = self.client.patch(
            reverse("api_me"), {"nickname": "jog", "role": "MASTER"}, format="json"
        )

        self.assertEqual(resposta.status_code, 200)
        perfil = self.jogador.profile
        perfil.refresh_from_db()
        self.assertEqual(perfil.nickname, "jog")
        self.assertEqual(perfil.role, "PLAYER")

    def test_me_exige_token(self):
        resposta = self.client.get(reverse("api_me"))

        self.assertEqual(resposta.status_code, 401)

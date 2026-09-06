"""
Duas coisas que este painel promete e que quebram calado se ninguém olhar:

  1. o inventário por slots — capacidade fixa, posição única, sem slot órfão
     quando a capacidade encolhe;
  2. o controle de acesso por papel — quem não é mestre nem jogador da campanha
     não entra, e só o mestre revela personagem escondido.

Os testes de página usam StaticFilesStorage no lugar do manifesto do WhiteNoise:
sem `collectstatic` o manifesto não existe, e o `{% static %}` derrubaria o teste
por um motivo que não tem nada a ver com a regra sendo testada.
"""

import base64
import json
import re
from io import BytesIO

from PIL import Image

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from hud.forms import (
    CharacterForm,
    encolher_imagem,
    ProfileEditForm,
    RegistrationForm,
    ResetPasswordForm,
)
from hud.models import (
    Campaign,
    Character,
    CharacterAbility,
    CharacterAttack,
    CharacterAttribute,
    CharacterBar,
    CharacterSkill,
    Enemy,
    EnemyAttribute,
    EnemyBar,
    InventorySlot,
    Item,
    NPC,
    NPCBar,
    NPCSkill,
    PasswordResetToken,
    Polaroid,
    StickyNote,
    UserProfile,
)

User = get_user_model()

# O CI roda com DEBUG desligado de propósito, e é aí que o settings.py liga o
# SECURE_SSL_REDIRECT. O cliente de teste fala http, então toda requisição
# viraria 301 antes de chegar na view e o teste mediria o redirecionamento em
# vez da regra. Quem precisa do cliente desliga só o redirecionamento — o resto
# do modo de produção continua valendo.
SEM_REDIRECT_HTTPS = override_settings(SECURE_SSL_REDIRECT=False)

SEM_MANIFESTO = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)


def make_user(username):
    return User.objects.create_user(username=username, password='SenhaForte!2026')


class PerfilTests(TestCase):
    def test_todo_usuario_nasce_com_perfil_de_jogador(self):
        ana = make_user('ana')

        perfil = UserProfile.objects.get(user=ana)
        self.assertEqual(perfil.role, UserProfile.ROLE_PLAYER)
        self.assertTrue(perfil.is_player)
        self.assertFalse(perfil.is_master)


class InventarioTests(TestCase):
    def setUp(self):
        self.ana = make_user('ana')

    def test_personagem_nasce_com_os_slots_da_capacidade(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.ana, inventory_capacity=16
        )

        self.assertEqual(personagem.slots.count(), 16)
        self.assertEqual(
            list(personagem.slots.values_list('position', flat=True)), list(range(1, 17))
        )

    def test_duas_posicoes_iguais_no_mesmo_personagem_sao_recusadas(self):
        personagem = Character.objects.create(name='Kai', created_by=self.ana)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventorySlot.objects.create(character=personagem, position=1)

    def test_reduzir_a_capacidade_apaga_os_slots_excedentes(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.ana, inventory_capacity=16
        )
        personagem.inventory_capacity = 8
        personagem.save()
        personagem.ensure_slots()

        self.assertEqual(personagem.slots.count(), 8)
        self.assertEqual(personagem.slots.filter(position__gt=8).count(), 0)

    def test_aumentar_a_capacidade_cria_so_o_que_falta_e_preserva_os_itens(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.ana, inventory_capacity=4
        )
        espada = Item.objects.create(name='Espada', created_by=self.ana)
        slot = personagem.slots.get(position=1)
        slot.item = espada
        slot.save()

        personagem.inventory_capacity = 8
        personagem.save()
        personagem.ensure_slots()

        self.assertEqual(personagem.slots.count(), 8)
        self.assertEqual(personagem.slots.get(position=1).item, espada)

    def test_apagar_o_item_esvazia_o_slot_sem_apagar_o_slot(self):
        # `on_delete=SET_NULL`: o slot é do personagem, não do item.
        personagem = Character.objects.create(name='Kai', created_by=self.ana)
        espada = Item.objects.create(name='Espada', created_by=self.ana)
        slot = personagem.slots.get(position=1)
        slot.item = espada
        slot.save()

        espada.delete()

        slot.refresh_from_db()
        self.assertIsNone(slot.item)
        self.assertTrue(personagem.slots.filter(position=1).exists())


class ClampDeStatusTests(TestCase):
    def setUp(self):
        self.ana = make_user('ana')

    def test_vida_atual_nao_passa_do_maximo_no_save(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.ana, hp_max=20, hp_current=999
        )

        personagem.refresh_from_db()
        self.assertEqual(personagem.hp_current, 20)

    def test_reduzir_o_maximo_puxa_a_vida_atual_junto(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.ana, hp_max=20, hp_current=20
        )
        personagem.hp_max = 5
        personagem.save()

        personagem.refresh_from_db()
        self.assertEqual(personagem.hp_current, 5)


@SEM_REDIRECT_HTTPS
class AcessoACampanhaTests(TestCase):
    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.estranho = make_user('estranho')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        # `master_dashboard` entra o mestre na lista de jogadores ao criar a
        # campanha. Sem isso o `?mode=player` derruba o próprio mestre em 403,
        # porque com `is_master` desligado ele não é mais nada na campanha.
        self.campanha.players.add(self.mestre, self.jogador)

    def test_visitante_sem_login_e_mandado_para_o_login(self):
        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)

    def test_quem_nao_e_da_campanha_leva_403(self):
        self.client.force_login(self.estranho)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        self.assertEqual(resposta.status_code, 403)

    @SEM_MANIFESTO
    def test_jogador_da_campanha_entra(self):
        self.client.force_login(self.jogador)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['is_master'])

    @SEM_MANIFESTO
    def test_jogador_nao_ve_personagem_escondido(self):
        Character.objects.create(
            name='Segredo', created_by=self.mestre, campaign=self.campanha, visible=False
        )
        Character.objects.create(
            name='Aberto', created_by=self.mestre, campaign=self.campanha, visible=True
        )
        self.client.force_login(self.jogador)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        nomes = [p.name for p in resposta.context['characters']]
        self.assertIn('Aberto', nomes)
        self.assertNotIn('Segredo', nomes)

    @SEM_MANIFESTO
    def test_mestre_ve_o_personagem_escondido(self):
        Character.objects.create(
            name='Segredo', created_by=self.mestre, campaign=self.campanha, visible=False
        )
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        self.assertTrue(resposta.context['is_master'])
        self.assertIn('Segredo', [p.name for p in resposta.context['characters']])

    @SEM_MANIFESTO
    def test_mestre_em_mode_player_perde_a_visao_de_mestre(self):
        # O painel deixa o mestre "olhar com os olhos do jogador". Se o
        # mode=player não desligar de fato o modo mestre, ele vira uma
        # maquiagem que mostra spoiler.
        Character.objects.create(
            name='Segredo', created_by=self.mestre, campaign=self.campanha, visible=False
        )
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk]) + '?mode=player'
        )

        self.assertFalse(resposta.context['is_master'])
        self.assertNotIn('Segredo', [p.name for p in resposta.context['characters']])


@SEM_REDIRECT_HTTPS
class ModificarStatusTests(TestCase):
    def setUp(self):
        self.mestre = make_user('mestre')
        self.dono = make_user('dono')
        self.outro = make_user('outro')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.dono, self.outro)
        self.personagem = Character.objects.create(
            name='Kai',
            created_by=self.mestre,
            campaign=self.campanha,
            assigned_to=self.dono,
            hp_max=10,
            hp_current=5,
        )

    def url(self):
        return reverse('modify_hp', args=[self.personagem.pk])

    def test_dono_altera_a_propria_vida(self):
        self.client.force_login(self.dono)

        resposta = self.client.post(self.url(), {'action': 'increase'})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()['hp_current'], 6)

    def test_mestre_altera_a_vida_de_qualquer_personagem_da_campanha(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(self.url(), {'action': 'decrease'})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()['hp_current'], 4)

    def test_outro_jogador_da_mesma_campanha_leva_403(self):
        # Estar na campanha não dá direito à ficha alheia.
        self.client.force_login(self.outro)

        resposta = self.client.post(self.url(), {'action': 'increase'})

        self.assertEqual(resposta.status_code, 403)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.hp_current, 5)

    def test_vida_nao_passa_do_maximo_nem_fica_negativa(self):
        self.client.force_login(self.mestre)
        for _ in range(10):
            self.client.post(self.url(), {'action': 'increase'})
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.hp_current, 10)

        for _ in range(20):
            self.client.post(self.url(), {'action': 'decrease'})
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.hp_current, 0)

    def test_acao_desconhecida_e_400(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(self.url(), {'action': 'teleportar'})

        self.assertEqual(resposta.status_code, 400)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(self.url())

        self.assertEqual(resposta.status_code, 405)


@SEM_REDIRECT_HTTPS
class VisibilidadeTests(TestCase):
    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha, visible=False
        )
        self.npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha, visible=False
        )

    def test_so_o_mestre_revela_personagem(self):
        self.client.force_login(self.jogador)
        resposta = self.client.post(
            reverse('toggle_character_visibility', args=[self.personagem.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.personagem.refresh_from_db()
        self.assertFalse(self.personagem.visible)

        self.client.force_login(self.mestre)
        resposta = self.client.post(
            reverse('toggle_character_visibility', args=[self.personagem.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.personagem.refresh_from_db()
        self.assertTrue(self.personagem.visible)

    def test_so_o_mestre_revela_npc(self):
        self.client.force_login(self.jogador)
        resposta = self.client.post(
            reverse('toggle_npc_visibility', args=[self.npc.pk])
        )
        self.assertEqual(resposta.status_code, 403)

        self.client.force_login(self.mestre)
        resposta = self.client.post(
            reverse('toggle_npc_visibility', args=[self.npc.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.npc.refresh_from_db()
        self.assertTrue(self.npc.visible)


class SenhaTests(TestCase):
    """Os AUTH_PASSWORD_VALIDATORS só valem se os forms os chamarem.

    Os três forms de senha são `forms.Form` escritos à mão, não os do Django:
    sem a chamada explícita a `validate_password`, a lista no settings.py é
    decoração e `123` entra como senha.
    """

    def test_cadastro_recusa_senha_fraca(self):
        form = RegistrationForm(data={
            'nome': 'Ana',
            'sobrenome': 'Silva',
            'apelido': 'ana',
            'email': 'ana@example.com',
            'senha': '123',
            'confirmacao': '123',
        })

        self.assertFalse(form.is_valid())

    def test_cadastro_aceita_senha_forte(self):
        form = RegistrationForm(data={
            'nome': 'Ana',
            'sobrenome': 'Silva',
            'apelido': 'ana',
            'email': 'ana@example.com',
            'senha': 'SenhaForte!2026',
            'confirmacao': 'SenhaForte!2026',
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_reset_recusa_senha_fraca(self):
        form = ResetPasswordForm(data={'password': '123', 'password_confirm': '123'})

        self.assertFalse(form.is_valid())

    def test_edicao_de_perfil_recusa_senha_fraca(self):
        ana = make_user('ana')
        form = ProfileEditForm(
            user=ana,
            data={
                'apelido': 'ana',
                'email': 'ana@example.com',
                'senha': '123',
                'confirmacao': '123',
            },
        )

        self.assertFalse(form.is_valid())


@SEM_MANIFESTO
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
@SEM_REDIRECT_HTTPS
class RecuperacaoDeSenhaTests(TestCase):
    def setUp(self):
        self.ana = make_user('ana')
        self.ana.email = 'ana@example.com'
        self.ana.save()

    def test_usuario_inexistente_responde_igual_ao_existente(self):
        """Resposta diferente para nome que existe entrega a lista de contas."""
        existente = self.client.post(reverse('forgot_password'), {'username': 'ana'})
        inexistente = self.client.post(reverse('forgot_password'), {'username': 'ninguem'})

        self.assertEqual(existente.status_code, inexistente.status_code)
        self.assertEqual(existente.content, inexistente.content)

    def test_so_o_usuario_existente_recebe_email_e_token(self):
        self.client.post(reverse('forgot_password'), {'username': 'ninguem'})
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetToken.objects.count(), 0)

        self.client.post(reverse('forgot_password'), {'username': 'ana'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetToken.objects.count(), 1)

    def test_usar_um_token_queima_os_outros_do_mesmo_usuario(self):
        self.client.post(reverse('forgot_password'), {'username': 'ana'})
        self.client.post(reverse('forgot_password'), {'username': 'ana'})
        primeiro, segundo = PasswordResetToken.objects.order_by('created_at')
        # O banco guarda o hash: o token que serve de link só existe no e-mail.
        cru = mail.outbox[0].body.split('/reset-password/')[1].split()[0].strip('/')

        resposta = self.client.post(
            reverse('reset_password', args=[cru]),
            {'password': 'OutraSenha!2026', 'password_confirm': 'OutraSenha!2026'},
        )
        self.assertEqual(resposta.status_code, 302)

        primeiro.refresh_from_db()
        segundo.refresh_from_db()
        self.assertTrue(primeiro.used)
        self.assertTrue(segundo.used)


@SEM_REDIRECT_HTTPS
class IsolamentoDeItemTests(TestCase):
    """Item de uma campanha não pode entrar no slot de outra.

    O endpoint recebe o id do item pelo POST e devolve nome e imagem na
    resposta: sem filtrar por campanha, ele vira uma janela para o material
    das outras mesas.
    """

    def setUp(self):
        self.mestre = make_user('mestre')
        self.minha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.alheia = Campaign.objects.create(name='Outra', master=make_user('estranho'))
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.minha
        )
        self.slot = self.personagem.slots.first()
        self.item_de_casa = Item.objects.create(name='Adaga', campaign=self.minha)
        self.item_alheio = Item.objects.create(name='Relíquia', campaign=self.alheia)
        self.client.force_login(self.mestre)

    def _atribuir(self, item):
        return self.client.post(
            reverse('assign_slot', args=[self.personagem.pk, self.slot.pk]),
            {'item_id': item.pk},
        )

    def test_item_da_propria_campanha_entra_no_slot(self):
        resposta = self._atribuir(self.item_de_casa)

        self.assertEqual(resposta.status_code, 200)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.item, self.item_de_casa)

    def test_item_de_outra_campanha_e_recusado(self):
        resposta = self._atribuir(self.item_alheio)

        self.assertEqual(resposta.status_code, 404)
        self.slot.refresh_from_db()
        self.assertIsNone(self.slot.item)


@SEM_REDIRECT_HTTPS
class InventarioDoNpcTests(TestCase):
    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha
        )
        self.slot = self.npc.slots.first()
        self.item = Item.objects.create(name='Adaga', campaign=self.campanha)

    def _atribuir(self):
        return self.client.post(
            reverse('assign_npc_slot', args=[self.npc.pk, self.slot.pk]),
            {'item_id': self.item.pk},
        )

    def test_mestre_poe_item_no_slot_do_npc(self):
        self.client.force_login(self.mestre)

        resposta = self._atribuir()

        self.assertEqual(resposta.status_code, 200)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.item, self.item)

    def test_slot_vazio_quando_o_post_vem_sem_item(self):
        self.slot.item = self.item
        self.slot.save()
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('assign_npc_slot', args=[self.npc.pk, self.slot.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.slot.refresh_from_db()
        self.assertIsNone(self.slot.item)

    def test_jogador_da_campanha_nao_mexe_no_inventario_do_npc(self):
        self.client.force_login(self.jogador)

        resposta = self._atribuir()

        self.assertEqual(resposta.status_code, 403)
        self.slot.refresh_from_db()
        self.assertIsNone(self.slot.item)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('assign_npc_slot', args=[self.npc.pk, self.slot.pk])
        )

        self.assertEqual(resposta.status_code, 405)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TokenDeResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana = make_user('ana')
        self.ana.email = 'ana@example.com'
        self.ana.save()

    def _token_do_email(self):
        corpo = mail.outbox[0].body
        return corpo.split('/reset-password/')[1].split()[0].strip('/')

    def test_o_banco_guarda_o_hash_e_nao_o_token_do_link(self):
        self.client.post(reverse('forgot_password'), {'username': 'ana'})

        cru = self._token_do_email()
        guardado = PasswordResetToken.objects.get()

        self.assertNotEqual(guardado.token, cru)
        self.assertEqual(guardado.token, PasswordResetToken.hash_token(cru))

    def test_o_link_do_email_funciona(self):
        self.client.post(reverse('forgot_password'), {'username': 'ana'})
        cru = self._token_do_email()

        resposta = self.client.post(
            reverse('reset_password', args=[cru]),
            {'password': 'OutraSenha!2026', 'password_confirm': 'OutraSenha!2026'},
        )

        self.assertEqual(resposta.status_code, 302)
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.check_password('OutraSenha!2026'))

    def test_o_hash_guardado_nao_serve_como_link(self):
        """Quem lesse o banco não poderia usar o que está lá como token."""
        self.client.post(reverse('forgot_password'), {'username': 'ana'})
        guardado = PasswordResetToken.objects.get()

        resposta = self.client.get(reverse('reset_password', args=[guardado.token]))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class LimiteDePedidosDeResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana = make_user('ana')
        self.ana.email = 'ana@example.com'
        self.ana.save()

    def tearDown(self):
        cache.clear()

    def test_a_conta_para_de_receber_email_depois_do_teto(self):
        for _ in range(10):
            self.client.post(reverse('forgot_password'), {'username': 'ana'})

        self.assertEqual(len(mail.outbox), 5)

    def test_a_resposta_continua_a_mesma_depois_do_teto(self):
        primeira = self.client.post(reverse('forgot_password'), {'username': 'ana'})
        for _ in range(10):
            self.client.post(reverse('forgot_password'), {'username': 'ana'})
        depois = self.client.post(reverse('forgot_password'), {'username': 'ana'})

        # Se a tela mudasse ao bater o teto, ela viraria outro jeito de
        # descobrir quais contas existem.
        self.assertEqual(primeira.status_code, depois.status_code)
        self.assertEqual(primeira.content, depois.content)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class CriacaoNaCampanhaTests(TestCase):
    """Os POST do campaign_detail: só o mestre cria, e sempre na campanha dele."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.mestre, self.jogador)
        self.url = reverse('campaign_detail', args=[self.campanha.pk])

    def test_mestre_cria_personagem_na_campanha(self):
        self.client.force_login(self.mestre)

        self.client.post(self.url, {
            'form_type': 'character',
            'character-name': 'Kai',
            'character-inventory_capacity': 16,
            'character-assigned_to': self.jogador.pk,
        })

        personagem = Character.objects.get(name='Kai')
        self.assertEqual(personagem.campaign, self.campanha)
        self.assertEqual(personagem.created_by, self.mestre)
        self.assertEqual(personagem.assigned_to, self.jogador)

    def test_jogador_nao_cria_personagem(self):
        self.client.force_login(self.jogador)

        self.client.post(self.url, {
            'form_type': 'character',
            'character-name': 'Intruso',
            'character-inventory_capacity': 16,
            'character-assigned_to': self.jogador.pk,
        })

        self.assertFalse(Character.objects.filter(name='Intruso').exists())

    def test_mestre_cria_item_e_npc_na_campanha(self):
        self.client.force_login(self.mestre)

        self.client.post(self.url, {'form_type': 'item', 'item-name': 'Adaga'})
        self.client.post(self.url, {
            'form_type': 'npc', 'npc-name': 'Vulto', 'npc-inventory_capacity': 16,
        })

        self.assertEqual(Item.objects.get(name='Adaga').campaign, self.campanha)
        self.assertEqual(NPC.objects.get(name='Vulto').campaign, self.campanha)

    def test_apagar_campanha_exige_o_nome_certo(self):
        self.client.force_login(self.mestre)

        self.client.post(self.url, {'form_type': 'delete_campaign', 'confirm_name': 'Ossos!'})
        self.assertTrue(Campaign.objects.filter(pk=self.campanha.pk).exists())

        self.client.post(self.url, {'form_type': 'delete_campaign', 'confirm_name': 'Ossos'})
        self.assertFalse(Campaign.objects.filter(pk=self.campanha.pk).exists())

    def test_jogador_nao_apaga_campanha(self):
        self.client.force_login(self.jogador)

        self.client.post(self.url, {'form_type': 'delete_campaign', 'confirm_name': 'Ossos'})

        self.assertTrue(Campaign.objects.filter(pk=self.campanha.pk).exists())


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class EdicaoDeFichaTests(TestCase):
    """Os POST do character_detail e do npc_detail."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.mestre, self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha
        )

    def test_mestre_adiciona_atributo_ao_personagem(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('character_detail', args=[self.personagem.pk]),
            {'form_type': 'attribute', 'attribute-name': 'Forca', 'attribute-value': '3'},
        )

        self.assertEqual(self.personagem.attributes.get().name, 'Forca')

    def test_atributo_sem_valor_avisa_em_vez_de_derrubar(self):
        """Este caminho quebrava com NameError por um ability.save() orfao."""
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('character_detail', args=[self.personagem.pk]),
            {'form_type': 'attribute', 'attribute-name': 'Forca', 'attribute-value': ''},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.personagem.attributes.count(), 0)

    def test_jogador_dono_da_ficha_nao_adiciona_atributo(self):
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('character_detail', args=[self.personagem.pk]),
            {'form_type': 'attribute', 'attribute-name': 'Forca', 'attribute-value': '3'},
        )

        self.assertEqual(self.personagem.attributes.count(), 0)

    def test_mestre_adiciona_pericia_ao_npc(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('npc_detail', args=[self.npc.pk]),
            {'form_type': 'skill', 'skill-name': 'Furtividade', 'skill-value': '+4',
             'skill-order': 0},
        )

        self.assertEqual(self.npc.skills.get().name, 'Furtividade')

    def test_jogador_sem_vinculo_nao_abre_o_npc(self):
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('npc_detail', args=[self.npc.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_barra_do_npc_recusa_get(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('add_npc_bar', args=[self.npc.pk]))

        self.assertEqual(resposta.status_code, 405)


@SEM_REDIRECT_HTTPS
class EnquadramentoDoRetratoTests(TestCase):
    """O zoom e o ponto do retrato: quem salva, o que e aparado, quem nao mexe."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha
        )

    def test_personagem_nasce_centrado_e_sem_zoom(self):
        self.assertEqual(self.personagem.image_zoom, 100)
        self.assertEqual(self.personagem.image_focus_x, 0.5)
        self.assertEqual(self.personagem.image_focus_y, 0.5)

    def test_mestre_guarda_o_enquadramento_do_personagem(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': '250', 'focus_x': '0.2', 'focus_y': '0.8'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.image_zoom, 250)
        self.assertAlmostEqual(self.personagem.image_focus_x, 0.2)
        self.assertAlmostEqual(self.personagem.image_focus_y, 0.8)

    def test_mestre_guarda_o_enquadramento_do_npc(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_npc_framing', args=[self.npc.pk]),
            {'zoom': '180', 'focus_x': '0', 'focus_y': '1'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.npc.refresh_from_db()
        self.assertEqual(self.npc.image_zoom, 180)
        self.assertAlmostEqual(self.npc.image_focus_x, 0.0)
        self.assertAlmostEqual(self.npc.image_focus_y, 1.0)

    def test_valor_fora_da_faixa_e_aparado_em_vez_de_entrar_no_banco(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': '9000', 'focus_x': '-3', 'focus_y': '7'},
        )

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.image_zoom, 400)
        self.assertAlmostEqual(self.personagem.image_focus_x, 0.0)
        self.assertAlmostEqual(self.personagem.image_focus_y, 1.0)

    def test_nan_e_recusado(self):
        """Um NaN atravessa o float() e escapa de qualquer min/max depois."""
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': '100', 'focus_x': 'nan', 'focus_y': '0.5'},
        )

        self.assertEqual(resposta.status_code, 400)
        self.personagem.refresh_from_db()
        self.assertAlmostEqual(self.personagem.image_focus_x, 0.5)

    def test_texto_no_lugar_do_numero_e_400(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': 'muito', 'focus_x': '0.5', 'focus_y': '0.5'},
        )

        self.assertEqual(resposta.status_code, 400)

    def test_jogador_dono_da_ficha_nao_enquadra(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': '400', 'focus_x': '0.1', 'focus_y': '0.1'},
        )

        self.assertEqual(resposta.status_code, 403)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.image_zoom, 100)

    def test_jogador_nao_enquadra_o_npc(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_npc_framing', args=[self.npc.pk]),
            {'zoom': '400', 'focus_x': '0.1', 'focus_y': '0.1'},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('update_character_framing', args=[self.personagem.pk])
        )

        self.assertEqual(resposta.status_code, 405)


class RetratoDaFichaTests(TestCase):
    """O upload: quais formatos entram e o que acontece com o corte antigo."""

    # 1x1 transparente, o menor GIF89a valido que existe.
    GIF = base64.b64decode(
        'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
    )

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )

    def _form(self, arquivo=None):
        arquivos = {}
        if arquivo is not None:
            arquivos['character-image'] = arquivo
        return CharacterForm(
            {
                'character-name': 'Kai',
                'character-inventory_capacity': '16',
                'character-assigned_to': str(self.jogador.pk),
            },
            arquivos,
            instance=self.personagem,
            prefix='character',
        )

    def test_gif_e_aceito(self):
        gif = SimpleUploadedFile('bicho.gif', self.GIF, content_type='image/gif')

        form = self._form(gif)

        self.assertTrue(form.is_valid(), form.errors)

    def test_arquivo_que_nao_e_imagem_e_recusado(self):
        falso = SimpleUploadedFile(
            'bicho.gif', b'nao sou um gif', content_type='image/gif'
        )

        form = self._form(falso)

        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_foto_nova_devolve_o_enquadramento_ao_centro(self):
        """O corte e da foto antiga: mante-lo cortaria a nova em outro lugar."""
        self.personagem.image_zoom = 300
        self.personagem.image_focus_x = 0.1
        self.personagem.image_focus_y = 0.9
        self.personagem.save()
        gif = SimpleUploadedFile('outro.gif', self.GIF, content_type='image/gif')

        form = self._form(gif)
        self.assertTrue(form.is_valid(), form.errors)
        ficha = form.save(commit=False)   # commit=False nao escreve em MEDIA_ROOT

        self.assertEqual(ficha.image_zoom, 100)
        self.assertEqual(ficha.image_focus_x, 0.5)
        self.assertEqual(ficha.image_focus_y, 0.5)

    def test_salvar_a_ficha_sem_trocar_a_foto_preserva_o_corte(self):
        self.personagem.image_zoom = 300
        self.personagem.image_focus_x = 0.1
        self.personagem.save()

        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        ficha = form.save(commit=False)

        self.assertEqual(ficha.image_zoom, 300)
        self.assertAlmostEqual(ficha.image_focus_x, 0.1)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class FichaDeInimigoTests(TestCase):
    """A ficha do inimigo: quem cria, quem abre e o que ela nao tem."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.estranho = make_user('estranho')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )

    def test_inimigo_nao_tem_inventario(self):
        """O que separa o inimigo do NPC: nenhum slot, nem relacao para eles."""
        self.assertFalse(hasattr(self.inimigo, 'slots'))
        self.assertFalse(hasattr(self.inimigo, 'inventory_capacity'))

    def test_inimigo_nasce_escondido(self):
        self.assertFalse(self.inimigo.visible)

    def test_mestre_cria_inimigo_na_campanha(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]),
            {'form_type': 'enemy', 'enemy-name': 'Hidra'},
        )

        self.assertTrue(self.campanha.enemies.filter(name='Hidra').exists())

    def test_jogador_nao_cria_inimigo(self):
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]),
            {'form_type': 'enemy', 'enemy-name': 'Hidra'},
        )

        self.assertFalse(self.campanha.enemies.filter(name='Hidra').exists())

    def test_mestre_abre_a_ficha(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('enemy_detail', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_jogador_nao_abre_inimigo_escondido(self):
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('enemy_detail', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_jogador_abre_o_inimigo_revelado_em_leitura(self):
        self.inimigo.visible = True
        self.inimigo.save()
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('enemy_detail', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['is_master'])

    def test_quem_nao_e_da_campanha_leva_403_mesmo_revelado(self):
        self.inimigo.visible = True
        self.inimigo.save()
        self.client.force_login(self.estranho)

        resposta = self.client.get(reverse('enemy_detail', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 403)

    def test_so_o_mestre_revela(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('toggle_enemy_visibility', args=[self.inimigo.pk])
        )

        self.assertEqual(resposta.status_code, 403)
        self.inimigo.refresh_from_db()
        self.assertFalse(self.inimigo.visible)

    def test_mestre_revela_e_esconde(self):
        self.client.force_login(self.mestre)

        self.client.post(reverse('toggle_enemy_visibility', args=[self.inimigo.pk]))
        self.inimigo.refresh_from_db()
        self.assertTrue(self.inimigo.visible)

        self.client.post(reverse('toggle_enemy_visibility', args=[self.inimigo.pk]))
        self.inimigo.refresh_from_db()
        self.assertFalse(self.inimigo.visible)

    def test_mestre_adiciona_atributo_e_pericia(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('enemy_detail', args=[self.inimigo.pk]),
            {'form_type': 'attribute', 'attribute-name': 'Forca', 'attribute-value': '9'},
        )
        self.client.post(
            reverse('enemy_detail', args=[self.inimigo.pk]),
            {'form_type': 'skill', 'skill-name': 'Rastrear', 'skill-value': '+6',
             'skill-order': 0},
        )

        self.assertEqual(self.inimigo.attributes.get().name, 'Forca')
        self.assertEqual(self.inimigo.skills.get().name, 'Rastrear')

    def test_jogador_com_o_inimigo_revelado_nao_edita(self):
        self.inimigo.visible = True
        self.inimigo.save()
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('enemy_detail', args=[self.inimigo.pk]),
            {'form_type': 'attribute', 'attribute-name': 'Forca', 'attribute-value': '9'},
        )

        self.assertEqual(self.inimigo.attributes.count(), 0)

    def test_mestre_apaga_o_inimigo(self):
        self.client.force_login(self.mestre)

        self.client.post(reverse('delete_enemy', args=[self.inimigo.pk]))

        self.assertFalse(Enemy.objects.filter(pk=self.inimigo.pk).exists())

    def test_jogador_nao_apaga_o_inimigo(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(reverse('delete_enemy', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(Enemy.objects.filter(pk=self.inimigo.pk).exists())


@SEM_REDIRECT_HTTPS
class BarrasDoInimigoTests(TestCase):
    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha, visible=True
        )

    def _criar_barra(self):
        return EnemyBar.objects.create(
            enemy=self.inimigo, name='Vida', current=10, max_value=10
        )

    def test_mestre_cria_barra_cheia(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('add_enemy_bar', args=[self.inimigo.pk]),
            {'name': 'Vida', 'max_value': '40', 'color': '#e11d2e'},
        )

        self.assertEqual(resposta.status_code, 200)
        barra = self.inimigo.bars.get()
        self.assertEqual(barra.current, 40)
        self.assertEqual(barra.max_value, 40)

    def test_barra_sem_nome_e_recusada(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('add_enemy_bar', args=[self.inimigo.pk]),
            {'name': '  ', 'max_value': '40'},
        )

        self.assertEqual(self.inimigo.bars.count(), 0)

    def test_barra_nao_passa_do_maximo_nem_fica_negativa(self):
        barra = self._criar_barra()
        self.client.force_login(self.mestre)
        url = reverse('modify_enemy_bar', args=[self.inimigo.pk, barra.pk])

        self.client.post(url, {'action': 'increase'})
        barra.refresh_from_db()
        self.assertEqual(barra.current, 10)

        for _ in range(12):
            self.client.post(url, {'action': 'decrease'})
        barra.refresh_from_db()
        self.assertEqual(barra.current, 0)

    def test_jogador_nao_mexe_na_barra(self):
        barra = self._criar_barra()
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('modify_enemy_bar', args=[self.inimigo.pk, barra.pk]),
            {'action': 'decrease'},
        )

        self.assertEqual(resposta.status_code, 403)
        barra.refresh_from_db()
        self.assertEqual(barra.current, 10)

    def test_barra_de_outro_inimigo_nao_entra_pela_url(self):
        outro = Enemy.objects.create(
            name='Quimera', created_by=self.mestre, campaign=self.campanha
        )
        barra = self._criar_barra()
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('modify_enemy_bar', args=[outro.pk, barra.pk]),
            {'action': 'decrease'},
        )

        self.assertEqual(resposta.status_code, 404)

    def test_mestre_apaga_a_barra(self):
        barra = self._criar_barra()
        self.client.force_login(self.mestre)

        self.client.post(reverse('delete_enemy_bar', args=[self.inimigo.pk, barra.pk]))

        self.assertEqual(self.inimigo.bars.count(), 0)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('add_enemy_bar', args=[self.inimigo.pk]))

        self.assertEqual(resposta.status_code, 405)

    def test_mestre_enquadra_o_retrato_do_inimigo(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_enemy_framing', args=[self.inimigo.pk]),
            {'zoom': '220', 'focus_x': '0.3', 'focus_y': '0.7'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.inimigo.refresh_from_db()
        self.assertEqual(self.inimigo.image_zoom, 220)
        self.assertAlmostEqual(self.inimigo.image_focus_x, 0.3)

    def test_jogador_nao_enquadra_o_inimigo(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_enemy_framing', args=[self.inimigo.pk]),
            {'zoom': '220', 'focus_x': '0.3', 'focus_y': '0.7'},
        )

        self.assertEqual(resposta.status_code, 403)


@SEM_REDIRECT_HTTPS
class EnquadramentoDeItemEAvatarTests(TestCase):
    """O corte tambem vale para a imagem do item e para o avatar do perfil."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.item = Item.objects.create(name='Adaga', campaign=self.campanha)

    def test_item_nasce_centrado_e_sem_zoom(self):
        self.assertEqual(self.item.image_zoom, 100)
        self.assertEqual(self.item.image_focus_x, 0.5)

    def test_mestre_enquadra_a_imagem_do_item(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_item_framing', args=[self.item.pk]),
            {'zoom': '260', 'focus_x': '0.15', 'focus_y': '0.85'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.image_zoom, 260)
        self.assertAlmostEqual(self.item.image_focus_x, 0.15)
        self.assertAlmostEqual(self.item.image_focus_y, 0.85)

    def test_jogador_nao_enquadra_item_da_mesa(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_item_framing', args=[self.item.pk]),
            {'zoom': '260', 'focus_x': '0.15', 'focus_y': '0.85'},
        )

        self.assertEqual(resposta.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.image_zoom, 100)

    def test_item_de_outra_campanha_nao_e_enquadrado_por_este_mestre(self):
        outro_mestre = make_user('outro')
        outra = Campaign.objects.create(name='Cinzas', master=outro_mestre)
        alheio = Item.objects.create(name='Elmo', campaign=outra)
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_item_framing', args=[alheio.pk]),
            {'zoom': '200', 'focus_x': '0.5', 'focus_y': '0.5'},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_valor_do_item_fora_da_faixa_e_aparado(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_item_framing', args=[self.item.pk]),
            {'zoom': '9000', 'focus_x': '-1', 'focus_y': '9'},
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.image_zoom, 400)
        self.assertAlmostEqual(self.item.image_focus_x, 0.0)
        self.assertAlmostEqual(self.item.image_focus_y, 1.0)

    def test_cada_um_enquadra_o_proprio_avatar(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_avatar_framing'),
            {'zoom': '180', 'focus_x': '0.25', 'focus_y': '0.75'},
        )

        self.assertEqual(resposta.status_code, 200)
        perfil = UserProfile.objects.get(user=self.jogador)
        self.assertEqual(perfil.image_zoom, 180)
        self.assertAlmostEqual(perfil.image_focus_x, 0.25)

    def test_enquadrar_o_avatar_nao_mexe_no_dos_outros(self):
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('update_avatar_framing'),
            {'zoom': '180', 'focus_x': '0.25', 'focus_y': '0.75'},
        )

        self.assertEqual(UserProfile.objects.get(user=self.mestre).image_zoom, 100)

    def test_avatar_recusa_get(self):
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('update_avatar_framing'))

        self.assertEqual(resposta.status_code, 405)

    def test_o_slot_recebe_o_corte_junto_com_a_imagem(self):
        """Sem isto o slot recem-preenchido cortaria pelo meio ate recarregar."""
        self.item.image_zoom = 240
        self.item.image_focus_x = 0.2
        self.item.save()
        personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        slot = personagem.slots.first()
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('assign_slot', args=[personagem.pk, slot.pk]),
            {'item_id': self.item.pk},
        )

        dados = resposta.json()
        self.assertEqual(dados['itemZoom'], 240)
        self.assertAlmostEqual(dados['itemFocusX'], 0.2)

    def test_slot_esvaziado_volta_ao_corte_neutro(self):
        personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        slot = personagem.slots.first()
        slot.item = self.item
        slot.save()
        self.client.force_login(self.mestre)

        dados = self.client.post(
            reverse('assign_slot', args=[personagem.pk, slot.pk])
        ).json()

        self.assertEqual(dados['itemName'], 'Vazio')
        self.assertEqual(dados['itemZoom'], 100)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class QuadroDaCampanhaTests(TestCase):
    """Arrastar peca, pregar polaroid e mexer nas barras de la."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )

    def _mover(self, kind, pk, x='0.25', y='0.75'):
        return self.client.post(
            reverse('move_board_piece', args=[self.campanha.pk]),
            {'kind': kind, 'id': pk, 'x': x, 'y': y},
        )

    def test_peca_nasce_sem_posicao(self):
        """Nulo quer dizer 'nunca foi arrastada', e a grade cuida dessas."""
        self.assertIsNone(self.personagem.board_x)
        self.assertIsNone(self.inimigo.board_y)

    def test_mestre_arrasta_personagem(self):
        self.client.force_login(self.mestre)

        resposta = self._mover('character', self.personagem.pk)

        self.assertEqual(resposta.status_code, 200)
        self.personagem.refresh_from_db()
        self.assertAlmostEqual(self.personagem.board_x, 0.25)
        self.assertAlmostEqual(self.personagem.board_y, 0.75)

    def test_mestre_arrasta_inimigo(self):
        self.client.force_login(self.mestre)

        self._mover('enemy', self.inimigo.pk, x='0.1', y='0.2')

        self.inimigo.refresh_from_db()
        self.assertAlmostEqual(self.inimigo.board_x, 0.1)

    def test_posicao_fora_do_quadro_e_aparada(self):
        self.client.force_login(self.mestre)

        self._mover('character', self.personagem.pk, x='-4', y='9')

        self.personagem.refresh_from_db()
        self.assertAlmostEqual(self.personagem.board_x, 0.0)
        self.assertAlmostEqual(self.personagem.board_y, 1.0)

    def test_nan_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self._mover('character', self.personagem.pk, x='nan')

        self.assertEqual(resposta.status_code, 400)
        self.personagem.refresh_from_db()
        self.assertIsNone(self.personagem.board_x)

    def test_tipo_desconhecido_e_400(self):
        self.client.force_login(self.mestre)

        resposta = self._mover('item', self.personagem.pk)

        self.assertEqual(resposta.status_code, 400)

    def test_jogador_nao_arruma_o_quadro(self):
        self.client.force_login(self.jogador)

        resposta = self._mover('character', self.personagem.pk)

        self.assertEqual(resposta.status_code, 403)
        self.personagem.refresh_from_db()
        self.assertIsNone(self.personagem.board_x)

    def test_peca_de_outra_campanha_nao_entra_pela_url(self):
        """O filtro por campanha e o que impede mover a peca da mesa alheia."""
        outra = Campaign.objects.create(name='Cinzas', master=self.mestre)
        alheio = Character.objects.create(
            name='Nix', created_by=self.mestre, campaign=outra,
            assigned_to=self.jogador,
        )
        self.client.force_login(self.mestre)

        resposta = self._mover('character', alheio.pk)

        self.assertEqual(resposta.status_code, 404)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('move_board_piece', args=[self.campanha.pk])
        )

        self.assertEqual(resposta.status_code, 405)

    def test_aba_do_quadro_so_aparece_para_o_mestre(self):
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertNotContains(resposta, 'id="board-tab"')

    def test_o_que_esta_oculto_nao_vira_peca(self):
        """O inimigo nasce escondido: enquanto a mesa nao pode ver, nao entra."""
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertContains(resposta, 'id="board-tab"')
        self.assertEqual(list(resposta.context['board_enemies']), [])

    def test_revelar_poe_a_peca_no_quadro(self):
        self.inimigo.visible = True
        self.inimigo.save()
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertEqual(list(resposta.context['board_enemies']), [self.inimigo])

    def test_personagem_escondido_tambem_sai_do_quadro(self):
        self.personagem.visible = False
        self.personagem.save()
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertEqual(list(resposta.context['board_characters']), [])

    def test_o_jogador_nao_recebe_o_quadro(self):
        """A mesa nao ve o quadro de forma alguma, nem no HTML."""
        self.personagem.visible = True
        self.personagem.save()
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertNotContains(resposta, 'id="quadro"')
        self.assertNotContains(resposta, 'data-kind="character"')

    def test_mestre_em_mode_player_tambem_nao_recebe_o_quadro(self):
        """O mestre so consegue espiar o modo leitura se tambem for da mesa."""
        self.campanha.players.add(self.mestre)
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk]) + '?mode=player'
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'id="quadro"')

    def test_mestre_prega_polaroid(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]),
            {'form_type': 'polaroid', 'polaroid-caption': 'O mapa da cripta'},
        )

        self.assertEqual(self.campanha.polaroids.get().caption, 'O mapa da cripta')

    def test_jogador_nao_prega_polaroid(self):
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]),
            {'form_type': 'polaroid', 'polaroid-caption': 'O mapa da cripta'},
        )

        self.assertEqual(self.campanha.polaroids.count(), 0)

    def test_inclinacao_da_polaroid_fica_na_faixa(self):
        polaroid = Polaroid.objects.create(campaign=self.campanha, tilt=90)

        self.assertEqual(polaroid.tilt, Polaroid.INCLINACAO_MAXIMA)

    def test_mestre_tira_a_polaroid_do_quadro(self):
        polaroid = Polaroid.objects.create(campaign=self.campanha, caption='Mapa')
        self.client.force_login(self.mestre)

        self.client.post(reverse('delete_polaroid', args=[polaroid.pk]))

        self.assertEqual(self.campanha.polaroids.count(), 0)

    def test_jogador_nao_tira_a_polaroid(self):
        polaroid = Polaroid.objects.create(campaign=self.campanha, caption='Mapa')
        self.client.force_login(self.jogador)

        resposta = self.client.post(reverse('delete_polaroid', args=[polaroid.pk]))

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.campanha.polaroids.count(), 1)

    def test_polaroid_tambem_se_arrasta(self):
        polaroid = Polaroid.objects.create(campaign=self.campanha, caption='Mapa')
        self.client.force_login(self.mestre)

        self._mover('polaroid', polaroid.pk, x='0.4', y='0.6')

        polaroid.refresh_from_db()
        self.assertAlmostEqual(polaroid.board_x, 0.4)


@SEM_REDIRECT_HTTPS
class PassoDaBarraTests(TestCase):
    """O quadro tira mais de um por clique; a ficha continua tirando um."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )
        self.barra = EnemyBar.objects.create(
            enemy=self.inimigo, name='Vida', current=20, max_value=20
        )

    def _mexer(self, **extra):
        return self.client.post(
            reverse('modify_enemy_bar', args=[self.inimigo.pk, self.barra.pk]),
            {'action': 'decrease', **extra},
        )

    def test_sem_amount_anda_um(self):
        self.client.force_login(self.mestre)

        self._mexer()

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 19)

    def test_amount_anda_o_que_pediu(self):
        self.client.force_login(self.mestre)

        self._mexer(amount='5')

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 15)

    def test_amount_nao_derruba_abaixo_de_zero(self):
        self.client.force_login(self.mestre)

        self._mexer(amount='999')

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 0)

    def test_amount_lixo_vira_um(self):
        self.client.force_login(self.mestre)

        self._mexer(amount='muito')

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 19)

    def test_amount_negativo_nao_inverte_a_acao(self):
        """Sem o piso em 1, 'decrease' com amount -5 curaria em vez de ferir."""
        self.client.force_login(self.mestre)

        self._mexer(amount='-5')

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 19)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class PostItDoQuadroTests(TestCase):
    """O post-it nasce vazio e e escrito no lugar."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)

    def test_mestre_prega_post_it_vazio(self):
        """Sem formulario: o caminho entre lembrar e escrever e um clique."""
        self.client.force_login(self.mestre)

        self.client.post(reverse('create_sticky_note', args=[self.campanha.pk]))

        recado = self.campanha.notes.get()
        self.assertEqual(recado.text, '')
        self.assertIn(recado.color, StickyNote.CORES)

    def test_a_cor_gira_em_vez_de_sortear(self):
        self.client.force_login(self.mestre)

        for _ in range(3):
            self.client.post(reverse('create_sticky_note', args=[self.campanha.pk]))

        cores = list(self.campanha.notes.values_list('color', flat=True))
        self.assertEqual(cores, StickyNote.CORES[:3])

    def test_jogador_nao_prega_post_it(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('create_sticky_note', args=[self.campanha.pk])
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.campanha.notes.count(), 0)

    def test_mestre_escreve_no_post_it(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sticky_note', args=[recado.pk]),
            {'text': 'A senha do portao e "cinza"'},
        )

        self.assertEqual(resposta.status_code, 200)
        recado.refresh_from_db()
        self.assertEqual(recado.text, 'A senha do portao e "cinza"')

    def test_apagar_o_texto_deixa_o_post_it_vazio(self):
        recado = StickyNote.objects.create(campaign=self.campanha, text='algo')
        self.client.force_login(self.mestre)

        self.client.post(reverse('update_sticky_note', args=[recado.pk]), {'text': ''})

        recado.refresh_from_db()
        self.assertEqual(recado.text, '')

    def test_jogador_nao_escreve_no_post_it(self):
        recado = StickyNote.objects.create(campaign=self.campanha, text='segredo')
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_sticky_note', args=[recado.pk]), {'text': 'invadido'}
        )

        self.assertEqual(resposta.status_code, 403)
        recado.refresh_from_db()
        self.assertEqual(recado.text, 'segredo')

    def test_mestre_estica_o_post_it_para_os_lados(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sticky_note', args=[recado.pk]),
            {'width': '420', 'height': '260'},
        )

        self.assertEqual(resposta.status_code, 200)
        recado.refresh_from_db()
        self.assertEqual((recado.width, recado.height), (420, 260))

    def test_mudar_o_tamanho_nao_apaga_o_texto(self):
        # O pedido de tamanho não manda texto nenhum. Enquanto a view lia
        # `text` com padrão vazio, esticar a peça limpava a anotação inteira.
        recado = StickyNote.objects.create(campaign=self.campanha, text='a senha e cinza')
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_sticky_note', args=[recado.pk]), {'width': '300'}
        )

        recado.refresh_from_db()
        self.assertEqual(recado.text, 'a senha e cinza')
        self.assertEqual(recado.width, 300)

    def test_escrever_nao_mexe_no_tamanho(self):
        recado = StickyNote.objects.create(campaign=self.campanha, width=400, height=300)
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_sticky_note', args=[recado.pk]), {'text': 'outra coisa'}
        )

        recado.refresh_from_db()
        self.assertEqual((recado.width, recado.height), (400, 300))

    def test_tamanho_fora_da_faixa_e_puxado_para_dentro(self):
        # Um arrastão perdido não pode deixar um papel de tres pixels, que
        # ninguem consegue pegar de volta para esticar.
        minusculo = StickyNote.objects.create(campaign=self.campanha, width=3, height=1)
        gigante = StickyNote.objects.create(campaign=self.campanha, width=99999, height=99999)

        self.assertEqual(minusculo.width, StickyNote.LARGURA_MINIMA)
        self.assertEqual(minusculo.height, StickyNote.ALTURA_MINIMA)
        self.assertEqual(gigante.width, StickyNote.TAMANHO_MAXIMO)
        self.assertEqual(gigante.height, StickyNote.TAMANHO_MAXIMO)

    def test_tamanho_ilegivel_e_recusado(self):
        recado = StickyNote.objects.create(campaign=self.campanha, width=200)
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sticky_note', args=[recado.pk]), {'width': 'largo'}
        )

        self.assertEqual(resposta.status_code, 400)
        recado.refresh_from_db()
        self.assertEqual(recado.width, 200)

    def test_jogador_nao_estica_o_post_it(self):
        recado = StickyNote.objects.create(campaign=self.campanha, width=200)
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_sticky_note', args=[recado.pk]), {'width': '800'}
        )

        self.assertEqual(resposta.status_code, 403)
        recado.refresh_from_db()
        self.assertEqual(recado.width, 200)

    def test_texto_gigante_e_cortado_no_limite(self):
        recado = StickyNote.objects.create(
            campaign=self.campanha, text='x' * (StickyNote.LIMITE_DO_TEXTO + 200)
        )

        self.assertEqual(len(recado.text), StickyNote.LIMITE_DO_TEXTO)

    def test_cor_de_fora_da_lista_volta_para_a_primeira(self):
        recado = StickyNote.objects.create(campaign=self.campanha, color='#000000')

        self.assertEqual(recado.color, StickyNote.CORES[0])

    def test_inclinacao_fica_na_faixa(self):
        recado = StickyNote.objects.create(campaign=self.campanha, tilt=-90)

        self.assertEqual(recado.tilt, -StickyNote.INCLINACAO_MAXIMA)

    def test_post_it_tambem_se_arrasta(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('move_board_piece', args=[self.campanha.pk]),
            {'kind': 'note', 'id': recado.pk, 'x': '0.3', 'y': '0.7'},
        )

        recado.refresh_from_db()
        self.assertAlmostEqual(recado.board_x, 0.3)

    def test_mestre_tira_o_post_it_do_quadro(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.mestre)

        self.client.post(reverse('delete_sticky_note', args=[recado.pk]))

        self.assertEqual(self.campanha.notes.count(), 0)

    def test_jogador_nao_tira_o_post_it(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.jogador)

        resposta = self.client.post(reverse('delete_sticky_note', args=[recado.pk]))

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.campanha.notes.count(), 1)

    def test_get_e_recusado(self):
        recado = StickyNote.objects.create(campaign=self.campanha)
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('update_sticky_note', args=[recado.pk]))

        self.assertEqual(resposta.status_code, 405)

    def test_o_post_it_aparece_no_quadro_do_mestre(self):
        StickyNote.objects.create(campaign=self.campanha, text='O ladrao mentiu')
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertContains(resposta, 'O ladrao mentiu')

    def test_o_jogador_nao_recebe_os_post_its(self):
        StickyNote.objects.create(campaign=self.campanha, text='O ladrao mentiu')
        self.client.force_login(self.jogador)

        resposta = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertNotContains(resposta, 'O ladrao mentiu')


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class SemRecarregarTests(TestCase):
    """Criar e apagar devolvem o pedaco novo, nao a pagina inteira."""

    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.client.force_login(self.mestre)

    def _criar(self, dados):
        return self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]), dados, **self.AJAX
        )

    def test_personagem_volta_como_card_pronto(self):
        resposta = self._criar({
            'form_type': 'character',
            'character-name': 'Kai',
            'character-inventory_capacity': '16',
            'character-assigned_to': str(self.jogador.pk),
        })

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados['ok'])
        self.assertIn('Kai', dados['html'])
        self.assertIn('character-card', dados['html'])

    def test_item_volta_como_card_pronto(self):
        resposta = self._criar({'form_type': 'item', 'item-name': 'Adaga'})

        self.assertIn('Adaga', resposta.json()['html'])

    def test_npc_volta_como_card_pronto(self):
        resposta = self._criar({
            'form_type': 'npc', 'npc-name': 'Vulto', 'npc-inventory_capacity': '16',
        })

        self.assertIn('Vulto', resposta.json()['html'])

    def test_inimigo_volta_como_card_pronto(self):
        resposta = self._criar({'form_type': 'enemy', 'enemy-name': 'Cerbero'})

        self.assertIn('Cerbero', resposta.json()['html'])

    def test_post_it_volta_como_peca_pronta(self):
        resposta = self.client.post(
            reverse('create_sticky_note', args=[self.campanha.pk]), **self.AJAX
        )

        dados = resposta.json()
        self.assertTrue(dados['ok'])
        self.assertIn('post-it', dados['html'])

    def test_polaroid_volta_como_peca_pronta(self):
        resposta = self._criar({'form_type': 'polaroid', 'polaroid-caption': 'O mapa'})

        self.assertIn('O mapa', resposta.json()['html'])

    def test_barra_volta_como_linha_pronta(self):
        inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )

        resposta = self.client.post(
            reverse('add_enemy_bar', args=[inimigo.pk]),
            {'name': 'Vida', 'max_value': '30'},
            **self.AJAX,
        )

        dados = resposta.json()
        self.assertIn('Vida', dados['html'])
        self.assertIn('30', dados['html'])

    def test_form_invalido_responde_o_erro_em_vez_da_pagina(self):
        """Campo em branco e o caso comum, e recarregar para dizer isso e o que
        estamos tirando."""
        resposta = self._criar({'form_type': 'item', 'item-name': ''})

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(resposta.json()['ok'])
        self.assertTrue(resposta.json()['erro'])

    def test_apagar_responde_ok_em_vez_de_redirecionar(self):
        item = Item.objects.create(name='Adaga', campaign=self.campanha)

        resposta = self.client.post(
            reverse('delete_item', args=[item.pk]), **self.AJAX
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()['ok'])
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())

    def test_sem_o_cabecalho_o_caminho_antigo_continua(self):
        """Sem JavaScript o mesmo endpoint tem que redirecionar como antes."""
        resposta = self._criar_sem_ajax()

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(self.campanha.items.filter(name='Adaga').exists())

    def _criar_sem_ajax(self):
        return self.client.post(
            reverse('campaign_detail', args=[self.campanha.pk]),
            {'form_type': 'item', 'item-name': 'Adaga'},
        )

    def test_o_card_da_grade_e_o_mesmo_que_volta_na_criacao(self):
        """Duas copias do mesmo layout divergem na primeira mudanca."""
        resposta_criacao = self._criar({'form_type': 'item', 'item-name': 'Adaga'})
        html_novo = resposta_criacao.json()['html']

        pagina = self.client.get(reverse('campaign_detail', args=[self.campanha.pk]))

        self.assertContains(pagina, 'data-card="item"')
        self.assertIn('data-card="item"', html_novo)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class LinhasDaFichaTests(TestCase):
    """Pericia, habilidade e atributo agora tambem se reescrevem e se apagam."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.pericia = CharacterSkill.objects.create(
            character=self.personagem, name='Furtividade', value='+4'
        )
        self.atributo = CharacterAttribute.objects.create(
            character=self.personagem, name='Forca', value='12'
        )
        self.habilidade = CharacterAbility.objects.create(
            character=self.personagem, name='Golpe duplo'
        )

    def test_mestre_reescreve_pericia(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk]),
            {'name': 'Acrobacia', 'value': '+6'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.pericia.refresh_from_db()
        self.assertEqual(self.pericia.name, 'Acrobacia')
        self.assertEqual(self.pericia.value, '+6')

    def test_mestre_reescreve_atributo(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_sheet_line', args=['character-attribute', self.atributo.pk]),
            {'name': 'Destreza', 'value': '15'},
        )

        self.atributo.refresh_from_db()
        self.assertEqual(self.atributo.name, 'Destreza')
        self.assertEqual(self.atributo.value, '15')

    def test_mestre_reescreve_habilidade(self):
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_sheet_line', args=['character-ability', self.habilidade.pk]),
            {'name': 'Golpe triplo'},
        )

        self.habilidade.refresh_from_db()
        self.assertEqual(self.habilidade.name, 'Golpe triplo')

    def test_nome_vazio_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk]),
            {'name': '   ', 'value': '+6'},
        )

        self.assertEqual(resposta.status_code, 400)
        self.pericia.refresh_from_db()
        self.assertEqual(self.pericia.name, 'Furtividade')

    def test_pericia_aceita_valor_em_branco_e_atributo_nao(self):
        """O modelo e quem sabe: o value da pericia e blank=True, o do atributo nao."""
        self.client.force_login(self.mestre)

        ok = self.client.post(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk]),
            {'name': 'Furtividade', 'value': ''},
        )
        recusado = self.client.post(
            reverse('update_sheet_line', args=['character-attribute', self.atributo.pk]),
            {'name': 'Forca', 'value': ''},
        )

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(recusado.status_code, 400)

    def test_jogador_dono_da_ficha_nao_reescreve(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk]),
            {'name': 'Invadida', 'value': '+9'},
        )

        self.assertEqual(resposta.status_code, 403)
        self.pericia.refresh_from_db()
        self.assertEqual(self.pericia.name, 'Furtividade')

    def test_mestre_de_outra_mesa_nao_reescreve(self):
        outro = make_user('outro')
        self.client.force_login(outro)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk]),
            {'name': 'Invadida'},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_mestre_apaga_cada_uma(self):
        self.client.force_login(self.mestre)

        for tipo, obj in (
            ('character-skill', self.pericia),
            ('character-attribute', self.atributo),
            ('character-ability', self.habilidade),
        ):
            self.client.post(reverse('delete_sheet_line', args=[tipo, obj.pk]))

        self.assertEqual(self.personagem.skills.count(), 0)
        self.assertEqual(self.personagem.attributes.count(), 0)
        self.assertEqual(self.personagem.abilities.count(), 0)

    def test_jogador_nao_apaga(self):
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('delete_sheet_line', args=['character-skill', self.pericia.pk])
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.personagem.skills.count(), 1)

    def test_tipo_desconhecido_e_403(self):
        """Tipo fora da tabela nao vira consulta nenhuma."""
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-inventario', 1]),
            {'name': 'x'},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('update_sheet_line', args=['character-skill', self.pericia.pk])
        )

        self.assertEqual(resposta.status_code, 405)

    def test_linha_de_npc_e_de_inimigo_seguem_a_mesma_rota(self):
        npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha
        )
        inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )
        pericia_npc = NPCSkill.objects.create(npc=npc, name='Rastrear')
        atributo_inimigo = EnemyAttribute.objects.create(
            enemy=inimigo, name='Furia', value='8'
        )
        self.client.force_login(self.mestre)

        self.client.post(
            reverse('update_sheet_line', args=['npc-skill', pericia_npc.pk]),
            {'name': 'Farejar', 'value': '+2'},
        )
        self.client.post(
            reverse('delete_sheet_line', args=['enemy-attribute', atributo_inimigo.pk])
        )

        pericia_npc.refresh_from_db()
        self.assertEqual(pericia_npc.name, 'Farejar')
        self.assertEqual(inimigo.attributes.count(), 0)

    def test_a_ficha_traz_o_lapis_para_o_mestre_e_nao_para_o_jogador(self):
        self.client.force_login(self.mestre)
        do_mestre = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        )

        self.client.force_login(self.jogador)
        do_jogador = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        )

        self.assertContains(do_mestre, 'id="alternar-edicao"')
        self.assertNotContains(do_jogador, 'id="alternar-edicao"')


class ImagemQueEncolheTests(TestCase):
    """A resolucao se resolve encolhendo, nao recusando — e sem achatar o alfa."""

    def _png(self, largura, altura, com_alfa=True):
        imagem = Image.new(
            'RGBA' if com_alfa else 'RGB',
            (largura, altura),
            (10, 20, 30, 0) if com_alfa else (10, 20, 30),
        )
        memoria = BytesIO()
        imagem.save(memoria, format='PNG')
        return SimpleUploadedFile('arte.png', memoria.getvalue(), content_type='image/png')

    def _abrir(self, arquivo):
        arquivo.seek(0)
        return Image.open(BytesIO(arquivo.read()))

    def test_imagem_grande_encolhe_ate_o_teto(self):
        grande = self._png(4000, 2000)

        menor = encolher_imagem(grande, 1600)

        self.assertIsNotNone(menor)
        self.assertEqual(max(self._abrir(menor).size), 1600)

    def test_imagem_que_ja_cabia_nao_e_reescrita(self):
        """Sem reescrever, o arquivo original chega intacto do outro lado."""
        pequena = self._png(300, 400)

        self.assertIsNone(encolher_imagem(pequena, 1600))

    def test_fundo_transparente_continua_transparente(self):
        """Converter para RGB encheria de preto todo desenho recortado."""
        recortada = self._png(3000, 3000, com_alfa=True)

        menor = encolher_imagem(recortada, 800)

        aberta = self._abrir(menor)
        self.assertEqual(aberta.format, 'PNG')
        self.assertIn('A', aberta.getbands())
        self.assertEqual(aberta.getpixel((0, 0))[3], 0)

    def test_gif_nao_e_mexido(self):
        """Um resize ingenuo reabriria so o primeiro quadro e mataria a animacao."""
        gif = SimpleUploadedFile('bicho.gif', RetratoDaFichaTests.GIF, content_type='image/gif')

        self.assertIsNone(encolher_imagem(gif, 8))

    def test_o_formulario_encolhe_no_caminho(self):
        mestre = make_user('mestre')
        jogador = make_user('jogador')
        campanha = Campaign.objects.create(name='Ossos', master=mestre)
        campanha.players.add(jogador)
        personagem = Character.objects.create(
            name='Kai', created_by=mestre, campaign=campanha, assigned_to=jogador
        )

        form = CharacterForm(
            {
                'character-name': 'Kai',
                'character-inventory_capacity': '16',
                'character-assigned_to': str(jogador.pk),
            },
            {'character-image': self._png(3000, 3000)},
            instance=personagem,
            prefix='character',
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(max(self._abrir(form.cleaned_data['image']).size), 1600)


@SEM_REDIRECT_HTTPS
class HabilidadeComCamposTests(TestCase):
    """Dano e campo proprio; o resto e uma lista de pares na ordem da pessoa."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.habilidade = CharacterAbility.objects.create(
            character=self.personagem, name='Golpe duplo'
        )
        self.client.force_login(self.mestre)

    def _salvar(self, **extra):
        return self.client.post(
            reverse('update_sheet_line', args=['character-ability', self.habilidade.pk]),
            {'name': 'Golpe duplo', **extra},
        )

    def test_dano_e_guardado(self):
        self._salvar(damage='2d6+3')

        self.habilidade.refresh_from_db()
        self.assertEqual(self.habilidade.damage, '2d6+3')

    def test_campos_extras_guardam_a_ordem(self):
        self._salvar(
            damage='2d6',
            extras=json.dumps([['alcance', '9m'], ['custo', '2 PM']]),
        )

        self.habilidade.refresh_from_db()
        self.assertEqual(
            self.habilidade.extras, [['alcance', '9m'], ['custo', '2 PM']]
        )

    def test_par_torto_e_descartado_em_vez_de_derrubar(self):
        self._salvar(extras=json.dumps([['ok', '1'], 'lixo', ['', 'sem rotulo'], [1, 2]]))

        self.habilidade.refresh_from_db()
        self.assertEqual(self.habilidade.extras, [['ok', '1'], ['1', '2']])

    def test_ha_um_teto_de_campos(self):
        muitos = [[f'c{i}', str(i)] for i in range(40)]
        self._salvar(extras=json.dumps(muitos))

        self.habilidade.refresh_from_db()
        self.assertEqual(
            len(self.habilidade.extras), CharacterAbility.LIMITE_DE_CAMPOS
        )

    def test_json_quebrado_e_400(self):
        resposta = self._salvar(extras='{isso nao e json')

        self.assertEqual(resposta.status_code, 400)

    def test_a_resposta_devolve_o_que_ficou(self):
        dados = self._salvar(damage='1d8', extras=json.dumps([['tipo', 'fogo']])).json()

        self.assertEqual(dados['damage'], '1d8')
        self.assertEqual(dados['extras'], [['tipo', 'fogo']])


@SEM_REDIRECT_HTTPS
class OrdemDosAtributosTests(TestCase):
    """Vai a lista inteira na ordem em que ficou, e nao 'essa subiu uma'."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.a = CharacterAttribute.objects.create(
            character=self.personagem, name='Forca', value='1', order=0
        )
        self.b = CharacterAttribute.objects.create(
            character=self.personagem, name='Destreza', value='2', order=1
        )
        self.c = CharacterAttribute.objects.create(
            character=self.personagem, name='Vigor', value='3', order=2
        )

    def _reordenar(self, ids):
        return self.client.post(
            reverse('reorder_sheet_lines', args=['character-attribute']),
            {'ids': json.dumps(ids)},
        )

    def test_mestre_reordena(self):
        self.client.force_login(self.mestre)

        resposta = self._reordenar([self.c.pk, self.a.pk, self.b.pk])

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            list(self.personagem.attributes.values_list('name', flat=True)),
            ['Vigor', 'Forca', 'Destreza'],
        )

    def test_jogador_nao_reordena(self):
        self.client.force_login(self.jogador)

        resposta = self._reordenar([self.c.pk, self.a.pk, self.b.pk])

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(
            list(self.personagem.attributes.values_list('name', flat=True)),
            ['Forca', 'Destreza', 'Vigor'],
        )

    def test_id_de_outra_mesa_derruba_a_reordenacao_inteira(self):
        """Nada e gravado pela metade: ou a ordem toda vale, ou nenhuma."""
        outro = make_user('outro')
        outra = Campaign.objects.create(name='Cinzas', master=outro)
        alheio = Character.objects.create(
            name='Nix', created_by=outro, campaign=outra, assigned_to=outro
        )
        de_fora = CharacterAttribute.objects.create(
            character=alheio, name='Sorte', value='9'
        )
        self.client.force_login(self.mestre)

        resposta = self._reordenar([self.c.pk, de_fora.pk])

        self.assertEqual(resposta.status_code, 403)
        self.c.refresh_from_db()
        self.assertEqual(self.c.order, 2)

    def test_ordem_invalida_e_400(self):
        self.client.force_login(self.mestre)

        resposta = self.client.post(
            reverse('reorder_sheet_lines', args=['character-attribute']),
            {'ids': 'nao e json'},
        )

        self.assertEqual(resposta.status_code, 400)

    def test_get_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('reorder_sheet_lines', args=['character-attribute'])
        )

        self.assertEqual(resposta.status_code, 405)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class EstruturaDasColunasTests(TestCase):
    """As colunas da ficha tem que ser irmas, e nao uma dentro da outra.

    Duas vezes uma edicao de template deixou a coluna do meio sem fechar, e as
    outras viraram filhas dela: sumia a terceira coluna e o inventario deixava
    de atravessar a pagina. O erro nao aparece em nenhum outro teste — a pagina
    responde 200 igual, so sai torta.
    """

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha
        )
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )

    def _profundidade(self, html):
        """Maior aninhamento de <section> na pagina."""
        fundo = 0
        maior = 0
        for pedaco in re.finditer(r'</?section\b', html):
            if pedaco.group(0).startswith('</'):
                fundo -= 1
            else:
                fundo += 1
                maior = max(maior, fundo)
        return maior, fundo

    def _conferir(self, url):
        self.client.force_login(self.mestre)
        html = self.client.get(url).content.decode()

        maior, sobrou = self._profundidade(html)
        self.assertEqual(sobrou, 0, 'sobrou <section> sem fechar')
        self.assertEqual(maior, 1, 'uma coluna ficou dentro da outra')
        return html

    def test_ficha_do_personagem_tem_as_tres_colunas_irmas(self):
        html = self._conferir(reverse('character_detail', args=[self.personagem.pk]))

        self.assertIn('coluna-pericias', html)
        self.assertIn('coluna-ficha', html)
        self.assertIn('coluna-atributos', html)
        self.assertIn('largura-total', html)

    def test_ficha_do_npc_tem_as_tres_colunas_irmas(self):
        html = self._conferir(reverse('npc_detail', args=[self.npc.pk]))

        self.assertIn('coluna-atributos', html)
        self.assertIn('largura-total', html)

    def test_ficha_do_inimigo_tem_as_tres_colunas_irmas(self):
        """O inimigo nao tem inventario, entao aqui sao tres colunas e so."""
        html = self._conferir(reverse('enemy_detail', args=[self.inimigo.pk]))

        self.assertIn('coluna-atributos', html)

    def test_a_ficha_do_jogador_tambem_fecha_certo(self):
        """O aviso de modo leitura entra antes das colunas e ja bagunçou o grid."""
        self.client.force_login(self.jogador)
        html = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        ).content.decode()

        maior, sobrou = self._profundidade(html)
        self.assertEqual(sobrou, 0)
        self.assertEqual(maior, 1)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class DoisEnquadramentosTests(TestCase):
    """Ficha e menu sao dois cortes da mesma imagem, e um nao encosta no outro."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.client.force_login(self.mestre)

    def _enquadrar(self, **extra):
        return self.client.post(
            reverse('update_character_framing', args=[self.personagem.pk]),
            {'zoom': '250', 'focus_x': '0.2', 'focus_y': '0.8', **extra},
        )

    def test_sem_alvo_mexe_no_da_ficha(self):
        self._enquadrar()

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.image_zoom, 250)
        self.assertEqual(self.personagem.card_zoom, 100)

    def test_alvo_menu_mexe_so_no_do_card(self):
        self._enquadrar(alvo='menu')

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.card_zoom, 250)
        self.assertAlmostEqual(self.personagem.card_focus_x, 0.2)
        self.assertEqual(self.personagem.image_zoom, 100)
        self.assertAlmostEqual(self.personagem.image_focus_x, 0.5)

    def test_um_nao_apaga_o_outro(self):
        self._enquadrar(alvo='menu')
        self._enquadrar(zoom='140', focus_x='0.9', focus_y='0.1')

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.card_zoom, 250)
        self.assertAlmostEqual(self.personagem.card_focus_x, 0.2)
        self.assertEqual(self.personagem.image_zoom, 140)
        self.assertAlmostEqual(self.personagem.image_focus_x, 0.9)

    def test_alvo_desconhecido_cai_no_da_ficha(self):
        self._enquadrar(alvo='inventado')

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.image_zoom, 250)
        self.assertEqual(self.personagem.card_zoom, 100)

    def test_o_corte_do_menu_tambem_e_aparado(self):
        self._enquadrar(alvo='menu', zoom='9000', focus_x='-2', focus_y='7')

        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.card_zoom, 400)
        self.assertAlmostEqual(self.personagem.card_focus_x, 0.0)
        self.assertAlmostEqual(self.personagem.card_focus_y, 1.0)

    def test_jogador_nao_enquadra_o_menu(self):
        self.client.force_login(self.jogador)

        resposta = self._enquadrar(alvo='menu')

        self.assertEqual(resposta.status_code, 403)
        self.personagem.refresh_from_db()
        self.assertEqual(self.personagem.card_zoom, 100)

    def test_o_card_da_lista_usa_o_corte_do_menu(self):
        self.personagem.card_zoom = 320
        self.personagem.save()

        html = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        ).content.decode()

        self.assertIn('data-zoom="320"', html)

    def test_o_seletor_so_aparece_quando_ha_imagem(self):
        """Sem foto nao ha o que enquadrar, nem na ficha nem no menu."""
        sem_foto = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        ).content.decode()

        # So o nome do arquivo: o template nao abre a imagem, so monta a URL.
        self.personagem.image = 'characters/kai.png'
        self.personagem.save()
        com_foto = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        ).content.decode()

        self.assertNotIn('data-portrait-alvos', sem_foto)
        self.assertIn('data-portrait-alvos', com_foto)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class DescricaoDoSlotTests(TestCase):
    """A descricao viaja com o item, senao o slot fica mudo ate recarregar."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.item = Item.objects.create(
            name='Adaga', campaign=self.campanha, description='Corta e envenena.'
        )
        self.slot = self.personagem.slots.first()
        self.client.force_login(self.mestre)

    def test_a_resposta_do_slot_traz_a_descricao(self):
        dados = self.client.post(
            reverse('assign_slot', args=[self.personagem.pk, self.slot.pk]),
            {'item_id': self.item.pk},
        ).json()

        self.assertEqual(dados['itemDescription'], 'Corta e envenena.')

    def test_esvaziar_o_slot_limpa_a_descricao(self):
        self.slot.item = self.item
        self.slot.save()

        dados = self.client.post(
            reverse('assign_slot', args=[self.personagem.pk, self.slot.pk])
        ).json()

        self.assertEqual(dados['itemDescription'], '')

    def test_item_sem_descricao_devolve_vazio_em_vez_de_none(self):
        """None viraria a string 'None' no dataset do slot."""
        mudo = Item.objects.create(name='Pedra', campaign=self.campanha)

        dados = self.client.post(
            reverse('assign_slot', args=[self.personagem.pk, self.slot.pk]),
            {'item_id': mudo.pk},
        ).json()

        self.assertEqual(dados['itemDescription'], '')

    def test_o_slot_ja_nasce_com_a_descricao_no_html(self):
        self.slot.item = self.item
        self.slot.save()

        html = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        ).content.decode()

        self.assertIn('data-item-description="Corta e envenena."', html)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class FichaEhDoDonoTests(TestCase):
    """Ficha alheia e do dono e do mestre, e de mais ninguem.

    Estar na campanha abria a ficha de todo mundo: nome, vida, pericias e
    inventario dos outros jogadores.
    """

    def setUp(self):
        self.mestre = make_user('mestre')
        self.dono = make_user('dono')
        self.outro = make_user('outro')
        self.estranho = make_user('estranho')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.mestre, self.dono, self.outro)
        self.ficha = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.dono,
        )

    def _abrir(self, sufixo=''):
        return self.client.get(
            reverse('character_detail', args=[self.ficha.pk]) + sufixo
        )

    def test_o_dono_abre_a_propria_ficha(self):
        self.client.force_login(self.dono)

        resposta = self._abrir()

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['is_master'])

    def test_outro_jogador_da_mesma_campanha_leva_403(self):
        self.client.force_login(self.outro)

        self.assertEqual(self._abrir().status_code, 403)

    def test_quem_nem_e_da_campanha_leva_403(self):
        self.client.force_login(self.estranho)

        self.assertEqual(self._abrir().status_code, 403)

    def test_o_mestre_abre_qualquer_ficha(self):
        self.client.force_login(self.mestre)

        resposta = self._abrir()

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['is_master'])

    def test_o_mestre_espia_em_modo_leitura(self):
        """E assim que ele confere como a ficha chega para a mesa."""
        self.client.force_login(self.mestre)

        resposta = self._abrir('?mode=player')

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context['is_master'])

    def test_mode_player_nao_abre_porta_para_outro_jogador(self):
        """O sufixo nao pode virar a chave que faltava."""
        self.client.force_login(self.outro)

        self.assertEqual(self._abrir('?mode=player').status_code, 403)

    def test_a_barra_do_topo_do_jogador_tem_so_a_ficha_aberta(self):
        """Nem a ficha alheia, nem outra ficha dele: de personagem para
        personagem se passa pela campanha."""
        Character.objects.create(
            name='Alheia', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.outro,
        )
        Character.objects.create(
            name='Segunda', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.dono,
        )
        self.client.force_login(self.dono)

        resposta = self._abrir()

        nomes = [c.name for c in resposta.context['campaign_characters']]
        self.assertEqual(nomes, ['Kai'])

    def test_o_mestre_em_modo_leitura_ve_a_barra_do_jogador(self):
        """E para isso que o modo leitura serve: conferir o que a mesa ve."""
        Character.objects.create(
            name='Alheia', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.outro,
        )
        self.client.force_login(self.mestre)

        resposta = self._abrir('?mode=player')

        nomes = [c.name for c in resposta.context['campaign_characters']]
        self.assertEqual(nomes, ['Kai'])

    def test_o_mestre_ve_todas_na_barra_do_topo(self):
        Character.objects.create(
            name='Alheia', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.outro,
        )
        self.client.force_login(self.mestre)

        nomes = [c.name for c in self._abrir().context['campaign_characters']]

        self.assertIn('Kai', nomes)
        self.assertIn('Alheia', nomes)

    def test_a_lista_da_campanha_nao_oferece_o_botao_de_ficha_alheia(self):
        """Um botao que leva a 403 e pior do que botao nenhum."""
        self.client.force_login(self.outro)

        html = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        ).content.decode()

        self.assertNotIn(f"/characters/{self.ficha.pk}/?mode=player", html)

    def test_o_npc_vinculado_a_ficha_do_jogador_continua_abrindo(self):
        npc = NPC.objects.create(
            name='Vulto', created_by=self.mestre, campaign=self.campanha,
            assigned_to_character=self.ficha, visible=True,
        )
        self.client.force_login(self.dono)

        resposta = self.client.get(reverse('npc_detail', args=[npc.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_o_npc_do_personagem_alheio_nao_abre(self):
        alheia = Character.objects.create(
            name='Alheia', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.outro,
        )
        npc = NPC.objects.create(
            name='Sombra', created_by=self.mestre, campaign=self.campanha,
            assigned_to_character=alheia, visible=True,
        )
        self.client.force_login(self.dono)

        resposta = self.client.get(reverse('npc_detail', args=[npc.pk]))

        self.assertEqual(resposta.status_code, 403)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class FichaEscondidaTests(TestCase):
    """Escondida e escondida: some da lista e nao abre nem pela URL.

    Sem isto o `visible` era cortina e nao tranca — o personagem sumia da
    campanha e continuava abrindo para o dono pelo endereco direto.
    """

    def setUp(self):
        self.mestre = make_user('mestre')
        self.dono = make_user('dono')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.mestre, self.dono)
        self.ficha = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.dono, visible=False,
        )

    def test_o_dono_nao_abre_a_ficha_escondida(self):
        self.client.force_login(self.dono)

        resposta = self.client.get(
            reverse('character_detail', args=[self.ficha.pk])
        )

        self.assertEqual(resposta.status_code, 403)

    def test_revelar_devolve_a_ficha_ao_dono(self):
        self.ficha.visible = True
        self.ficha.save()
        self.client.force_login(self.dono)

        resposta = self.client.get(
            reverse('character_detail', args=[self.ficha.pk])
        )

        self.assertEqual(resposta.status_code, 200)

    def test_o_mestre_abre_a_escondida(self):
        """Quem escondeu precisa continuar entrando para preparar a ficha."""
        self.client.force_login(self.mestre)

        resposta = self.client.get(
            reverse('character_detail', args=[self.ficha.pk])
        )

        self.assertEqual(resposta.status_code, 200)

    def test_a_escondida_nao_aparece_na_lista_da_campanha(self):
        self.client.force_login(self.dono)

        resposta = self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        )

        self.assertNotIn('Kai', [c.name for c in resposta.context['characters']])


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class AtaquesTests(TestCase):
    """Ataque tem a forma da habilidade: nome, dano, descricao e campos livres."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha
        )
        self.client.force_login(self.mestre)

    def test_mestre_cria_ataque_na_ficha(self):
        self.client.post(
            reverse('character_detail', args=[self.personagem.pk]),
            {'form_type': 'attack', 'attack-name': 'Espada longa',
             'attack-damage': '1d8+2', 'attack-description': 'Corpo a corpo.',
             'attack-order': 0},
        )

        ataque = self.personagem.attacks.get()
        self.assertEqual(ataque.name, 'Espada longa')
        self.assertEqual(ataque.damage, '1d8+2')
        self.assertEqual(ataque.description, 'Corpo a corpo.')

    def test_a_ordem_segue_a_criacao(self):
        for nome in ('Soco', 'Chute', 'Cabecada'):
            self.client.post(
                reverse('character_detail', args=[self.personagem.pk]),
                {'form_type': 'attack', 'attack-name': nome, 'attack-order': 0},
            )

        self.assertEqual(
            list(self.personagem.attacks.values_list('name', flat=True)),
            ['Soco', 'Chute', 'Cabecada'],
        )

    def test_jogador_nao_cria_ataque(self):
        self.client.force_login(self.jogador)

        self.client.post(
            reverse('character_detail', args=[self.personagem.pk]),
            {'form_type': 'attack', 'attack-name': 'Roubado', 'attack-order': 0},
        )

        self.assertEqual(self.personagem.attacks.count(), 0)

    def test_o_ataque_se_reescreve_pela_mesma_rota_das_outras_linhas(self):
        ataque = CharacterAttack.objects.create(
            character=self.personagem, name='Soco', damage='1d4'
        )

        self.client.post(
            reverse('update_sheet_line', args=['character-attack', ataque.pk]),
            {'name': 'Soco giratorio', 'damage': '2d4',
             'extras': json.dumps([['alcance', 'corpo a corpo']])},
        )

        ataque.refresh_from_db()
        self.assertEqual(ataque.name, 'Soco giratorio')
        self.assertEqual(ataque.damage, '2d4')
        self.assertEqual(ataque.extras, [['alcance', 'corpo a corpo']])

    def test_o_ataque_se_apaga(self):
        ataque = CharacterAttack.objects.create(character=self.personagem, name='Soco')

        self.client.post(
            reverse('delete_sheet_line', args=['character-attack', ataque.pk])
        )

        self.assertEqual(self.personagem.attacks.count(), 0)

    def test_jogador_nao_reescreve_o_ataque(self):
        ataque = CharacterAttack.objects.create(character=self.personagem, name='Soco')
        self.client.force_login(self.jogador)

        resposta = self.client.post(
            reverse('update_sheet_line', args=['character-attack', ataque.pk]),
            {'name': 'Roubado'},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_o_inimigo_tambem_tem_ataques(self):
        self.client.post(
            reverse('enemy_detail', args=[self.inimigo.pk]),
            {'form_type': 'attack', 'attack-name': 'Mordida',
             'attack-damage': '2d6', 'attack-order': 0},
        )

        self.assertEqual(self.inimigo.attacks.get().damage, '2d6')

    def test_o_ataque_aparece_na_ficha(self):
        CharacterAttack.objects.create(
            character=self.personagem, name='Espada longa', damage='1d8+2'
        )

        html = self.client.get(
            reverse('character_detail', args=[self.personagem.pk])
        ).content.decode()

        self.assertIn('Espada longa', html)
        self.assertIn('1d8+2', html)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class BarrasEmTodoLugarTests(TestCase):
    """A mesma vida na ficha e no quadro, e so para quem pode ver aquela ficha.

    O valor mora no banco e cada pagina pergunta pelo que ela mesma mostra: e
    isso que faz o mestre tirar cinco no quadro e o jogador ver doze na ficha
    sem apertar F5.
    """

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.outro = make_user('outro')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador, self.outro)
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador,
        )
        self.barra = CharacterBar.objects.create(
            character=self.personagem, name='Vida', current=17, max_value=17
        )
        self.inimigo = Enemy.objects.create(
            name='Cerbero', created_by=self.mestre, campaign=self.campanha, visible=True
        )
        self.barra_do_inimigo = EnemyBar.objects.create(
            enemy=self.inimigo, name='Vida', current=30, max_value=30
        )

    def _estado(self, escopo, pk):
        return self.client.get(reverse('bar_state'), {'scope': escopo, 'pk': pk})

    def _mexer(self, quanto='5'):
        return self.client.post(
            reverse('modify_bar', args=[self.barra.pk]),
            {'action': 'decrease', 'amount': quanto},
        )

    def test_o_dono_le_o_valor_da_propria_ficha(self):
        self.client.force_login(self.jogador)

        dados = self._estado('character', self.personagem.pk).json()

        self.assertEqual(
            dados['bars'][f'character:{self.barra.pk}'],
            {'current': 17, 'max': 17},
        )

    def test_o_que_o_mestre_tira_o_jogador_le(self):
        self.client.force_login(self.mestre)
        self._mexer('5')

        self.client.force_login(self.jogador)
        dados = self._estado('character', self.personagem.pk).json()

        self.assertEqual(dados['bars'][f'character:{self.barra.pk}']['current'], 12)

    def test_o_que_o_jogador_gasta_o_mestre_le_no_quadro(self):
        self.client.force_login(self.jogador)
        self._mexer('3')

        self.client.force_login(self.mestre)
        dados = self._estado('campaign', self.campanha.pk).json()

        self.assertEqual(dados['bars'][f'character:{self.barra.pk}']['current'], 14)

    def test_o_quadro_traz_os_tres_tipos_de_peca(self):
        npc = NPC.objects.create(
            name='Velho', created_by=self.mestre, campaign=self.campanha, visible=True
        )
        barra_do_npc = NPCBar.objects.create(
            npc=npc, name='Animo', current=4, max_value=4
        )
        self.client.force_login(self.mestre)

        barras = self._estado('campaign', self.campanha.pk).json()['bars']

        self.assertIn(f'character:{self.barra.pk}', barras)
        self.assertIn(f'npc:{barra_do_npc.pk}', barras)
        self.assertIn(f'enemy:{self.barra_do_inimigo.pk}', barras)

    def test_a_chave_leva_o_tipo_junto(self):
        """No quadro convivem barras dos tres, e o id sozinho nao distingue."""
        self.client.force_login(self.mestre)

        barras = self._estado('campaign', self.campanha.pk).json()['bars']

        self.assertTrue(all(':' in chave for chave in barras))

    def test_ficha_alheia_nao_entrega_valor(self):
        self.client.force_login(self.outro)

        self.assertEqual(
            self._estado('character', self.personagem.pk).status_code, 403
        )

    def test_o_jogador_nao_le_o_quadro_do_mestre(self):
        self.client.force_login(self.jogador)

        self.assertEqual(self._estado('campaign', self.campanha.pk).status_code, 403)

    def test_o_jogador_nao_le_a_vida_do_inimigo(self):
        self.client.force_login(self.jogador)

        self.assertEqual(self._estado('enemy', self.inimigo.pk).status_code, 403)

    def test_ficha_escondida_nao_entrega_valor_nem_ao_dono(self):
        self.personagem.visible = False
        self.personagem.save()
        self.client.force_login(self.jogador)

        self.assertEqual(
            self._estado('character', self.personagem.pk).status_code, 403
        )

    def test_ficha_escondida_tambem_nao_deixa_o_dono_mexer(self):
        """A barra segue a ficha: se ela nao abre, a vida dela nao muda."""
        self.personagem.visible = False
        self.personagem.save()
        self.client.force_login(self.jogador)

        self._mexer('5')

        self.barra.refresh_from_db()
        self.assertEqual(self.barra.current, 17)

    def test_escopo_sem_pk_e_recusado(self):
        self.client.force_login(self.mestre)

        resposta = self.client.get(reverse('bar_state'), {'scope': 'character'})

        self.assertEqual(resposta.status_code, 400)


@SEM_REDIRECT_HTTPS
@SEM_MANIFESTO
class PecaDoQuadroTests(TestCase):
    """A peca mostra o que o card mostra, e as barras nascem recolhidas."""

    def setUp(self):
        self.mestre = make_user('mestre')
        self.jogador = make_user('jogador')
        self.campanha = Campaign.objects.create(name='Ossos', master=self.mestre)
        self.campanha.players.add(self.jogador)
        # O nome do arquivo basta: o template so precisa da .url, e assim o
        # teste nao escreve nada no MEDIA_ROOT.
        self.personagem = Character.objects.create(
            name='Kai', created_by=self.mestre, campaign=self.campanha,
            assigned_to=self.jogador, image='kai.gif',
        )
        CharacterBar.objects.create(
            character=self.personagem, name='Vida', current=17, max_value=17
        )
        self.client.force_login(self.mestre)

    def _quadro(self):
        return self.client.get(
            reverse('campaign_detail', args=[self.campanha.pk])
        ).content.decode()

    def test_a_peca_usa_o_corte_do_menu(self):
        """A peca e o card sao a mesma imagem no mesmo corte: dois de 220."""
        self.personagem.card_zoom = 220
        self.personagem.save()

        html = self._quadro()

        self.assertIn('peca-retrato', html)
        self.assertGreaterEqual(html.count('data-zoom="220"'), 2)

    def test_a_peca_nao_usa_o_corte_da_ficha(self):
        """O corte alto da ficha cortaria o retrato no peito dentro da peca."""
        self.personagem.image_zoom = 175
        self.personagem.save()

        self.assertNotIn('data-zoom="175"', self._quadro())

    def test_os_botoes_da_barra_nascem_recolhidos(self):
        """Tres barras abertas viram doze botoes e empurram o quadro da tela."""
        html = self._quadro()

        self.assertIsNotNone(
            re.search(r'class="peca-barra-botoes"\s+hidden', html)
        )

    def test_a_barra_da_peca_diz_de_que_tipo_e(self):
        self.assertIn('data-bar-kind="character"', self._quadro())

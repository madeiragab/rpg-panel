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

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from hud.forms import ProfileEditForm, RegistrationForm, ResetPasswordForm
from hud.models import (
    Campaign,
    Character,
    InventorySlot,
    Item,
    NPC,
    PasswordResetToken,
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

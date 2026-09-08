"""Entrar pelo nome de usuário ou pelo e-mail.

O `username` da conta é derivado no cadastro: sai do apelido, ou do pedaço do
e-mail antes do @ quando não há apelido, e ainda ganha um número no fim se
aquele nome já estava tomado. Quem se cadastrou como "gabriel" pode ter virado
"gabriel2" sem nunca ver isso na tela — e depois não entra, porque digita o
nome que acha que é o dele. O e-mail a pessoa sabe de cor.

Só o campo de entrada muda. Senha, conta desativada e permissões continuam
sendo problema do `ModelBackend`, que é de onde este herda.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsuarioOuEmailBackend(ModelBackend):
    """O mesmo login do Django, aceitando o e-mail no lugar do usuário."""

    def authenticate(self, request, username=None, password=None, **kwargs):  # type: ignore[override]
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        usuario = self._procurar(UserModel, username)
        if usuario is None:
            # Sem este hash jogado fora, quem não existe responde na hora e
            # quem existe demora o tempo de conferir a senha: dá para descobrir
            # que uma conta existe só olhando o relógio.
            UserModel().set_password(password)
            return None

        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    @staticmethod
    def _procurar(UserModel, identificador: str):
        """A conta desse nome de usuário, ou desse e-mail. Nenhuma das duas: None."""
        try:
            return UserModel._default_manager.get_by_natural_key(identificador)
        except UserModel.DoesNotExist:
            pass

        # O Django não exige e-mail único. Com duas contas no mesmo endereço
        # não há como saber de quem é a senha digitada, e escolher uma delas
        # deixaria a outra pessoa entrando na conta errada: nesse caso o
        # e-mail não serve, e a entrada continua pelo nome de usuário.
        achados = list(UserModel._default_manager.filter(email__iexact=identificador)[:2])
        return achados[0] if len(achados) == 1 else None

from io import BytesIO

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import (
    Campaign,
    Character,
    CharacterAbility,
    CharacterAttribute,
    CharacterSkill,
    Enemy,
    EnemyAbility,
    EnemySkill,
    Item,
    NPC,
    NPCAbility,
    NPCAttribute,
    NPCSkill,
    Polaroid,
    UserProfile,
)


class ForgotPasswordForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label="Nome de usuário",
        widget=forms.TextInput(attrs={"class": "hud-input", "placeholder": "Digite seu nome de usuário"})
    )


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label="Nova senha",
        widget=forms.PasswordInput(attrs={"class": "hud-input", "placeholder": "Nova senha"})
    )
    password_confirm = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={"class": "hud-input", "placeholder": "Confirme a senha"})
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm:
            if password != password_confirm:
                raise forms.ValidationError("As senhas não correspondem.")
        # Sem esta chamada os AUTH_PASSWORD_VALIDATORS do settings.py não valem
        # nada aqui: este form é um forms.Form escrito à mão, não o do Django.
        if password:
            validate_password(password)
        return cleaned_data
class UserSelectWithAvatarWidget(forms.Select):
    """Custom widget to display username in options."""
    def optgroups(self, name, value, attrs=None):
        # This is a simplified approach; for true avatar display in <option>, CSS won't work.
        # We'll just ensure username is the label.
        return super().optgroups(name, value, attrs)


# O navegador manda o content_type que quiser; quem diz o formato de verdade é
# o Pillow, que o forms.ImageField já roda para validar. Por isso a conferência
# olha image.format, e não o cabeçalho do upload.
FORMATOS_DE_RETRATO = {"JPEG", "PNG", "WEBP", "GIF", "AVIF"}
ACCEPT_DE_RETRATO = "image/jpeg,image/png,image/webp,image/gif,image/avif"

# Não há teto de bytes: o que interessa é a resolução, e ela é resolvida
# encolhendo em vez de recusando. Uma arte de 6000px não fica melhor numa
# moldura de 280 — só custa banda em toda página que mostra aquela ficha.
LADO_MAXIMO_DA_FICHA = 1600
LADO_MAXIMO_DO_ITEM = 640
LADO_MAXIMO_DO_AVATAR = 640

# Um GIF animado não sobrevive a um resize ingênuo: o Pillow reabriria só o
# primeiro quadro e a animação morreria no caminho. Ele passa como está.
FORMATOS_QUE_NAO_ENCOLHEM = {"GIF"}

# Formatos com perda aceitam qualidade; PNG ignora o parâmetro.
QUALIDADE = {"JPEG": 90, "WEBP": 90, "AVIF": 80}


def encolher_imagem(arquivo, lado_maximo: int):
    """Devolve a imagem reduzida, ou None se ela já cabia.

    O formato é o mesmo da entrada e o modo também: um PNG com fundo
    transparente sai PNG com fundo transparente. Converter para RGB aqui
    encheria de preto todo desenho recortado, que é justamente o tipo de
    imagem que mais chega numa ficha.
    """
    # O formato sai do proprio Pillow, e nao do `.image` que o forms.ImageField
    # pendura no arquivo depois de validar: assim a funcao serve sozinha, sem
    # depender de ter passado por um formulario antes.
    arquivo.seek(0)
    try:
        imagem = Image.open(arquivo)
    except OSError:
        return None
    formato = (imagem.format or "").upper()
    if not formato or formato in FORMATOS_QUE_NAO_ENCOLHEM:
        return None

    imagem = ImageOps.exif_transpose(imagem)  # foto de celular vem deitada
    if max(imagem.size) <= lado_maximo:
        return None

    imagem.thumbnail((lado_maximo, lado_maximo), Image.LANCZOS)
    memoria = BytesIO()
    extras = {}
    if formato in QUALIDADE:
        extras["quality"] = QUALIDADE[formato]
    imagem.save(memoria, format=formato, **extras)
    return ContentFile(memoria.getvalue(), name=arquivo.name)


def conferir_e_encolher(imagem, lado_maximo: int):
    """Recusa formato que não serve, e encolhe o que veio grande demais."""
    formato = getattr(getattr(imagem, "image", None), "format", None)
    # Sem upload novo o campo devolve o arquivo que já estava salvo, e esse
    # não tem .image — não há o que reconferir nem o que encolher.
    if formato is None:
        return imagem
    if formato.upper() not in FORMATOS_DE_RETRATO:
        raise forms.ValidationError("Escolha uma imagem JPG, PNG, WEBP, GIF ou AVIF.")
    return encolher_imagem(imagem, lado_maximo) or imagem


class RetratoMixin:
    """Regras da imagem de ficha, iguais para personagem e NPC."""

    LADO_MAXIMO = LADO_MAXIMO_DA_FICHA

    def clean_image(self):
        return conferir_e_encolher(self.cleaned_data.get("image"), self.LADO_MAXIMO)

    def save(self, commit=True):
        ficha = super().save(commit=False)
        if "image" in self.changed_data:
            ficha.reset_framing()
            # O corte era da imagem antiga nos dois lugares.
            if hasattr(ficha, "reset_card"):
                ficha.reset_card()
        if commit:
            ficha.save()
            self.save_m2m()
        return ficha


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "description", "banner"]
        labels = {
            "name": "Nome da Campanha",
            "description": "Descrição",
            "banner": "Banner da Campanha",
        }


class CharacterForm(RetratoMixin, forms.ModelForm):
    class Meta:
        model = Character
        fields = ["name", "image", "inventory_capacity", "assigned_to"]
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "hud-select"}),
            "image": forms.ClearableFileInput(attrs={"accept": ACCEPT_DE_RETRATO}),
        }
        labels = {
            "name": "Nome",
            "image": "Imagem (upload)",
            "inventory_capacity": "Capacidade de inventário",
            "assigned_to": "Atribuir ao jogador",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make assigned_to required
        self.fields["assigned_to"].required = True
        # Customize queryset to use username as display label
        if self.fields["assigned_to"].queryset.exists():
            self.fields["assigned_to"].label_from_instance = lambda obj: obj.username


class ItemForm(RetratoMixin, forms.ModelForm):
    LADO_MAXIMO = LADO_MAXIMO_DO_ITEM

    class Meta:
        model = Item
        fields = ["name", "image", "description"]
        labels = {"name": "Nome", "image": "Imagem (upload)", "description": "Descrição"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Detalhes, efeitos, usos..."}),
            "image": forms.ClearableFileInput(attrs={"accept": ACCEPT_DE_RETRATO}),
        }


class NPCForm(RetratoMixin, forms.ModelForm):
    class Meta:
        model = NPC
        fields = ["name", "image", "inventory_capacity", "assigned_to_character"]
        widgets = {
            "assigned_to_character": forms.Select(attrs={"class": "hud-select"}),
            "image": forms.ClearableFileInput(attrs={"accept": ACCEPT_DE_RETRATO}),
        }
        labels = {
            "name": "Nome do NPC",
            "image": "Imagem (upload)",
            "inventory_capacity": "Capacidade de inventário",
            "assigned_to_character": "Vinculado ao personagem",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make assigned_to_character optional
        self.fields["assigned_to_character"].required = False


class NPCSkillForm(forms.ModelForm):
    class Meta:
        model = NPCSkill
        fields = ["name", "value", "order"]
        labels = {"name": "Nome", "value": "Valor", "order": "Ordem"}


class NPCAbilityForm(forms.ModelForm):
    class Meta:
        model = NPCAbility
        fields = ["name", "damage", "description", "order"]
        labels = {
            "name": "Nome",
            "damage": "Dano",
            "description": "Descrição",
            "order": "Ordem",
        }
        widgets = {
            "damage": forms.TextInput(attrs={"placeholder": "Ex.: 2d6+3"}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "O que a habilidade faz"}),
            "order": forms.HiddenInput(),
        }


class CharacterAttributeForm(forms.ModelForm):
    class Meta:
        model = CharacterAttribute
        fields = ["name", "value", "order"]
        labels = {"name": "Nome", "value": "Valor", "order": "Ordem"}
        widgets = {
            "order": forms.HiddenInput(),
        }


class NPCAttributeForm(forms.ModelForm):
    class Meta:
        model = NPCAttribute
        fields = ["name", "value", "order"]
        labels = {"name": "Nome", "value": "Valor", "order": "Ordem"}
        widgets = {
            "order": forms.HiddenInput(),
        }


class RegistrationForm(forms.Form):
    nome = forms.CharField(label="Nome", max_length=120)
    sobrenome = forms.CharField(label="Sobrenome", max_length=120)
    apelido = forms.CharField(label="Apelido", max_length=60, required=False)
    imagem = forms.ImageField(label="Imagem", required=False)
    email = forms.EmailField(label="Email")
    senha = forms.CharField(label="Senha", widget=forms.PasswordInput)
    confirmacao = forms.CharField(label="Confirmação de senha", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get("senha")
        confirm = cleaned.get("confirmacao")
        if senha and confirm and senha != confirm:
            raise forms.ValidationError("As senhas não coincidem.")
        if senha:
            # O usuário ainda não existe; um User solto serve para o validador
            # de semelhança comparar a senha com nome, apelido e e-mail.
            candidato = User(
                username=(cleaned.get("apelido") or "").strip(),
                email=cleaned.get("email") or "",
                first_name=cleaned.get("nome") or "",
                last_name=cleaned.get("sobrenome") or "",
            )
            validate_password(senha, candidato)
        return cleaned

    def clean_imagem(self):
        return conferir_e_encolher(self.cleaned_data.get("imagem"), LADO_MAXIMO_DO_AVATAR)

    def save(self):
        cleaned = self.cleaned_data
        base_username = (cleaned.get("apelido") or cleaned["email"].split("@")[0]).strip()
        username = base_username or "usuario"
        i = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{i}"
            i += 1
        user = User.objects.create_user(username=username, email=cleaned["email"], password=cleaned["senha"]) 
        user.first_name = cleaned.get("nome") or ""
        user.last_name = cleaned.get("sobrenome") or ""
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        # Display name como "Nome Sobrenome"
        display_name = " ".join(filter(None, [cleaned.get("nome"), cleaned.get("sobrenome")]))
        profile.display_name = display_name
        profile.nickname = cleaned.get("apelido") or ""
        if cleaned.get("imagem"):
            profile.avatar = cleaned["imagem"]
        profile.save()
        return user


class ProfileEditForm(forms.Form):
    apelido = forms.CharField(label="Apelido", max_length=60, required=False)
    email = forms.EmailField(label="Email")
    imagem = forms.ImageField(label="Imagem", required=False)
    senha = forms.CharField(label="Nova senha", widget=forms.PasswordInput, required=False)
    confirmacao = forms.CharField(label="Confirmação", widget=forms.PasswordInput, required=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["apelido"].initial = getattr(self.user.profile, "nickname", "")
        self.fields["email"].initial = self.user.email

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get("senha")
        confirm = cleaned.get("confirmacao")
        if senha or confirm:
            if senha != confirm:
                raise forms.ValidationError("As senhas não coincidem.")
            validate_password(senha, self.user)
        return cleaned

    def clean_imagem(self):
        return conferir_e_encolher(self.cleaned_data.get("imagem"), LADO_MAXIMO_DO_AVATAR)

    def save(self):
        cleaned = self.cleaned_data
        self.user.email = cleaned.get("email")
        self.user.save()
        prof = self.user.profile
        prof.nickname = cleaned.get("apelido") or prof.nickname
        if cleaned.get("imagem"):
            prof.avatar = cleaned["imagem"]
        prof.save()
        if cleaned.get("senha"):
            self.user.set_password(cleaned["senha"])
            self.user.save()
        return self.user


class CharacterSkillForm(forms.ModelForm):
    class Meta:
        model = CharacterSkill
        fields = ["name", "value", "order"]
        labels = {"name": "Nome", "value": "Valor", "order": "Ordem"}


class CharacterAbilityForm(forms.ModelForm):
    class Meta:
        model = CharacterAbility
        fields = ["name", "damage", "description", "order"]
        labels = {
            "name": "Nome",
            "damage": "Dano",
            "description": "Descrição",
            "order": "Ordem",
        }
        widgets = {
            "damage": forms.TextInput(attrs={"placeholder": "Ex.: 2d6+3"}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "O que a habilidade faz"}),
            "order": forms.HiddenInput(),
        }


class EnemyForm(RetratoMixin, forms.ModelForm):
    class Meta:
        model = Enemy
        fields = ["name", "image"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": ACCEPT_DE_RETRATO}),
        }
        labels = {"name": "Nome do inimigo", "image": "Imagem (upload)"}


class EnemySkillForm(forms.ModelForm):
    class Meta:
        model = EnemySkill
        fields = ["name", "value", "order"]
        labels = {"name": "Nome", "value": "Valor", "order": "Ordem"}


class EnemyAbilityForm(forms.ModelForm):
    class Meta:
        model = EnemyAbility
        fields = ["name", "damage", "description", "order"]
        labels = {
            "name": "Nome",
            "damage": "Dano",
            "description": "Descrição",
            "order": "Ordem",
        }
        widgets = {
            "damage": forms.TextInput(attrs={"placeholder": "Ex.: 2d6+3"}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "O que a habilidade faz"}),
            "order": forms.HiddenInput(),
        }


class PolaroidForm(RetratoMixin, forms.ModelForm):
    LADO_MAXIMO = LADO_MAXIMO_DA_FICHA

    class Meta:
        model = Polaroid
        fields = ["image", "caption"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": ACCEPT_DE_RETRATO}),
            "caption": forms.TextInput(attrs={"placeholder": "Ex.: o mapa que o ladrão largou"}),
        }
        labels = {"image": "Foto", "caption": "Legenda"}

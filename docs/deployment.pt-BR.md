> 🇧🇷 **Português** · 🇬🇧 [English](deployment.md)

# Deploy

O painel roda em qualquer lugar capaz de servir uma aplicação WSGI. Atualmente está implantado no PythonAnywhere (`galibinja.pythonanywhere.com`), e o `Procfile` também atende plataformas que o leem (Railway, Render, similares ao Heroku).

## Variáveis de ambiente

| Variável | Obrigatória | Propósito |
|---|---|---|
| `DJANGO_SECRET_KEY` | **Sim em produção** | Chave secreta do Django. A aplicação se recusa a subir sem ela quando o `DEBUG` está desligado. |
| `DEBUG` | Não | `True` liga o modo de depuração e um fallback de chave secreta exclusivo para desenvolvimento. Padrão: `False`. |
| `EMAIL_HOST_USER` | Para redefinição de senha | Conta Gmail usada para enviar os e-mails de redefinição. |
| `EMAIL_HOST_PASSWORD` | Para redefinição de senha | **Senha de app** do Gmail (não a senha da conta). |

Gere uma chave secreta com:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **Nota de segurança:** a chave secreta já esteve escrita diretamente em `settings.py` e, portanto, está presente no histórico git deste repositório. Qualquer deploy precisa usar uma chave **recém-gerada** via `DJANGO_SECRET_KEY` — nunca a antiga. Rotacionar a chave invalida as sessões existentes e os tokens de redefinição de senha, que é justamente o resultado desejado aqui.

## Hosts permitidos

`ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` estão escritos diretamente em `rpg_panel/settings.py`. Adicione seu domínio lá antes de implantar em um host novo, caso contrário o Django rejeita todas as requisições com um 400.

## Passos do deploy

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn rpg_panel.wsgi:application
```

O `Procfile` encadeia os dois últimos comandos, então plataformas que o leem não precisam de configuração adicional.

## Arquivos estáticos e de mídia

- **Estáticos** (`/static/`) — coletados em `staticfiles/` e servidos pelo **WhiteNoise** com nomes comprimidos e com hash. O `collectstatic` é obrigatório a cada deploy; pulá-lo quebra todo o CSS/JS, porque o storage por manifesto se recusa a servir nomes sem hash.
- **Mídia** (`/media/`) — uploads dos usuários (avatares, banners, imagens de personagens e itens) são gravados em `media/` no disco local.

> ⚠️ **Sistemas de arquivos efêmeros:** em plataformas que zeram o disco entre deploys (Railway, camadas gratuitas do Render, Heroku), as imagens enviadas se perdem a cada redeploy. Para uma configuração permanente, aponte a mídia para um object storage (S3 ou similar) via `django-storages`, ou use um host com volume persistente.

## Banco de dados

Tanto o desenvolvimento quanto o deploy atual usam **SQLite** (`db.sqlite3`, fora do versionamento). Para uma produção multiusuário, troque `DATABASES` para PostgreSQL e rode as migrações novamente — nenhuma mudança de modelo é necessária.

## Ramificações de migração

O histórico de migrações contém ramos paralelos vindos de trabalho simultâneo em funcionalidades (duas migrações `0007_*`, `0008_*`, `0009_*` e `0010_*`). O Django as resolve pelas dependências declaradas, então o `migrate` roda sem problemas. Se você adicionar uma migração e o Django reclamar de múltiplos nós folha, faça a fusão com:

```bash
python manage.py makemigrations --merge
```

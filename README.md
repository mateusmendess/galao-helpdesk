# Help Desk Equipe

Help Desk Equipe (nome técnico `galao-helpdesk`): controle de quem é a vez de trocar o galão de água do time de Help Desk.

## Como rodar localmente (Windows, PowerShell)

```powershell
# 1. Ambiente virtual e dependências
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 2. Variáveis de ambiente: copie o exemplo e troque a SECRET_KEY
Copy-Item .env.example .env

# 3. Banco local (SQLite)
python manage.py migrate
```

### Tailwind (CSS)

Baixe o executável standalone do Tailwind (sem Node) para a pasta `tools/`
(ela fica fora do git):

```powershell
New-Item -ItemType Directory -Force tools
Invoke-WebRequest https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-windows-x64.exe -OutFile tools\tailwindcss.exe
```

Gerar o CSS uma vez:

```powershell
.\tools\tailwindcss.exe -i static_src\input.css -o static\css\output.css --minify
```

### Dois terminais no dia a dia

```powershell
# Terminal 1: servidor em http://127.0.0.1:8000
python manage.py runserver

# Terminal 2: regera o CSS a cada mudança nos templates
.\tools\tailwindcss.exe -i static_src\input.css -o static\css\output.css --minify --watch
```

O `static/css/output.css` vai para o git: depois de mudar o visual, faça commit dele.

### Primeiro uso do login

```powershell
python manage.py migrate
python manage.py createsuperuser          # seu admin: e-mail e senha digitados por você
python manage.py criar_equipe_de_teste    # Pessoa 1 a 7, sem senha (só com DEBUG=True)
python manage.py changepassword pessoa1@exemplo.test   # define a senha de uma conta de teste
python manage.py runserver
```

Abra http://127.0.0.1:8000 e entre com o e-mail (ou a matrícula) e a senha. Contas novas de verdade
são cadastradas só pelo admin, em http://127.0.0.1:8000/admin/.

Limite de tentativas: 5 senhas erradas para a mesma pessoa em 15 minutos, somando as
feitas pelo e-mail e pela matrícula, bloqueiam essa pessoa automaticamente (em /entrar/
e no /admin/), e o bloqueio acaba sozinho.
Os valores ficam em `config/settings.py` (`LOGIN_MAX_TENTATIVAS` e `LOGIN_JANELA_MINUTOS`).

Senhas: cada pessoa troca a própria senha em "Trocar senha", na tela inicial.
O admin cria a senha provisória no /admin/; usuário novo vem marcado para trocar no primeiro acesso.
Ao redefinir a senha de outra pessoa no /admin/, a marca "precisa trocar a senha no próximo acesso" liga sozinha (a pessoa troca no próximo acesso).

Fila: a tela inicial mostra a rodada, de quem é a vez e a fila de 1 a 7.
A `ordem` de cada usuário (no /admin/) define a posição na fila; quem não tem ordem fica fora.
Qualquer pessoa logada registra a troca pelo botão "Troquei o galão" na tela inicial (inclusive cobertura).
O histórico completo fica em "Ver histórico" (/trocas/); a marca "devendo N" vem desse histórico.
O admin ainda pode lançar trocas em /admin/ (Fila › Trocas).
No /admin/, o admin corrige o executor e a observação de uma troca; o "devendo" se acerta sozinho.
Apagar só vale para uma troca da rodada atual, ou da última rodada fechada enquanto a atual estiver vazia (essa rodada é reaberta).
Ausências: no /admin/ (Fila › Ausências), o admin cadastra a pessoa, o início e o fim (fim em branco = sem data de volta).
Quem está ausente hoje é pulado na fila e aparece como "ausente até DD/MM" na tela inicial.

### Testes e ruff

```powershell
pytest
ruff check .
ruff format --check .
```

## Produção (Railway)

Build, pré-deploy, start e healthcheck ficam configurados no painel do Railway
(não há `railway.json` nem `Procfile`):

| Etapa | Valor |
|---|---|
| Build | `python manage.py collectstatic --noinput` |
| Pré-deploy | `python manage.py migrate --noinput` |
| Start | `gunicorn config.wsgi --bind 0.0.0.0:$PORT` |
| Healthcheck | `/saude/` (timeout de 300 s) |

O Python vem do `.python-version` (3.13). Variáveis de ambiente (sem valores aqui):

- `SECRET_KEY`: chave longa e aleatória, só de produção
- `DEBUG=False`
- `HTTPS_SEGURO=True` (redireciona para https, cookies seguros e HSTS)
- `ALLOWED_HOSTS`: domínio do site **e** `healthcheck.railway.app`, separados por vírgula
  (ex.: `meu-app.up.railway.app,healthcheck.railway.app`)
- `CSRF_TRUSTED_ORIGINS`: endereço com https (ex.: `https://meu-app.up.railway.app`)
- `DATABASE_URL`: URL do PostgreSQL do Railway

O `criar_equipe_de_teste` não roda em produção (recusa com `DEBUG=False`).

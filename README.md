# galao-helpdesk

Controle de quem é a vez de trocar o galão de água do time de Help Desk.

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

### Testes e ruff

```powershell
pytest
ruff check .
ruff format --check .
```

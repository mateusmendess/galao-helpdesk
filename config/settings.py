"""
Configuracoes do projeto galao-helpdesk.

Tudo que muda entre ambientes (computador do Mateus, CI, producao) vem de
variaveis de ambiente: SECRET_KEY, DEBUG, ALLOWED_HOSTS e DATABASE_URL.
Localmente elas ficam no arquivo .env (fora do git; veja .env.example).
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Le o .env se ele existir; no CI e em producao as variaveis vem do ambiente.
environ.Env.read_env(BASE_DIR / ".env")

# Sem valor padrao: se faltar, o Django para com erro em vez de usar chave fraca.
SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Origens https aceitas no CSRF (ex.: https://meu-app.up.railway.app).
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Producao atras do proxy HTTPS do Railway. False no computador e no CI:
# nesse caso nada abaixo e alterado.
HTTPS_SEGURO = env.bool("HTTPS_SEGURO", default=False)
if HTTPS_SEGURO:
    # O proxy termina o HTTPS e avisa pelo cabecalho X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # O healthcheck do Railway chega por http: a rota de saude nao redireciona.
    SECURE_REDIRECT_EXEMPT = [r"^saude/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # 1 hora de proposito; aumentar so com o site estavel.
    SECURE_HSTS_SECONDS = 3600


# Aplicacoes

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "usuarios",
    "fila",
    "escala",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "usuarios.middleware.TrocaDeSenhaObrigatoriaMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Banco de dados: somente via DATABASE_URL
# (SQLite no computador do Mateus, PostgreSQL no CI e em producao).

DATABASES = {
    "default": env.db("DATABASE_URL"),
}


# Usuario proprio: login por e-mail (veja usuarios/models.py)

AUTH_USER_MODEL = "usuarios.Usuario"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Limite de tentativas de login: com LOGIN_MAX_TENTATIVAS senhas erradas para o
# mesmo e-mail nos ultimos LOGIN_JANELA_MINUTOS minutos, o e-mail fica bloqueado.
AUTHENTICATION_BACKENDS = ["usuarios.backends.LimiteTentativasBackend"]
LOGIN_MAX_TENTATIVAS = 5
LOGIN_JANELA_MINUTOS = 15

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Idioma e fuso

LANGUAGE_CODE = "pt-br"

TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True

USE_TZ = True


# Arquivos estaticos (CSS gerado pelo Tailwind em static/css/output.css)

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    # Armazenamento simples do WhiteNoise: comprime, mas sem "manifest"
    # (o manifest exige collectstatic antes dos testes).
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# E-mail

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}

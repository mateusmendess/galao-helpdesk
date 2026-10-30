import re

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

MATRICULA_VALIDA = re.compile(r"^[0-9]+$")


class UsuarioManager(BaseUserManager):
    """Cria usuarios pelo e-mail (nao existe nome de usuario)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        # Admin do sistema = is_staff e is_superuser ligados.
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Admin precisa de is_staff=True e is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        # Usado no login: o e-mail digitado vale com qualquer maiuscula/minuscula.
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": email})

    def por_identificador(self, identificador):
        # Login: so digitos = matricula (texto exato); senao, e-mail como hoje.
        identificador = (identificador or "").strip()
        if MATRICULA_VALIDA.fullmatch(identificador):
            return self.get(matricula=identificador)
        return self.get_by_natural_key(identificador)


class Usuario(AbstractUser):
    username = None
    email = models.EmailField("e-mail", unique=True)
    # Texto (nao numero): "0123" e "123" sao matriculas diferentes.
    # Vazia vira None, para duas pessoas sem matricula nao baterem no unique.
    matricula = models.CharField(
        "matrícula",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(MATRICULA_VALIDA, "A matrícula deve ter só números.")
        ],
        help_text="Só números. Pode ficar em branco por enquanto.",
    )
    # Posicao na fila (1, 2, 3...). Vazia para quem nao esta na fila.
    ordem = models.PositiveIntegerField(
        "ordem",
        unique=True,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    # Posicao no rodizio dos sabados; a fila do galao continua em `ordem`.
    ordem_escala = models.PositiveIntegerField(
        "posição na escala de sábado",
        unique=True,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=(
            "Posição no rodízio dos sábados. "
            "Deixe em branco se a pessoa não entra na escala."
        ),
    )
    # Ligada pelo admin ao criar a conta com senha provisoria; so a tela
    # "Trocar senha" desliga.
    precisa_trocar_senha = models.BooleanField(
        "precisa trocar a senha no próximo acesso", default=False
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    def _normalizar_matricula(self):
        self.matricula = (self.matricula or "").strip() or None

    def clean_fields(self, exclude=None):
        # Os validadores rodam aqui, antes do clean(): tira os espacos antes.
        self._normalizar_matricula()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()
        self._normalizar_matricula()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        self._normalizar_matricula()
        super().save(*args, **kwargs)


class FalhaLogin(models.Model):
    """Uma senha errada para um e-mail (o e-mail pode nem existir)."""

    # Sem chave estrangeira: conta tambem e-mails que nao sao de ninguem.
    email = models.CharField("e-mail", max_length=254, db_index=True)
    criada_em = models.DateTimeField("criada em", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "falha de login"
        verbose_name_plural = "falhas de login"

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator
from django.db import models


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


class Usuario(AbstractUser):
    username = None
    email = models.EmailField("e-mail", unique=True)
    # Posicao na fila (1, 2, 3...). Vazia para quem nao esta na fila.
    ordem = models.PositiveIntegerField(
        "ordem",
        unique=True,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.lower()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    # Vazio de proposito: criado desde o modulo 1 porque trocar o modelo de
    # usuario depois do banco migrado e muito dificil. O modulo 2 acrescenta
    # os campos (ex.: ordem na fila).
    pass

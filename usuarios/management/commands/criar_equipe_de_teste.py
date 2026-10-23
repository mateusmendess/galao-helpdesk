from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usuarios.models import Usuario

TAMANHO_DA_EQUIPE = 7


class Command(BaseCommand):
    help = (
        "Cria a equipe de teste (Pessoa 1 a Pessoa 7, pessoaN@exemplo.test, "
        "ordem 1 a 7) sem senha. So roda com DEBUG ligado."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Recusado: DEBUG esta desligado. Este comando cria contas "
                "ficticias e so pode rodar no computador de desenvolvimento."
            )

        criadas = 0
        with transaction.atomic():
            for n in range(1, TAMANHO_DA_EQUIPE + 1):
                email = f"pessoa{n}@exemplo.test"
                if Usuario.objects.filter(email=email).exists():
                    continue
                if Usuario.objects.filter(ordem=n).exists():
                    raise CommandError(
                        f"A ordem {n} ja pertence a outra conta; nada foi criado."
                    )
                usuario = Usuario(email=email, first_name=f"Pessoa {n}", ordem=n)
                # Sem senha: quem for usar a conta define com changepassword.
                usuario.set_unusable_password()
                usuario.save()
                criadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{criadas} pessoa(s) criada(s); "
                f"{TAMANHO_DA_EQUIPE - criadas} ja existia(m)."
            )
        )

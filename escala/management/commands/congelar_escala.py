from django.core.management.base import BaseCommand

from escala.calculo import congelar_passados


class Command(BaseCommand):
    help = (
        "Grava (congela) os sábados da escala que já passaram e ainda não "
        "foram gravados."
    )

    def handle(self, *args, **options):
        gravados = congelar_passados()
        self.stdout.write(f"Sábados congelados: {gravados}")

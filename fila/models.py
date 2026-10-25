from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Value
from django.utils import timezone


class Rodada(models.Model):
    """Uma volta completa na fila: cada pessoa presente troca uma vez."""

    numero = models.PositiveIntegerField(
        "número", unique=True, validators=[MinValueValidator(1)]
    )
    aberta_em = models.DateTimeField("aberta em", default=timezone.now)
    # Vazia = rodada atual.
    fechada_em = models.DateTimeField("fechada em", null=True, blank=True)

    class Meta:
        verbose_name = "rodada"
        verbose_name_plural = "rodadas"
        ordering = ["-numero"]
        constraints = [
            # Indice unico sobre uma constante, so nas linhas abertas: o banco
            # recusa uma segunda rodada aberta (SQLite e PostgreSQL).
            models.UniqueConstraint(
                Value(1),
                condition=Q(fechada_em__isnull=True),
                name="uma_rodada_aberta",
            ),
        ]

    def __str__(self):
        return f"Rodada {self.numero}"


class Troca(models.Model):
    """Uma troca do galao: de quem era a vez (titular) e quem trocou (executor)."""

    rodada = models.ForeignKey(
        Rodada, on_delete=models.PROTECT, related_name="trocas", verbose_name="rodada"
    )
    titular = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trocas_como_titular",
        verbose_name="titular (de quem era a vez)",
    )
    executor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trocas_como_executor",
        verbose_name="executor (quem trocou)",
    )
    data_hora = models.DateTimeField("data e hora", default=timezone.now)
    observacao = models.TextField("observação", blank=True)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trocas_registradas",
        verbose_name="registrada por",
    )

    class Meta:
        verbose_name = "troca"
        verbose_name_plural = "trocas"
        ordering = ["-data_hora"]
        constraints = [
            models.UniqueConstraint(
                fields=["rodada", "titular"], name="um_titular_por_rodada"
            ),
        ]

    def __str__(self):
        from .regras import nome_de_exibicao

        return f"{self.rodada}: {nome_de_exibicao(self.titular)}"

    def clean(self):
        from .regras import rodada_atual

        super().clean()
        erros = {}
        if self.titular_id:
            titular = self.titular
            if not titular.is_active:
                erros["titular"] = "O titular está inativo."
            elif titular.ordem is None:
                erros["titular"] = "O titular não está na fila (sem ordem)."
            else:
                # No admin a rodada ainda nao foi preenchida aqui.
                rodada = self.rodada if self.rodada_id else rodada_atual()
                repetida = Troca.objects.filter(rodada=rodada, titular=titular)
                if repetida.exclude(pk=self.pk).exists():
                    erros["titular"] = "O titular já tem troca nesta rodada."
        if self.executor_id and not self.executor.is_active:
            erros["executor"] = "O executor está inativo."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        from .regras import fechar_rodada_se_completa

        # Grava a troca e, se ela completou a rodada, fecha e abre a proxima,
        # tudo junto. O fechamento so mexe em Rodada: nao chama Troca.save().
        with transaction.atomic():
            super().save(*args, **kwargs)
            fechar_rodada_se_completa(self.rodada)

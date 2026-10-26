from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q, Value
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
        if not self._state.adding:
            # Troca ja gravada: o titular nao muda e nao e revalidado; o
            # executor e conferido pela lista do formulario do admin.
            return
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
        # Corrigir uma troca ja gravada nao fecha nem abre rodada.
        criando = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if criando:
                fechar_rodada_se_completa(self.rodada)


FIM_ANTES_DO_INICIO = "O fim não pode ser antes do início."


class Ausencia(models.Model):
    """Periodo (inclusivo) em que a pessoa sai da fila; fim vazio = em aberto."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ausencias",
        verbose_name="pessoa",
    )
    inicio = models.DateField("início")
    fim = models.DateField(
        "fim",
        null=True,
        blank=True,
        help_text=(
            "Deixe em branco se não souber quando a pessoa volta. "
            "O fim não pode ser antes do início."
        ),
    )

    class Meta:
        verbose_name = "ausência"
        verbose_name_plural = "ausências"
        ordering = ["-inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__isnull=True) | Q(fim__gte=F("inicio")),
                name="ausencia_fim_nao_antes_do_inicio",
                violation_error_message=FIM_ANTES_DO_INICIO,
            ),
        ]

    def __str__(self):
        from .regras import nome_de_exibicao

        periodo = f"{self.inicio:%d/%m/%Y} " + (
            f"a {self.fim:%d/%m/%Y}" if self.fim else "em diante (em aberto)"
        )
        return f"{nome_de_exibicao(self.usuario)}: {periodo}"

    def clean(self):
        super().clean()
        if self.inicio and self.fim and self.fim < self.inicio:
            raise ValidationError({"fim": FIM_ANTES_DO_INICIO})
        if not (self.usuario_id and self.inicio):
            return
        # Sobrepoe se inicio_A <= fim_B e inicio_B <= fim_A (vazio = infinito).
        # Nao enxerga dois admins salvando ao mesmo tempo (uso raro, so admins).
        outras = Ausencia.objects.filter(usuario_id=self.usuario_id).exclude(pk=self.pk)
        outras = outras.filter(Q(fim__isnull=True) | Q(fim__gte=self.inicio))
        if self.fim:
            outras = outras.filter(inicio__lte=self.fim)
        existente = outras.order_by("inicio").first()
        if existente is None:
            return
        if existente.fim is None:
            raise ValidationError(
                "Esta pessoa já tem uma ausência neste período "
                f"({existente.inicio:%d/%m} em diante, em aberto). Preencha o fim "
                "da ausência anterior antes de cadastrar outra."
            )
        raise ValidationError(
            "Esta pessoa já tem uma ausência neste período "
            f"({existente.inicio:%d/%m} a {existente.fim:%d/%m}). Ajuste a "
            "ausência existente em vez de criar outra."
        )

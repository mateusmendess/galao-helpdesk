import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copiar_pulados(apps, schema_editor):
    """Copia as ligacoes do M2M antigo para o PuladoNoSabado (antes de
    remover o campo antigo)."""
    SabadoFechado = apps.get_model("escala", "SabadoFechado")
    PuladoNoSabado = apps.get_model("escala", "PuladoNoSabado")
    Antiga = SabadoFechado.pulados.through
    PuladoNoSabado.objects.bulk_create(
        PuladoNoSabado(fechado_id=ligacao.sabadofechado_id, usuario_id=ligacao.usuario_id)
        for ligacao in Antiga.objects.all()
    )


def devolver_pulados(apps, schema_editor):
    """Volta: copia do PuladoNoSabado para o M2M antigo (ja recriado)."""
    SabadoFechado = apps.get_model("escala", "SabadoFechado")
    PuladoNoSabado = apps.get_model("escala", "PuladoNoSabado")
    Antiga = SabadoFechado.pulados.through
    Antiga.objects.bulk_create(
        Antiga(sabadofechado_id=p.fechado_id, usuario_id=p.usuario_id)
        for p in PuladoNoSabado.objects.all()
    )


class Migration(migrations.Migration):
    # O Django nao troca um M2M simples por um com `through`: cria o modelo
    # novo, copia os dados, remove o campo antigo e cria o novo campo.

    dependencies = [
        ("escala", "0002_sabado_fechado"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PuladoNoSabado",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "fechado",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="escala.sabadofechado",
                        verbose_name="sábado",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="pessoa",
                    ),
                ),
            ],
            options={
                "verbose_name": "pulado no sábado",
                "verbose_name_plural": "pulados no sábado",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("fechado", "usuario"),
                        name="pulado_uma_vez_por_sabado",
                    )
                ],
            },
        ),
        migrations.RunPython(copiar_pulados, devolver_pulados),
        migrations.RemoveField(model_name="sabadofechado", name="pulados"),
        migrations.AddField(
            model_name="sabadofechado",
            name="pulados",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                through="escala.PuladoNoSabado",
                to=settings.AUTH_USER_MODEL,
                verbose_name="pulados por ausência",
            ),
        ),
    ]

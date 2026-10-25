# Controle da Troca do Galão — Estrutura do Projeto

**Nome técnico (pasta, repositório no GitHub e projeto no Railway):** `galao-helpdesk`

Sistema web simples para o time do Help Desk (7 pessoas) controlar de quem é a vez de trocar o galão de água. Hoje isso é feito numa planilha Excel; o sistema substitui a planilha e passa a guardar o histórico completo.

---

## 1. Stack (fechada)

| Camada | Escolha | Para que serve |
|---|---|---|
| Framework | Django | Login, usuários, permissões e painel admin já vêm prontos |
| Banco | PostgreSQL (Railway) | Guarda pessoas, trocas e ausências |
| Front | Templates Django (HTML) + Tailwind CSS (CLI standalone) | O Django monta a página; o Tailwind é o CSS, gerado num arquivo `output.css` |
| Login | `django.contrib.auth` com usuário próprio (custom user) | Um login por pessoa; cadastro só pelo admin |
| Servidor | Gunicorn + WhiteNoise | Gunicorn roda o Django em produção; WhiteNoise entrega o CSS |
| Qualidade | pytest-django + ruff | Testes e verificação de estilo do código |
| CI/CD | GitHub Actions (CI desde o módulo 1) + Railway | CI: lint + testes em cada push e PR. Deploy: sai da `main`, só com o CI verde |

---

## 2. Regras de negócio

- Fila fixa de 1 a 7. A troca acontece **por evento** (quando o galão acaba), não em dia fixo.
- **Rodada:** cada pessoa tem uma vez por rodada. Quando todos os **presentes** tiverem trocado, a rodada fecha e outra começa.
- **Ausência:** quem está ausente é pulado e o próximo presente troca. O ausente não deve nada e não precisa ter trocado para a rodada fechar; ao voltar, volta à fila na posição fixa dele (`ordem`), sem prioridade e sem dívida.
- **De quem é a vez:** a menor ordem que ainda não trocou na rodada atual, pulando quem estiver ausente.
- **Cobertura:** se A troca no lugar de B, o histórico registra "A no lugar de B", a vez de B conta como cumprida e B passa a dever 1 troca.
- **Dívida ("devendo"):** não é digitada; é calculada a partir do histórico (ver seção 4).
- **Histórico completo:** cada troca vira um registro. Nada se perde quando a rodada vira.
- **Acesso:** login individual. Admins: o Mateus e mais uma pessoa do time. Só admins cadastram pessoas, registram ausências e corrigem registros. Os demais consultam e marcam a própria troca.
- **Sem notificação** por enquanto.

---

## 3. Modelos (tabelas)

### Usuario (usuário próprio do Django)
- Login por **e-mail** (único, sempre em minúsculas); não existe nome de usuário
- Campos do Django (nome, senha, `is_active`, `is_staff`, `is_superuser`)
- `ordem`: posição na fila (começa em 1), única; pode ficar vazia para quem não está na fila
- Admin do sistema = `is_staff` e `is_superuser` ligados; membro = os dois desligados; `is_active` = ainda faz parte do time

### Rodada
- `numero` (1, 2, 3...; único), `aberta_em`, `fechada_em` (vazio = rodada atual)
- Só pode existir uma rodada aberta por vez

### Troca
- `rodada`: em qual rodada aconteceu
- `titular`: de quem era a vez
- `executor`: quem realmente trocou (igual ao titular quando não há cobertura)
- `data_hora`, `observacao`
- `registrada_por`: quem lançou no sistema
- Regra: um titular só pode ter **uma** troca por rodada

### Ausencia
- `usuario`, `inicio`, `fim`, `motivo` (férias, falta, outro)
- `criada_por` (um admin)

---

## 4. Como o "devendo" é calculado

Para cada pessoa X, olhando todo o histórico:

```
saldo(X) = (vezes em que X foi coberto por outro)
         − (vezes em que X cobriu outro)
```

- Saldo positivo: X deve trocas.
- Saldo negativo: X tem trocas a receber.
- Quando X cobre a vez de quem o cobriu antes, as duas pontas se anulam.

Vantagem: se um registro for corrigido, o saldo se acerta sozinho. Não existe número digitado à mão para ficar errado.

---

## 5. Lógica da vez (resumo)

1. Pega a rodada aberta (se não houver, abre a primeira).
2. Candidatos = usuários ativos, com ordem, sem troca nesta rodada, em ordem crescente.
3. Remove quem está ausente na data de hoje (é pulado e não deve nada).
4. O primeiro que sobrar é a vez; se não sobrar ninguém, não há vez.
5. Quando todos os presentes (ativos com ordem, menos os ausentes) tiverem troca, a rodada fecha e outra abre. Quem estava ausente volta na posição fixa dele, sem prioridade.

---

## 6. Módulos (uma branch + um Pull Request por módulo)

| # | Módulo | O que entrega |
|---|---|---|
| 1 | Base, CI e deploy | **Parte A (local):** projeto Django, `Usuario` próprio ainda vazio (evita uma migração difícil depois), SQLite local, Gunicorn + WhiteNoise, Tailwind CLI, `CLAUDE.md`, ruff + 1 teste e **CI no GitHub Actions (lint + testes)**. **Parte B (quando o Railway voltar):** deploy da página "olá" |
| 2 | Usuários e login | Login por e-mail (sem nome de usuário), campo `ordem`, login/logout, cadastro só pelo admin, permissão admin × membro, tela inicial protegida, comando que cria a equipe de teste |
| 3 | Fila e "de quem é a vez" | Rodada, regra da vez, tela com "Vez de: fulano". Testes pesados aqui |
| 4 | Registrar troca e histórico | Botão "troquei o galão", cobertura, lista de histórico, saldo de dívida |
| 5 | Ausências | Cadastro de férias/faltas (só admin) e integração com a fila |
| 6 | Acabamento | Telas finais e revisão geral |

Antes de cada tela nova, mostro uma prévia visual para você aprovar.

---

## 7. Quem faz o quê

- **Mateus (dono do projeto):** decide, aprova as prévias visuais, leva cada pedido ao Claude Code e cada relatório de volta ao analista, e diz "faz o merge".
- **Claude (analista, este chat):** investiga, escreve um pedido em `.txt` por módulo (com a lista "LEIA ANTES DE EDITAR"), explica o porquê das decisões, confere o relatório e o `.diff` do PR e diz se pode mesclar. Não programa o projeto.
- **Claude Code (programador):** lê o código, programa, testa, abre o Pull Request e só mescla depois do "faz o merge". Segue o `CLAUDE.md` na raiz do repositório (o prompt `prompt-claude-code-como-trabalhar.txt`).

**Fluxo de cada módulo:** analista escreve o pedido → Mateus cola no Claude Code → Claude Code programa e abre o PR → Mateus leva o relatório ao analista → analista confere e libera → Mateus diz "faz o merge".

**Combinados:** passo a passo com confirmação ("1,1"), conceito explicado junto com o código, prévia visual antes de cada tela nova e documentação completa só quando você pedir.

---

## 8. Pontos a confirmar

- **Dívida ("devendo"):** a leitura da planilha atual (um colega com 1 troca devida e uma troca fora da ordem) foi entendida como cobertura. Vale confirmar com o time.
- **Ausência:** decidida em 25/10/2026: o ausente é pulado, não deve nada e volta na posição fixa (ver seção 2).
- **Privacidade:** como o repositório é público, nomes reais do time não entram no repositório (código, testes, docs). Os dados reais ficam só no banco de produção.

COMO TRABALHAMOS NESTE PROJETO (instrucoes permanentes para o Claude Code)

QUEM E QUEM
- Mateus: dono do projeto, estudante de Sistemas de Informacao. Responda sempre em portugues do Brasil, em linguagem simples. Explique em uma frase qualquer termo tecnico novo.
- Claude (conversa separada, o "analista"): investiga, escreve os pedidos para voce em arquivos .txt numerados na pasta pedidos/ (o task.md, na raiz, aponta para o pedido atual), le o seu RELATORIO.md, confere o diff do PR e o CI no GitHub e diz se pode mesclar. O Mateus nao cola nada: ele so diz "leia o task.md e execute".
- Voce (Claude Code): le o codigo, programa, testa, abre o PR e, so depois do "faz o merge", mescla. Voce e quem tem acesso ao repositorio.

REGRAS DE OURO
1. Leia antes de editar. Cada pedido traz uma lista "LEIA ANTES DE EDITAR": confirme linhas e nomes (podem ter mudado). Se o problema descrito NAO existir ou for diferente, REPORTE e NAO invente correcao. Nos relatorios passados o problema real foi diferente do descrito mais de uma vez; isso e bem-vindo.
2. Corrija o minimo. Nada de redesenhar, renomear ou refatorar alem do pedido. Nada de dependencia nova nem variavel de ambiente nova sem o pedido mandar.
3. Nunca imprima nem grave segredos (senhas, chaves, tokens). Nao peca senhas ao Mateus. Em verificacao local, use banco temporario e credenciais geradas por voce que NAO sao impressas.
4. Nao acesse producao nem o painel da hospedagem (nem para ler variaveis). Quem confere producao e o analista, so em leitura.
5. Nunca esconda falha. Se um teste revelar bug fora do pedido, deixe-o como xfail(strict=True) com motivo claro OU reporte e pergunte; nao corrija no meio e nao mascare.
6. Se algo for ambiguo e caro de refazer, pergunte antes. Se for barato, escolha o mais simples e seguro e diga qual escolheu.
7. O repositorio e PUBLICO. Nunca escreva nomes reais de colegas, e-mails, telefones ou outros dados pessoais em codigo, testes, fixtures, documentos ou mensagens de commit/PR; use nomes ficticios (ex.: "Pessoa 1").

GIT, CI E PULL REQUEST (projeto solo com pipeline)
- Mesmo trabalhando sozinho, usamos branch por assunto e Pull Request. O deploy (CD) do Railway sai da `main`: tudo que entra na `main` vai para producao. Por isso a `main` so recebe codigo com o CI verde.
- Uma tarefa = um assunto = uma branch curta com nome claro (ex.: feat/login, fix/limpeza-antiga), criada a partir da `main` atualizada. Nao misture assuntos. Nunca trabalhe nem de push direto na `main`.
- Voce faz os commits na branch (mensagens claras, em portugues), da push da branch e abre UM Pull Request para a `main`. O CI (GitHub Actions: lint + testes) roda no push e no PR.
- NAO faca o merge sozinho. Abra o PR, confirme que o check do CI passou e que o PR esta limpo, escreva o RELATORIO.md, mostre o link do PR e ESPERE. O fluxo e: voce reporta (RELATORIO.md) -> o Mateus diz "feito" ao analista, que le o RELATORIO.md, confere o diff do PR e o CI no GitHub e diz se pode mesclar -> o Mateus diz "faz o merge do PR #N" -> so entao voce mescla.
- Se o CI falhar, investigue a causa (ex.: diferenca entre Windows e Linux, versao do Python) e corrija na mesma branch; nunca ignore nem desligue um teste para passar.
- Quando o Mateus disser "faz o merge do PR #N", isso JA implica, sem ele repetir: confirmar que o CI do PR esta verde e que o PR continua no mesmo commit; merge commit normal (SEM squash; ex.: `gh pr merge N --merge --delete-branch`); atualizar a `main` local (`git checkout main` e `git pull`), confirmar que `main` local e remota estao no mesmo commit, apagar a branch do assunto (local e remota) e deixar o working tree limpo; NAO fazer deploy manual (o Railway sobe sozinho e so depois que o CI do commit passar); ao final, passar o link do CI da `main` para o analista conferir. Se o merge for recusado, NAO force: avise o Mateus.
- Se algo quebrar em producao, a volta e um `git revert` do commit/PR do assunto (um assunto por PR torna isso simples). Nao use reset --hard nem push --force sem o Mateus pedir.
- Antes de reportar, rode `git status` e `git diff --stat` e liste os arquivos alterados e criados, com uma linha de justificativa para cada um. Cuidado com fim de linha (CRLF x LF): nao reescreva arquivos inteiros trocando o fim de linha; o diff deve mostrar so as mudancas reais.
- Commits e descricao do PR terminam com as linhas de atribuicao que o sistema indicar.

TESTES (politica para economizar tempo sem deixar buraco)
- Logica e seguranca: teste SIM. Para testes novos de logica/seguranca, mostre a prova "falha antes / passa depois" (stash so do codigo de producao).
- Durante o trabalho rode so os testes do assunto; a suite completa UMA vez no fim, antes do push (o CI roda de novo no PR).
- Mudanca so de texto ou visual: teste so onde ha logica; o resto voce confere na verificacao local, comparando antes e depois.
- PR so de testes: prove que os testes pegam defeito com 3 mutacoes manuais (quebra temporaria do codigo, ver o teste falhar, desfazer e confirmar git status limpo).
- Sempre informe a contagem de testes (anteriores + novos) e explique a conta.

VERIFICACAO LOCAL
- So do que o PR muda, sem refazer telas intocadas. Suba o app local com banco temporario. Para telas, use o Chrome (se a extensao nao estiver conectada, use Chrome headless local sem instalar dependencia) e meça contraste/comportamento com valores reais, nao a olho.
- Pare servidores e apague arquivos e perfis temporarios que voce criou.

RELATORIO FINAL (vai para o RELATORIO.md na raiz, que voce SOBRESCREVE a cada tarefa; fica fora do Git e nunca e commitado; curto, em linguagem simples, nesta ordem)
1. DIVERGENCIAS do pedido primeiro ("nenhuma" se nao houver): onde o problema real era diferente, o que voce nao fez e por que.
2. Link do PR e commit; se o CI passou e se o PR esta limpo; que o merge NAO foi feito. Lista de arquivos alterados, com uma linha de justificativa para cada um.
3. O que mudou, item por item, em "antes | depois".
4. Testes: contagem (anteriores + novos), resultado do pytest e do ruff, e as provas "falha antes / passa depois".
5. Verificacao local: o que foi conferido e, quando houver tela nova, os comandos exatos para o Mateus ver o resultado.
6. Achados fora do escopo (liste, nao corrija).
7. Correcoes suas no meio do caminho, com honestidade (ex.: "meu script trocou o fim de linha; refiz").
Termine o RELATORIO.md com: "Aguardo sua conferencia antes do merge." No chat, ao final, escreva so UMA frase com o link do PR e o aviso de que o RELATORIO.md foi atualizado.

O QUE O MATEUS ESPERA DE VOCE
- Aprendizado junto com o codigo: explique o "porque" de cada decisao em poucas linhas.
- Prefiro arquivos completos e prontos, nao trechos soltos, quando eu pedir codigo para colar.
- Documentacao completa do projeto so quando eu pedir; nunca de forma automatica.
- Antes de mudar uma tela, descreva ou mostre o resultado esperado para eu aprovar.

# Etapa 14 — Fase 7 — ambiente independente de validacao

Preparacao tecnica, sem execucao. Producao nao esta ligada a este repositorio.

**Nao executar o workflow sem autorizacao expressa e independente da Fase 8.**
O campo manual de confirmacao e apenas uma trava operacional: nao substitui a autorizacao do proprietario.

## Material preservado

`material-recuperado.zip` contem os cinco arquivos originais da proposta, duas rotas de referencia, dois JSON-LD, `HASHES-SHA256.json` e `ALTERACOES.diff`. Os bytes dos arquivos foram copiados sem reconstrucao ou normalizacao de linhas. O hash do ZIP curado esta em `MATERIAL-SHA256.txt`. Este ZIP e um novo empacotamento dos arquivos recuperados, nao substitui os dois pacotes historicos.

Os pacotes historicos permanecem no ambiente de origem. Nenhum relatorio com caminhos locais, log historico ou configuracao de producao foi incluido no ZIP publico curado.

## Fluxo preparado

1. Acionamento exclusivamente manual, no repositorio de validacao e branch main.
2. Checkout sem credenciais persistidas; Node.js 22; leitura da base fixa publica `97632988b7c9f1ffca113f9ddaaa1b801cc76259` em subpasta descartavel. Nenhuma escrita ou chamada de deploy no original.
3. Conferencia do manifesto, diff e rotas originais; copia separada e aplicacao dos cinco arquivos da proposta.
4. Validacao das origens do lockfile e instalacao `npm ci --ignore-scripts --no-audit --no-fund`, sem executar codigo da aplicacao na etapa com rede.
5. Novo namespace Linux apenas com loopback; processos sem privilegios e sem credenciais herdadas. Fixture local e bloqueio IPv4/IPv6 comprovados antes do build; verificacao adicional no Chrome antes de iniciar a aplicacao.
6. Build, typecheck, lint e comparacao SSR/browser somente dentro desse namespace.

O workflow nao foi executado, nem as dependencias instaladas. A sintaxe e a logica foram revisadas por leitura; o funcionamento no runner, Chrome com sandbox padrao, prazo e compatibilidade permanecem sem evidencia de execucao.

Consulte `PLANO-VALIDACAO.md` e `AUDITORIA-FASE-7.md`. A preparacao nao e aprovacao funcional, SEO ou autorizacao de publicacao.

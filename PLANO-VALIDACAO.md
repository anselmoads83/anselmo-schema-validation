# Plano de isolamento e criterios — execucao futura autorizada

## Isolamento obrigatorio

O runner Ubuntu 24.04 e temporario. A instalacao inicial usa rede para Actions oficiais, Node e registry.npmjs.org. O lockfile deve conter somente tarballs HTTPS desse registry e integridade registrada. Nao ha lifecycle de dependencias, audit, fund, npx ou codigo da aplicacao na etapa conectada.

`isolate-runtime.sh` cria um namespace de rede novo, sem veth, bridge, NAT ou encaminhamento DNS. Ativa somente loopback. O host nao recebe portas nem regras de firewall novas. Build, SSR, Chrome e driver sao filhos do mesmo namespace. `setpriv` remove capacidades, impede elevacao posterior e troca para o usuario comum; `env -i` nao herda tokens, chaves ou configuracao GitHub. O navegador usa sandbox padrao: nao usar --no-sandbox nem relaxar protecoes para contornar falha.

Antes do build, `isolated-checks.sh` exige uma unica interface e nenhuma rota default IPv4/IPv6. Uma fixture sintetica em loopback deve responder; tentativas de conexao a enderecos de documentacao 192.0.2.1 e 2001:db8::1 devem falhar. Nenhum endpoint real e usado para testar o bloqueio. Antes da aplicacao, o driver repete comunicacao local e tentativa externa no navegador. Somente depois inicia a aplicacao.

O Chrome ainda recebe interceptacao que permite somente GET/HEAD para http://127.0.0.1:3000. Chamadas externas e metodos de submissao sao bloqueados. Isso e uma camada adicional; a barreira principal e a ausencia de rede externa no namespace, incluindo chamadas do servidor. CDP e aplicacao escutam apenas em loopback. Sem tunel, porta publica, banco ou credenciais de producao.

Qualquer falha na criacao do namespace, retirada de privilegios, pre-verificacao, navegador ou dependencias encerra o job. Nao existe fallback para o host, rede aberta ou producao. O namespace e removido no encerramento. O mecanismo esta preparado, mas sua comprovacao executada depende da Fase 8. Nenhuma garantia de testes aprovados e inferida da preparacao.

## Comparacao controlada

Base fixa: 97632988b7c9f1ffca113f9ddaaa1b801cc76259. O workflow le essa revisao exata; nao acompanha main/deploy/guara do original nem escreve nele. As duas rotas devem corresponder byte a byte aos originais documentados. A proposta recebe somente os cinco arquivos preservados. package.json e package-lock.json permanecem da base, sem nova dependencia de teste: Chrome do runner e CDP/WebSocket do Node sao utilizados. Se o Chrome esperado nao estiver disponivel, parar.

As duas variantes usam o mesmo lockfile, ambiente e comandos. Build: npm run build com NITRO_PRESET=node-server. Typecheck: compilador local tsc --noEmit. Lint: npm run lint. Falhas de qualquer variante encerram a aprovacao; comparar logs por variante para distinguir preexistencia de regressao. Nao suprimir regra, modificar lockfile ou habilitar scripts de instalacao automaticamente.

## Criterios de aprovacao

| Item | Evidencia exigida |
|---|---|
| Integridade | Nove hashes do manifesto, diff preservado e duas rotas da base correspondentes. |
| Instalacao/build | npm ci pelo lockfile e build completo aprovados para base e proposta. |
| Tipos/lint | Ambos aprovados; falha preexistente documentada continua pendencia, sem aprovacao silenciosa. |
| SSR real | HTML retornado pelo servidor Nitro, HTTP 200 na home e politica, JSON-LD parseavel; nao usar prototipo como SSR. |
| Grafos | Home com 11 nos, Organization unica, WebSite, WebPage e oito Service; politica com WebPage unico; IDs unicos e referencias resolvidas. |
| Escopo | Telefone institucional aprovado; sem endereco, geo, tipos locais, reviews ou campos comerciais nao autorizados. |
| Metadados | title, description e canonical presentes e identicos entre variantes, sem mudanca indevida. |
| Hidratacao | JSON-LD no DOM igual ao SSR; sem excecoes ou erros React/console. |
| Navegacao | Link real home para politica; sem acumulacao de scripts. Retorno, historico e demais rotas exigem checklist complementar abaixo. |
| Pagina inexistente | HTTP 404 e nenhum JSON-LD institucional indevido. |
| Formularios | Mesma quantidade e conteudo; nenhuma submissao real; qualquer POST bloqueado no navegador. |
| Logotipo | Imagens institucionais carregadas, dimensoes intrinsecas positivas e mesmas referencias locais. Revisao visual complementar obrigatoria. |
| Regressao | Nenhuma diferenca nao relacionada ao schema; checklist complementar aprovado antes de qualquer conclusao global. |

## Checklist complementar de interacao e imagem

O driver preparado cobre SSR, DOM, erros, link da politica, grafos, metadados, imagens e captura local da home. Ele nao comprova sozinho todos os comportamentos visuais ou interacoes de negocio.

Na Fase 8, preparar a observacao autorizada das capturas temporarias ou ampliar o driver, mantendo o mesmo isolamento, para revisar:
- desktop e mobile; menus e ancoras; home, politica, voltar/avancar;
- abrir e fechar Fale Conosco e MEI 360, incluindo Escape, abertura automatica e ausencia de duplicidade;
- consentimento, rejeicao e persistencia local de cookies;
- foco, teclado, layouts e sobreposicoes;
- logo legivel, proporcao e integracao com fundo sem recorte indevido;
- campos e validacao local dos formularios, sem envio e sem dados de cliente.

Capturas e logs ficam somente no filesystem temporario do runner. Nao ha upload-artifact, cache, Pages ou publicacao. Qualquer necessidade de exportacao/revisao desses arquivos exige escopo aprovado na fase seguinte; nao acrescentar publicacao automatica. Nao declarar regressao completa aprovada apenas porque o driver passou.

## Custos e limites

Runner padrao ubuntu-24.04 em repositorio publico: uso gratuito conforme documentacao consultada em 11/11/2026. Nao usar larger runners. Um unico job, timeout 45 minutos (abaixo de 6 horas por job); grupo de concorrencia exclusivo e sem cancelamento de execucao em andamento. Sem cache ou upload de artefatos. Retencao de logs configurada no repositorio: 90 dias. Filas e limites compartilhados da conta continuam aplicaveis. Se o repositorio deixar de ser publico ou o runner mudar, reavaliar antes de executar.

Fontes: https://docs.github.com/en/actions/concepts/billing-and-usage e https://docs.github.com/en/actions/reference/limits.

## Encerramento

Nenhuma execucao na Fase 7. Aprovar testes requer autorizacao independente; nenhuma aprovacao de teste autoriza deploy. Guara Cloud, Supabase, Brevo e site publicado permanecem fora do fluxo.

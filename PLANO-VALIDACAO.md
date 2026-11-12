# Fase 7D — criterios objetivos para futura auditoria e execucao

## Estado atual: nenhuma execucao liberada

O workflow tem somente workflow_dispatch, contents: read e job bloqueado incondicionalmente. A politica mantem autorizacao false, imagem null e hash de cache null. Sao bloqueios deliberados, nao parametros a preencher automaticamente. Uma futura autorizacao deve identificar o commit exato revisado. O SHA fornecido externamente deve coincidir com GITHUB_SHA e o checkout real; nao colocar no proprio commit um SHA que teria de corresponder ao hash dele mesmo.

## Imagem e aquisicao

Requisito pendente: imagem Linux auditada e disponivel localmente, por digest imutavel, com Node 22, npm, Python3, setpriv e Google Chrome com sandbox funcional. Nenhum pull, build de imagem, instalacao de ferramenta ou alteracao de protecoes e feito automaticamente. A imagem nao pode exigir --privileged, sandbox desabilitado, seccomp unconfined ou AppArmor desabilitado. Sua procedencia, configuracoes e bibliotecas devem ser auditadas antes de autorizar uso.

Requisito pendente: offline-cache.zip contendo somente _cacache, sem links e com SHA-256 aprovado. A criacao desse bundle deve ocorrer em aquisicao separada, com destinos restritos, TLS validado, redirecionamentos controlados e nenhum lifecycle ou codigo do projeto. Esse mecanismo de aquisicao conectada NAO foi implementado nesta entrega: nao ha ambiente/proxy auditado nem bundle aprovado disponivel. Por isso nao existe fallback para npm conectado. A fase de validacao faz apenas npm ci --offline --ignore-scripts --no-audit --no-fund, com configuracoes npm de usuario/global desativadas.

## Integridade e comparacao

prepare-material.py usa verificacoes explicitas, nao assert. Exige ZIP original e diff por hashes fixos, nove entradas do manifesto exatamente iguais as referencias documentadas, ausencia de duplicatas e limites de tamanho. Confere a base fixa 97632988b7c9f1ffca113f9ddaaa1b801cc76259 e worktree limpa antes de gerar copias. Nao reconstroi ou altera o material recuperado.

Lockfile v3 obrigatorio; entradas locais/bundled/workspaces e fontes fora de tarballs HTTPS de registry.npmjs.org sao recusadas. Integridade sha512 obrigatoria e coerencia de dependencias entre package.json/lockfile. Qualquer incompatibilidade com o lockfile recuperado e pendencia para revisao, nunca relaxamento automatico. Arquivos operacionais .env*, .npmrc, shrinkwrap ou credenciais sao recusados. .env.example nao e disponibilizado as cargas. Os snapshots e hashes de controle ficam protegidos; package/lock e fontes sao reconferidos apos instalacao, tipo, lint, build e runtime.

## Isolamento e supervisao

O supervisor do host e o unico usuario do Docker; o socket nunca entra no container. Ele usa imagem ja local, sem pull, network none, IPC privado, rootfs read-only e mounts enumerados. Nao ha rede host, publish de portas, dispositivos extras, volumes de outros containers ou modos privilegiados. /app, /tmp, /run e shm sao privados; limites de RAM, CPU e PIDs sao definidos.

O supervisor interno e root apenas dentro do container, com SETUID, SETGID, SETPCAP e KILL. Toda carga e lancada por setpriv com UID/GID dedicado, grupos suplementares vazios, conjuntos de capacidades zerados e no-new-privs. A aplicacao nao pode escrever controles/referencias/evidencias nem acessar a outra variante. O driver e Chrome usam outro UID e perfil exclusivo. O Docker controla PID/mount/network/IPC; a imagem continua compartilhando o kernel do host, risco residual conhecido.

O preflight confere contrato, politica, ferramentas, Node22, identidades, /proc/self/status, somente interface lo, rotas e ausencia de sockets conhecidos do host. A barreira principal e network none; a prova sintetica exige erro de falta de rota IPv4/IPv6, nao timeout generico. O navegador deve acessar fixture local e apresentar erro de rede conclusivo na tentativa a endereco de documentacao. Nenhum endpoint real e usado. Verificacao ambigua interrompe.

Npm, build, servidor e navegador nunca rodam no host. Ha prazos por ferramenta, inicializacao, CDP, pagina e container; timeout encerra a carga. O supervisor encerra todos os processos dos UIDs dedicados; o host remove o container/cgroup inteiro antes de apagar arquivos temporarios. Nenhuma falha permite continuar em ambiente menos restrito.

## Driver e evidencias

Chrome com sandbox padrao; nenhum --no-sandbox. CDP via pipe, sem listener TCP; targets inesperados interrompem o driver. Requisicoes da pagina permitem somente GET/HEAD local na porta da aplicacao. Submissoes e destinos externos sao recusados. Nao enviar formulario real nem usar dados de clientes.

O driver exerce o menu mobile (aria-label Abrir/Fechar menu) e o acordeao da politica (aria-controls card-01-content), com eventos de mouse e mudancas de estado obrigatorias. Isso comprova comportamento React nas duas paginas; JSON-LD existente no SSR sozinho nao comprova hidratacao. A navegacao por link real deve preservar identificador de documento e performance.timeOrigin. Retorno pelo historico tambem deve preservar documento. Sem prontidao baseada apenas em sleep.

Contexto/perfil/container novo por variante; viewports desktop 1280x900 e mobile 390x844. Metadados unicos e nao vazios no SSR e DOM; igualdade entre ambos e entre variantes. JSON-LD completo comparado aos JSONs aprovados; unica normalizacao: nome emitido do logo, com origem, caminho e asset local verificados. Logo institucional visivel obrigatorio, nao lista vazia. Pagina 404 deve permanecer sem JSON-LD.

Resultados de comparacao usam hashes, sem publicar conteudo de pagina. Mensagens de pacotes/app nao sao despejadas em logs publicos: supervisores emitem codigos fixos e resumos limitados. result.json e escrito tambem em falha; screenshots ficam apenas na area temporaria do driver, separada da aplicacao. Nao ha upload-artifact, cache remoto ou publicacao de evidencias. Em falha de inicializacao anterior ao driver, o supervisor emite codigo de bloqueio mesmo que nao exista result.json.

## Cobertura complementar obrigatoria

| Caso | Criterio antes de aprovacao global |
|---|---|
| Menus e ancoras | Abertura/fechamento, destino local correto, foco e comportamento em desktop/mobile; sem acessar links externos reais. |
| Fale Conosco e MEI360 | Abrir/fechar, Escape, foco, abertura automatica prevista e ausencia de duplicidade. |
| Cookies | Estado inicial limpo, aceitar/rejeitar opcionais, reabrir preferencias e persistencia somente no perfil local. |
| Formularios | Campos, validacao local e teclado; requisicoes de envio devem continuar bloqueadas. |
| Navegacao | Home/politica/historico; sem scripts acumulados nem metadados antigos. |
| Aparencia | Capturas nos dois viewports; logo, proporcao, fundo, tipografia, overlays e ausencia de recortes indevidos. |
| Acessibilidade basica | Ordem de foco e acionamento por teclado, sem campos ocultos recebendo foco indevido. |

Somente menu mobile, acordeao, navegacao/historico, SSR/DOM/grafos/metadados e verificacoes tecnicas do logo estao automatizados nesta revisao. Os demais casos continuam pendentes; nao sao marcados como aprovados. A forma de revisao humana/exportacao das capturas ainda requer escopo autorizado. O supervisor retorna resultado global INCOMPLETE_MANUAL_REVIEW e codigo nao zero mesmo quando todos os checks automatizados passam. Nao confundir teste parcial com homologacao.

## Riscos residuais e sequencia

1. Nova auditoria estatica dos controles e imagem/cache ainda pendentes.
2. So depois, eventual autorizacao expressa da revisao exata e escopo de execucao.
3. Preflight e compatibilidade real de imagem, Docker, Chrome sandbox e lockfile somente podem ser comprovados em execucao futura. Nenhuma ferramenta ou politica sera relaxada para contornar falhas.
4. Regressao completa depende do checklist complementar e evidencias revisaveis.
5. Aprovar testes nunca autoriza deploy. Producao, Guara Cloud, Supabase e Brevo nao integram o fluxo.

Timeout externo planejado: 45 minutos; containers limitados individualmente. Sem garantia antecipada de duracao, memoria ou compatibilidade. Qualquer falta de recursos ou dependencia offline encerra a tentativa.

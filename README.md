# Etapa 14 — Fase 7D — correcoes preparadas, execucao bloqueada

**Fase 8 NAO AUTORIZADA.** O workflow permanece somente manual e seu job esta bloqueado por `if: ${{ false }}`. `EXECUTION-POLICY.json` tambem mantem `phase8_authorized: false`. Nenhuma carga pode ser liberada simplesmente digitando uma frase no formulario.

Esta revisao substitui os controles operacionais da Fase 7. `AUDITORIA-FASE-7.md` e um registro historico; nao descreve o novo launcher. O plano atualizado esta em `PLANO-VALIDACAO.md`, e as limitacoes em `RELATORIO-FASE-7D.md`.

## Material original inalterado

`material-recuperado.zip` e `MATERIAL-SHA256.txt` nao foram modificados. Os cinco arquivos de proposta, duas rotas originais, dois JSON-LD, manifesto original e diff aprovado permanecem dentro do ZIP. SHA-256 do ZIP: `d9456a739e69e9e5559300de11a47d2eaa1ddc10c9edd35c4e125906faa9f43f`.

## Nova arquitetura preparada

- Nenhuma instalacao npm ou execucao de aplicacao no host.
- Imagem local previamente auditada, identificada por digest; sem pull automatico.
- Cache npm previamente auditado; instalacao exclusivamente offline e sem lifecycle.
- Containers separados por variante, sem rede, filesystem raiz somente leitura, IPC privado, limites de memoria/processos e nenhum socket ou porta do host.
- Aplicacao UID 62001 e driver/Chrome UID 62002, sem grupos suplementares nem capacidades; apenas o supervisor confiavel possui capacidades limitadas dentro do container.
- Controles e referencias em mounts somente leitura; perfis, fontes de trabalho, caches e evidencias separados.
- CDP por pipes privados, sem porta de depuracao acessivel a aplicacao.
- Interacoes React reais, verificacao de documento preservado na navegacao, comparacao completa de JSON-LD com a referencia e metadados SSR/DOM.
- Remocao forcada do container/cgroup pelo supervisor do host em falha ou timeout; nenhum fallback para execucao direta.

## Impedimentos mantidos de forma explicita

A imagem por digest e o bundle offline nao existem nesta entrega. Seus campos continuam nulos; o launcher recusa iniciar. Seleciona-los exige trabalho posterior autorizado, revisao de procedencia, versoes e compatibilidade, sem ampliar permissoes de aplicativos. Nao foi improvisada uma imagem, cache, proxy ou instalacao conectada.

Nem o launcher nem o driver foram executados. As correcoes precisam de nova auditoria independente. Compatibilidade do Chrome com sandbox, runtime e regressao funcional/visual continuam sem aprovacao. Nao usar --no-sandbox nem desabilitar seccomp/AppArmor.

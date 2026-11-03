# BMAD Handoff — Guia de refinamento e execução no Codex

## 1. Preparação

- Copiar este pacote para a pasta de trabalho do futuro repositório.
- Colocar os dados originais **localmente** sob `data/raw/` com os nomes descritos no enunciado, conforme direitos de uso e exposição; usar `.gitignore` onde necessário.
- Disponibilizar os PDFs para consulta local.
- Inicializar BMAD de acordo com **a versão efetivamente instalada**; comandos/nomes dos workflows podem variar, por isso não inventamos comandos específicos.
- Para usar Ponytail como apoio à implementação, seguir `PONYTAIL_WORKFLOW.md`; conferir instalação e hooks no Codex antes de habilitar. Opcional: continuar sem plugin caso o ambiente não o suporte. Não copiar `AGENTS.md` do Ponytail por cima do arquivo do projeto.
- Ler primeiro `README.md`, `PROJECT_BRIEF.md`, `PRD.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `AGENT_DESIGN.md`, `TEST_STRATEGY.md`, `ROADMAP.md`, `PONYTAIL_WORKFLOW.md` e `AGENTS.md`.

## 2. Prompt inicial sugerido para BMAD

> Atue como Product Manager, Software Architect, Senior AI Engineer e QA Lead. Estou realizando um desafio técnico Python de AI Engineer para Artefact. Leia o enunciado PDF e os CSVs/manual da loja, depois compare com o pacote `artefact_architecture_v2`. Sua tarefa é **refinar**, não recomeçar do zero. Primeiro faça um gap analysis: requisitos oficiais vs decisões P0/P1/P2, riscos, ambiguidades e arquitetura proposta. Preserve a LLM Factory com provider adapters, a opção de WhatsApp por Channel Adapter, RAG documental rastreável, ferramentas determinísticas para dados, Market Price Intelligence separado e MCP como adapter opcional. Não apresente preços de snapshot como dados ao vivo, não exponha PII de pedidos e não transforme o MCP em dependência do core. Gere um PRD revisado, architecture review com ADRs, épicos e histórias pequenas, prioridades e acceptance criteria testáveis. Marque qualquer modificação de premissas, pergunte apenas se há bloqueador real, e documente as suposições. Preserve o uso opcional do Ponytail como **ferramenta de engenharia** para simplificação e revisão do diff, sem incorporá-lo ao runtime nem priorizar redução de LOC sobre segurança e contratos. Inclua gates de revisão e testes por story. **Não comece a implementar antes de listar o backlog consolidado e seu caminho crítico.**

## 3. Perguntas críticas para o review arquitetural

1. O contrato normalizado de `LLMPort` preserva chamadas de ferramentas e erros para todos os provedores planejados?
2. Existe algum acoplamento desnecessário criado para prover 'suporte a qualquer modelo', além das capacidades que um modelo oferece?
3. Quais regras comerciais devem permanecer determinísticas em Python, e quais somente recuperar do PDF?
4. A autenticação de pedidos será realmente demonstrada com fluxo seguro ou será limitada a uma demo explícita com principal injetada?
5. Pode a integração WhatsApp ficar somente no nível de adapter testado caso não haja credenciais Meta?
6. Market search/mean price tem rigor de modelo/variante, links e datas e fallback offline?
7. MCP traz valor demonstrável sem duplicar serviço ou introduzir autenticação frágil?
8. Os testes de comportamento e security negatives são suficientes para detectar alucinações e vazamentos?
9. O README final mostra honestamente o trabalho de assistentes de IA e as decisões do candidato?
10. A simplificação sugerida por Ponytail preserva LLM Factory, canais, rastreabilidade, autorização e testes? O plugin continua opcional e fora do runtime?

## 4. Entregáveis esperados do refinamento

- Matriz `enunciado → requisito → story → teste → demonstração`.
- Lista de assumptions com status (confirmada, assumida, ambígua).
- Arquitetura aprovada + ADRs com rejected alternatives.
- Backlog ordered P0→P1 com stories implementáveis independentemente.
- Definition of Done por story + gate de release.
- Threat model curto e testes negativos de privacidade/prompt injection.
- Plano de 3–5 conversas capturadas **durante execução real**.

## 5. Prompt para Codex ao iniciar story

> Implemente somente a story `<ID>` conforme `ROADMAP.md` e a versão refinada pelo BMAD. Antes de alterar código, confirme escopo, dependências e contratos, identifique quais testes adicionar e quais arquivos mudam. Respeite `AGENTS.md`, preserve Clean/Hexagonal boundaries, não use APIs externas no caminho de testes básicos, execute os checks disponíveis, reporte falhas e limitações sem inventar sucessos. Atualize documentos necessários e proponha um commit incremental descritivo. Use Ponytail, caso esteja instalado e revisado, para examinar simplicidade e realizar code review do diff. Liste sugestões aceitas/rejeitadas e razões; não sobrescreva `AGENTS.md` e não sacrifique segurança, contratos, nem cobertura para reduzir LOC. Se o plugin não estiver disponível, faça a mesma revisão manual e siga normalmente. Não implemente outras stories sem necessidade.

## 6. Workflow recomendado

`BMAD gap analysis → backlog aprovado → Codex story + Ponytail opcional → testes → Ponytail review opcional + revisão independente → correções/regressão → commit → próxima story → evals & hardening → README & examples → delivery`.

Se BMAD recomendar alterações, preservar o racional nos ADRs e não perder os requisitos oficiais. Completar P0 e guardar P1 como opcional se prazo estiver próximo.

## 7. Critérios de 'handoff concluído'

O repositório de desenvolvimento tem docs acessíveis, dados localmente disponíveis (não necessariamente públicos), ambiente reproduzível, backlog ordenado, primeira story pequena selecionada e regras de desenvolvimento disponíveis em `AGENTS.md`.

## 8. Instrução adicional para o review de cada story

> Antes de aprovar, verifique se o Codex reaproveitou funções existentes, introduziu abstrações com usuários reais e testou as regras críticas. Se Ponytail estiver instalado, faça revisão do diff usando a invocação apropriada ao host, registre findings e somente aplique refatorações com testes verdes. Segurança e comportamento têm precedência sobre concisão.

**Instalação e verificação:** consultar `PONYTAIL_WORKFLOW.md`, que documenta comandos de Codex e alternativas. A adoção não deve bloquear a entrega do desafio.

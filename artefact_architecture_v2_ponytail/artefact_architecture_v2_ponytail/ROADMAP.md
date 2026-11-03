# Roadmap / Product Backlog — Artefact AI Engineer

**Status:** plano para BMAD refinar, estimativas **não** comprometidas. Não confundir este documento com evidências de implementação concluída.

## Sequência de entrega

| Marco | Fase | Dependências | Entregável / Quality Gate |
|---|---|---|---|
| M0 | Discovery | fontes | requisitos, suposições, modelo de dados e prioridades |
| M1 | Architecture | M0 | contratos de ports, ADRs, threat model, provider strategy |
| M2 | Foundation | M1 | pyproject, lint, CI, fake LLM, bootstrap SQLite, CLI mínima; Ponytail opcional configurado/revisado no ambiente de desenvolvimento |
| M3 | Core data tools | M2 | ingestão CSV e consultas tipadas de catálogo/pedidos/promoções |
| M4 | Policies RAG | M2 | extraction/index/retrieval + testes de fonte |
| M5 | Agent MVP | M3+M4 | LLM factory, tool loop, sessões, CLI/API, evals centrais |
| M6 | Hardening | M5 | segurança, erros, regressões, README, exemplos reais |
| M7 | WhatsApp | M6 | adapter simulado e integração real opcional |
| M8 | Market Price Intelligence | M6 | cache, provider externo opcional, comparação com proveniência |
| M9 | MCP | M6 | adapter MCP com tools de domínio e testes |
| M10 | Delivery | M6 (+ P1 concluído) | Git público, documentos, 3–5 exemplos, prazo respeitado |

**Gate de release:** M6 + M10 são necessários para submeter; M7–M9 são incrementos opcionais e não devem ameaçar o deadline.

## Épicos / histórias sugeridas para BMAD

### EPIC-01 — Bootstrap e engenharia

- **ST-001 [P0]** Criar estrutura `src/`, `pyproject.toml`, configuração validada e `FakeLLMProvider`. AC: pacote importa, ambiente de testes sobe sem rede, testes básicos passam.
- **ST-002 [P0]** Implementar ports de repositório, LLM, retrieval e sessões. AC: core não importa SDKs/infra; cobertura de contratos por fixtures.
- **ST-003 [P1]** GitHub Actions com lint, type check e pytest. AC: executa sem secrets externos.

### EPIC-01A — Processo de desenvolvimento assistido (não runtime)

- **ST-023 [P1-processo, não depende de P0]** Verificar e opcionalmente instalar o Ponytail no ambiente Codex, revisando hooks e procedência. AC: instalação validada ou fallback manual documentado; nenhuma dependência adicionada ao runtime/CI.
- **ST-024 [P1-processo]** Aplicar revisão de simplicidade e review de diff por story relevante. AC: mudanças revisadas, findings registrados, checks repetidos e justificativas para ajustes que não foram adotados. Não bloquear uma story por indisponibilidade do plugin.

Estas histórias são **checkpoints de workflow**, não funcionalidades a serem demonstradas ao cliente. Usar `PONYTAIL_WORKFLOW.md` e ADR-004.

### EPIC-02 — Dados operacionais

- **ST-004 [P0]** Importar CSVs com schema, tipos, `specs` JSON e FK. AC: números/IDs válidos; falha de ingestão não deixa DB parcial.
- **ST-005 [P0]** Produtos: busca, filtros, detalhes, disponibilidade. AC: `active AND qty>0`, paginação e fallback.
- **ST-006 [P0]** Promoção e cálculo de meios de pagamento. AC: `Decimal`, promoção não cumulativa e limites de parcelamento com casos de borda.
- **ST-007 [P0]** Pedidos com controle de acesso. AC: teste autoriza pedido do dono e nega de outro; anon não vaza dados; demo explicitamente marcada.

### EPIC-03 — Retrieval documental

- **ST-008 [P0]** Extração do PDF com seções e páginas. AC: chunks têm IDs e metadados de origem, cobertura das principais seções.
- **ST-009 [P0]** Retriever textual e avaliação por perguntas. AC: expected sections recuperadas em suite documentada; insuficiência tratada.
- **ST-010 [P2]** Testar embeddings/híbrido se retrieval falhar. AC: comparação por métricas e ADR atualizado, sem vector DB gratuito por default.

### EPIC-04 — Agente, provider e canais

- **ST-011 [P0]** LLM Factory com um provider real + fake. AC: swap por `LLM_PROVIDER`; incompatibilidade de capacidade gera erro controlado.
- **ST-012 [P0]** Orquestrador tool calling com schema, autorizações, timeout e máximo de chamadas. AC: tool calls audíveis/validados, falhas tratadas.
- **ST-013 [P0]** Histórico por sessão e gestão de contexto. AC: follow-up de preço mantém produto e sessões são isoladas.
- **ST-014 [P0]** CLI e FastAPI com endpoints documentados. AC: examples de curl/CLI testados, API não exige WhatsApp.

### EPIC-05 — Qualidade e entrega básica

- **ST-015 [P0]** Testes de domínio, integração, evals e segurança. AC: casos T01–T16/T18–T20 pertinentes passam; resultados e limitações documentados.
- **ST-016 [P0]** README final + ADRs + 3–5 transcrições executadas. AC: reviewer clona/instala/usa em ambiente suportado; declaração do uso de IA.
- **ST-017 [P0]** Revisão independente e hardening. AC: riscos críticos resolvidos, secrets/PII ausentes, validação de entrega.

### EPIC-06 — WhatsApp

- **ST-018 [P1]** Channel Adapter + contrato WhatsApp com payload de fixture. AC: webhook normalizado, dedupe, assinatura inválida rejeitada.
- **ST-019 [P1]** Conexão opcional com Cloud API. AC: configuração por secrets, mock HTTP na CI, guia para credenciais reais; fora da conta Meta não prometer integração verificada.

### EPIC-07 — Mercado

- **ST-020 [P1]** Ports/DB para ofertas de mercado, TTL e agregação. AC: separação preço oficial/externo, rejeição de variante, dados insuficientes rotulados.
- **ST-021 [P1]** Provider de pesquisa autorizada e atualização sob demanda/job opcional. AC: URL/data/fontes, timeout/fallback, logs sem dados privados.

### EPIC-08 — MCP

- **ST-022 [P1]** Servidor MCP expondo catálogo e políticas via mesmos use cases. AC: testes confirmam mesmos contratos/regras; pedidos omitidos sem auth robusta.

## Critérios de uso de Ponytail

- O workflow pode começar no M2 e é **opcional/independente** do caminho crítico do projeto.
- Revisar os hooks antes de confiar; não trocar `AGENTS.md` do projeto por arquivo de terceiros.
- Aplicar sugestões de redução de complexidade **somente** se preservar contratos, segurança e comportamento.
- Registrar em cada story os testes reexecutados, findings importantes e eventual fallback manual.
- Ver `PONYTAIL_WORKFLOW.md` e `docs/adr/ADR-004-ponytail-development-workflow.md`.

## Dependências e paralelismo

- `ST-004` antes de ST-005/006/007.
- ST-008 antes de ST-009.
- ST-011 + ST-005/006/007 + ST-009 antes do tool loop final ST-012.
- ST-012 + ST-013 antes de ST-014/015/016.
- ST-018, ST-020 e ST-022 podem evoluir em paralelo **após** estabilização do core.

## Suggested commit sequence (executar commits reais)

1. `docs: define requirements architecture and ADRs`
2. `chore: bootstrap python project and checks`
3. `feat(data): import validated CSV snapshot`
4. `feat(tools): add catalog and promotion services`
5. `feat(retrieval): index and search policy sections`
6. `feat(agent): add configurable LLM factory and tool loop`
7. `feat(api): add CLI sessions and HTTP interface`
8. `test: add domain integration and agent evaluations`
9. `docs: add README and verified conversations`
10. `feat(whatsapp): add optional channel adapter` (se entregue)
11. `feat(market): add cached market comparison` (se entregue)
12. `feat(mcp): expose domain tools via MCP` (se entregue)

Os commits listados são **sugestões de unidade de trabalho**. Não criar commits fictícios nem reescrever o histórico para fingir desenvolvimento progressivo.

## Gate operacional por história

Story planejada → análise de contrato e reuso → implementação Codex (Ponytail opcional) → testes → review de diff (Ponytail opcional) + segurança → regressão após refatoração → docs → commit. Se um requisito não puder ser atendido, documentar decisão/limitação antes de seguir.

## Revisão final / submissão

- Verificar o prazo **no e-mail** do processo (não informado no PDF).
- Verificar permissão de inclusão dos arquivos da loja no repositório público, especialmente `customers.csv` e manual classificado como interno.
- Auditoria de secrets e PII; README e `.env.example` revisados.
- Pipeline passa; executar exemplos e salvar saída real.
- Relatar no README o uso real de Codex/BMAD/Ponytail, sem atribuir ao plugin benefícios ou métricas não medidas; garantir CI independente do plugin.
- Publicar link no e-mail original. Não alterar repositório após deadline.

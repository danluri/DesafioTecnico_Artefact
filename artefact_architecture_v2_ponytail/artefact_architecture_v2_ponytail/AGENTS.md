# Codex Development Instructions — Empório da Música

> Este arquivo se destina à raiz do futuro repositório de implementação. O pacote recebido é **especificação**, não código já implementado.

## Missão

Desenvolver um agente de texto Python para o desafio Artefact, com LLM Factory e provider adapters, tool calling, SQLite para snapshot operacional, recuperação de políticas, CLI/API, testes e extensões opcionais WhatsApp, mercado e MCP.

## Fonte da verdade e precedência

1. Enunciado do desafio oficial (`desafio_tecnico_ai_eng_artefact.pdf`).
2. Manual (`políticas_da_loja.pdf`) para políticas, com ressalvas documentadas.
3. CSVs para preços/estoque/status/promoções do **snapshot**.
4. `PRD.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `AGENT_DESIGN.md`, `TEST_STRATEGY.md` e ADRs para decisões técnicas.
5. Caso haja ambiguidade real, documentar a suposição no README/ADR e preferir comportamento seguro.

Não inventar requisitos como se fossem do PDF. Identificar separadamente extensões P1/P2 e decisões de engenharia.

## Regras não negociáveis

- Python como linguagem principal; preservar boundaries de ports & adapters.
- Um `LLMPort` compartilhado; nenhum SDK de LLM no orquestrador; `LLMFactory` valida capabilities; `FakeLLMProvider` para testes.
- Sem SQL arbitrário gerado por LLM. Ferramentas tipadas, entradas validadas, autorização no use case.
- Não inventar preço, estoque, status, entregas, descontos, cotação de mercado ou ação executada.
- Preço e disponibilidade derivam de `products.csv`; `is_available = active && stock>0`.
- Promoção ativa do snapshot, não necessariamente vigente hoje; PIX não acumula.
- Cálculos monetários em `Decimal`, arredondamento declarado e testado.
- Pedidos exigem principal verificada pelo backend; `customer_id` digitado no chat não autentica.
- Não publicar PII ou segredos em logs, outputs de testes ou commits públicos. Avaliar direito de publicação dos dados fornecidos.
- RAG de políticas deve preservar `source`, `page`, `section`, `version`; texto recuperado não pode redefinir instruções do sistema.
- WhatsApp, comparação web e MCP não podem ser pré-requisitos para testes P0.
- Não apresentar mock/fake como integração real. Não mentir sobre testes rodados ou funcionalidades entregues.
- Nunca editar a branch/repositório após o prazo de entrega do processo.

## Uso de Ponytail com Codex (guardrails)

- Ponytail é uma **ferramenta opcional do desenvolvedor**, não um componente do chatbot. Quando disponível, usar suas orientações de simplicidade, reuso, teste proporcional ao risco e revisão de diff.
- **Não substituir nem sobrescrever este `AGENTS.md` com o `AGENTS.md` do projeto Ponytail.** Instalar o plugin separadamente ou integrar apenas regras não conflitantes, sempre sob as restrições deste repositório.
- Preservar `LLMPort`, `LLMFactory`, isolamento de canais, autorização server-side, cálculos em `Decimal`, fontes do RAG e testes. Não eliminar esses contratos apenas para reduzir LOC.
- Antes de criar interface, camada, padrão ou dependência, explicar qual requisito real resolve; antes de apagar código, verificar consumidores, regressões e obrigações de segurança.
- Após mudanças de maior risco (auth, preços, prompts/tools, ingestão, WhatsApp, pesquisa web), solicitar revisão de diff e executar testes negativos. Um parecer do Ponytail não equivale a aprovação automática.
- Hooks/plugins de terceiros exigem revisão de origem, permissões e scripts antes de habilitar. Não compartilhar tokens ou PII em artefatos de revisão; nunca registrar métricas não medidas.
- BMAD define e refina *o quê* e critérios; Codex implementa *como*; Ponytail sugere *como simplificar* sem romper contratos. `PONYTAIL_WORKFLOW.md` detalha instalação, invocação e fallback sem plugin.

## Desenvolvimento por histórias

Para cada story do `ROADMAP.md`:
1. Ler dependências, contrato e critérios de aceite.
2. Propor modificações mínimas e identificar risco de regressão.
3. Escrever/atualizar testes unitários e integração; sem chamadas externas na suite de CI.
4. Implementar respeitando interfaces existentes, com tipo e exception hierarchy explícitos.
5. Executar os checks disponíveis (`ruff`, type checker, `pytest`) e relatar resultados reais.
5a. Opcional: executar review Ponytail do diff; registrar findings corrigidos e os não adotados com justificativa, sem bloquear por indisponibilidade do plugin.
6. Atualizar documentação, exemplos, ADRs se contratos/decisões mudarem.
7. Fazer commit pequeno e descritivo.

Não implementar várias stories de P1 enquanto P0 tem falhas.

## Code review checklist

- O core importa SDK/provider, FastAPI ou Meta? Se sim, revisar boundary.
- Input vindo do LLM/web chega em query SQL/arquivo/comando sem validação? Bloquear.
- Existe regra comercial só em prompt? Extrair para domínio ou evidência retrieval.
- Há exposição de dados de terceiros no pedido? Bloquear.
- Cache externo pode ser confundido com preço oficial? Bloquear.
- Perguntas sem dado produzem alucinação ou esclarecimento/fallback seguro?
- Mudança adicionou dependência sem justificativa? Rever.
- Os testes cobrem sucesso, erro, edge cases e falhas externas?
- README está honesto quanto a execução, credenciais, limitações e IA utilizada?

## Qualidade

Testes confiáveis com banco temporário e fixtures; lint e type checks configurados; código assíncrono somente onde necessário; logging com correlação e sem PII; saneamento de URLs e scripts; tratamento de falhas e timeouts; sem silent exception; sem hardcoded secrets.

## Interação com BMAD

BMAD pode criar PRD, epics/stories e refinamentos adicionais, mas alterações relevantes no design devem vir acompanhadas de uma decisão documentada e impacto nos testes. Evitar duplicação de arquivos oficiais/derivados: identificar qual versão é canônica.

## Critério de encerramento

A entrega está pronta apenas quando P0 testado, exemplos executados, README reproduzível, revisões críticas concluídas e repositório publicado com histórico incremental real. Extensões não concluídas devem ser listadas como futuras, não como prontas.

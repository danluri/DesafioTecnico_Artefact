# ADR-003 — WhatsApp, Market Search e MCP como adapters opcionais

**Status:** proposed.

## Contexto

O desafio não exige integração com Meta, pesquisa web de concorrentes nem MCP. Essas capacidades demonstram engenharia, porém podem consumir tempo e introduzir dependências de credenciais/custo/infra.

## Decisão

Canais são adapters do mesmo `ConversationService`: CLI/API P0, WhatsApp P1. Market search é um port opcional com cache/proveniência, sem alterar preço oficial. MCP Server reutiliza os serviços de domínio como adapter, jamais duplicando regras. Todos três protegidos por feature flags e mocks para CI.

## Consequências

P0 é executável offline (com FakeLLM), e demonstrável com 1 provider real configurado. WhatsApp real requer credenciais/conta autorizada, web search requer provedor e fontes válidas, MCP requer controle de acesso. Não prometer 'em produção' quando apenas adapter foi testado.

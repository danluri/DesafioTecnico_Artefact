# ADR-001 — LLM Factory + Provider Adapters

**Status:** proposed · **Contexto:** projeto necessita trocar provedor/modelo sem modificar orquestrador.

## Decisão

Definir `LLMPort` normalizado e `LLMFactory` selecionada por configuração, com adapters dos provedores e `FakeLLMProvider`. Exigir capabilities, especialmente tool calling, e validar compatibilidade na inicialização. Não prometer compatibilidade universal para modelos que não suportam ferramentas.

## Alternativas

- SDK de um provedor acoplado: simples no primeiro dia, troca difícil.
- Framework universal obrigatório: reduz glue code, mas pode obscurecer contratos e adicionar dependências.
- Factory + adapters: implementação inicial levemente maior, testes e portabilidade melhores.

## Consequências

Manter mapeamento de mensagens, tools e uso por provider; escrever testes de contrato. MVP pode ter 1 provider real + fake; documentação de extensibilidade não equivale a afirmar suporte real a todos.

# Architecture Diagrams

## Dependency direction

```mermaid
flowchart LR
  Delivery[CLI / HTTP / optional channels] --> Application[Application services]
  Application --> Domain[Domain rules]
  Application --> Ports[Ports]
  Infrastructure[SQLite / policy index / LLM providers / external APIs] --> Ports
  Domain --> Stdlib[Domain types and standard library]
```

## P0 runtime shape

```mermaid
flowchart TD
  User[Customer or evaluator] --> Channel[CLI or HTTP]
  Channel --> Conversation[ConversationService]
  Conversation --> Session[SessionRepository]
  Conversation --> Orchestrator[AgentOrchestrator]
  Orchestrator --> LLM[LLMPort / FakeLLM]
  Orchestrator --> Tools[Allowlisted ToolRegistry]
  Tools --> Domain[Catalog / payment / order services]
  Domain --> SQLite[(SQLite snapshot)]
  Tools --> Retriever[PolicyRetriever]
  Retriever --> Index[(Policy chunks and FTS5)]
```

## Runtime boundaries

- Offline test: FakeLLM, temporary SQLite, anonymized fixtures, no network.
- Local demonstration: SQLite snapshot, selected local channel, optional configured real provider.
- Optional integration environment: explicit secrets and feature flags; failures isolated from P0.

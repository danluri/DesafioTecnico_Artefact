# ADR-002 — Retrieval híbrido: SQL + RAG por seção

**Status:** proposed.

## Contexto

CSV com dados transacionais exige filtros, valores exatos e autorização. PDF interno contém políticas textuais com seções numeradas e apenas 8 páginas.

## Decisão

SQL parametrizado e serviços de domínio para produto, estoque, promoções e pedidos. Retrieval por seção + metadados de fonte para políticas (FTS5/BM25 como baseline). Avaliar embeddings por métricas antes de adotar vector database.

## Trade-offs

- Apenas LLM com corpus inteiro: barato de codificar mas difícil rastrear, atualizar e testar.
- Apenas RAG vetorial para tudo: ruim para valores exatos e controle de acesso.
- SQL + retrieval documental: responsabilidades explícitas e respostas verificáveis.

## Consequências

Dois caminhos de recuperação, ambos testados. Políticas ambíguas não resolvidas arbitrariamente pelo modelo. Fonte PDF não é instrução privilegiada sobre o sistema.

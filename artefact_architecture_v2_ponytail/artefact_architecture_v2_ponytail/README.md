# Empório da Música — Architecture V2.1 / BMAD + Codex + Ponytail Handoff

> **Status: planejamento, não implementação.** Este pacote contém decisões propostas e especificações para refinar com BMAD e desenvolver com Codex. Nenhuma funcionalidade ou teste de aplicação é declarada como implementada.

## Ordem de leitura

1. [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) — objetivo, escopo, critérios de sucesso.
2. [`PRD.md`](PRD.md) — requisitos, fluxos e critérios de aceite.
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) — portas/adaptadores, fluxos, qualidade e segurança.
4. [`DATA_MODEL.md`](DATA_MODEL.md) — diagnóstico real dos arquivos CSV, esquema e regras.
5. [`AGENT_DESIGN.md`](AGENT_DESIGN.md) — LLM Factory, ferramentas, RAG, WhatsApp, MCP e prompts.
6. [`TEST_STRATEGY.md`](TEST_STRATEGY.md) — testes, métricas e conjuntos de avaliação.
7. [`ROADMAP.md`](ROADMAP.md) — stories, dependências, milestones, gates e commits.
8. [`AGENTS.md`](AGENTS.md) — instruções para o Codex; mover/copiar para raiz do futuro repositório.
9. [`BMAD_HANDOFF.md`](BMAD_HANDOFF.md) — prompt inicial e sequência de refinamento.
10. [`PONYTAIL_WORKFLOW.md`](PONYTAIL_WORKFLOW.md) — instalação verificada, integração com Codex, revisões e limites.
11. [`docs/adr/`](docs/adr/) — ADRs propostos, incluindo ADR-004 (Ponytail).

## Fontes primárias utilizadas

- `desafio_tecnico_ai_eng_artefact.pdf` (3 páginas)
- `políticas_da_loja.pdf` (8 páginas; versão 2.1, junho de 2025)
- Seis CSVs: `categories`, `customers`, `order_items`, `orders`, `products`, `promotions`.

Esses arquivos originais **não estão incluídos neste ZIP**. No repositório final, documentar como obter/copiá-los para `data/raw/`, conferir permissão de publicação e evitar exposição indevida de dados pessoais no Git público. Para demonstração reproduzível, gerar fixtures sintéticas e/ou um conjunto explicitamente autorizado.

## Decisões já acordadas

- Python como linguagem principal; arquitetura modular inspirada em ports & adapters.
- **LLM Factory + provider adapters** para alternar LLM por configuração, com declaração de capacidades.
- Tool calling com ferramentas restritas e serviços determinísticos para SQL, preços, estoque e pagamento.
- RAG documental sobre manual de políticas com fonte, seção e página; começar com recuperação textual e medir antes de introduzir embeddings.
- Canais CLI e HTTP; adaptador WhatsApp e integração oficial opcionais.
- Pesquisa de preços de mercado com **tabela separada, cache e rastreabilidade**, sem sobrescrever o preço do exercício.
- MCP como adapter adicional sobre os mesmos serviços, não como requisito do caminho crítico.
- Testes automatizados, evals de comportamento, security review, README reproduzível, 3–5 exemplos reais.
- **Ponytail (opcional como ferramenta de desenvolvimento)** com Codex para reduzir duplicação e complexidade; não integra o runtime do agente nem substitui testes, review de segurança ou critérios de aceite. Adoção prevista desde o início do workflow de engenharia, sem bloquear P0 se indisponível.

## Observações importantes

1. Os registros representam dados fornecidos ao desafio, não um ERP em tempo real. **Não prometer preços/estoques reais atuais**.
2. Existe diferença entre números de contato indicados no manual (§1.2 vs §7); resolver pela finalidade do canal ou esclarecer a ambiguidade, documentando.
3. O manual estabelece regras de troca/garantia com potencial interpretação jurídica delicada; não reduzir a garantia legal a 30 dias.
4. O enunciado exige histórico progressivo de commits e proíbe mudanças após o prazo de entrega informado no e-mail; **data e hora exatas não constam do PDF**.

## Como começar

Abrir [`BMAD_HANDOFF.md`](BMAD_HANDOFF.md) com BMAD no ambiente Codex, confrontar as decisões com o enunciado e produzir um backlog refinado. Implementar story por story com testes e commits reais. Se optar pelo Ponytail, seguir [`PONYTAIL_WORKFLOW.md`](PONYTAIL_WORKFLOW.md), revisar os hooks antes de confiar e manter `AGENTS.md` do projeto como contrato prioritário.

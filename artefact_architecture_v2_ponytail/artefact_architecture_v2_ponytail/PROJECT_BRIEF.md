# Project Brief — Empório da Música / Artefact AI Engineer

## Contexto e problema

Desafio de seleção: prototipar em **Python** um agente de texto para a loja fictícia Empório da Música (Campo Grande/MS). O atendimento atual é feito por pessoas; perguntas recorrentes sobre horários, preços, disponibilidade, status de pedidos e políticas sobrecarregam a equipe.

O avaliador declara priorizar **raciocínio, clareza, iniciativa e decisões justificadas** mais do que uma solução perfeita. O objetivo não é fazer um ERP nem um produto de atendimento comercial completo.

## Visão

Construir um atendente confiável, amigável e rastreável, capaz de usar **ferramentas de dados estruturados** e **recuperação de políticas** sem alucinar preços, prazos, estoque ou status; demonstrar design extensível para LLMs e canais.

## Critérios de sucesso

- Cliente consegue perguntar sobre catálogo, preço, estoque, política comercial e horário.
- A aplicação escolhe corretamente entre **consulta estruturada** e **recuperação documental**.
- O LLM nunca é a fonte de verdade de preços, estoques, pedidos ou regras calculáveis.
- Existe experiência de conversa com contexto de várias mensagens.
- Há fallback seguro para dados ausentes, fonte ambígua, falha de API e assuntos alheios à loja.
- Executa localmente de modo reproduzível; testes automatizados sem credenciais externas.
- Repositório público com histórico incremental, README, limitações, declaração do uso de IA e 3–5 conversas demonstrativas.

## Escopo P0 (mínimo obrigatório + engenharia responsável)

- CLI e/ou API FastAPI; o plano prefere ambos se não comprometer entrega.
- Catálogo, disponibilidade, detalhe de produto, promoções, política de PIX/parcelamento, dados gerais.
- Pedido com **autorização de acesso**; ausência de credencial válida => não revelar detalhes privados.
- RAG de políticas com identificação de fonte; persona da loja.
- LLM Factory com pelo menos um adaptador real + um fake; os outros provedores podem ser opcionais, declarados com suas limitações.
- Sessões, logs sanitizados, tratamento de erros e testes.

## P1 (diferenciais após P0 estável)

- WhatsApp adapter (mock/testes) + Cloud API oficial quando houver credenciais.
- Market price intelligence: consulta externa autorizada, identidade de modelo, cache e comparação, sem alterar preço oficial.
- MCP Server adapter reutilizando os mesmos casos de uso.
- CI, ADRs, evaluations de regressão, métricas e rastreamento de tools.

## P2 / fora do escopo base

- Checkout, cancelamento real, registro real de reclamações, sistema de tickets, estoque sincronizado com ERP, autenticação comercial completa, multiagentes, vector DB externo, infraestrutura cloud obrigatória, UI sofisticada.

Esses recursos não devem ser simulados como ações realizadas. Se houver necessidade de encaminhar a um humano, orientar o usuário sem afirmar que foi aberto um chamado quando não foi.

## Ferramentas de desenvolvimento (não runtime)

O fluxo proposto é **BMAD (refino e critérios de aceite) → Codex (implementação) + Ponytail (orientação de simplicidade/review) → testes estáticos e automatizados → revisão humana → commit**. Ponytail é opcional e não entra como requisito do produto; funciona como prática para evitar abstrações prematuras em Factory, adapters, RAG e MCP. Preservar decisões aprovadas, segurança e evidências de testes mesmo quando simplificar significar mais código. Ver `PONYTAIL_WORKFLOW.md` e `docs/adr/ADR-004-ponytail-development-workflow.md`.

## Restrições e riscos

- Fonte CSV é **snapshot**, não informação ao vivo. Datas de pedidos abrangem 2025–mar/2026; não extrapolar previsão de entrega atual.
- Manual interno possui inconsistências de contato e regras que merecem linguagem prudente.
- Alguns produtos possuem estoque positivo embora `status != active`; alguns ativos têm zero estoque.
- Dados de clientes identificáveis estão no CSV; Git público exige verificação de permissão e política de exposição.
- WhatsApp real depende de conta, token, configuração, templates e regras de mensagem da Meta.
- Web search real pode falhar e anúncios podem referir-se a variantes diferentes.

## Não objetivos de desempenho

Não prometer SLA de produção com protótipo local. O manual menciona atendimento em até 5 minutos durante expediente: documentar como requisito operacional da loja, não como métrica demonstrada automaticamente pelo código sem infraestrutura.

## Definição de pronto da entrega

Todos os itens P0 possuem testes ou evidências reproduzíveis; comportamento de IA é avaliado por cenários; README explícito sobre suposições, limites e papel dos assistentes de código; Git público com commits reais, exemplos e sem segredos.

# ADR-004 — Ponytail como ferramenta opcional de engenharia

- **Status:** Proposed / Accepted for planning (a confirmar no refinamento BMAD)
- **Data:** 2026-11-01
- **Contexto:** O projeto incorpora LLM Factory, RAG, adaptadores de canal e extensões P1. Há risco de sobreengenharia e duplicação de código ao gerar implementações por agentes. O desafio exige justificar o uso de assistentes de IA no README.

## Decisão

Usar o **Ponytail opcionalmente, junto ao Codex**, para orientar reuso, simplicidade e revisão de código. Aplicar depois do refinamento BMAD e durante cada story relevante. Manter o Ponytail **fora do runtime**, dos requirements Python, do fluxo do chatbot e como não dependência da CI. Documentar o uso efetivo, não presumido.

## Por que não usar como requisito obrigatório

- Projeto deve ser reproduzível sem plugin de terceiros no ambiente do avaliador.
- Hooks e dependências de ferramentas de desenvolvimento exigem avaliação de segurança.
- A redução de linhas, sozinha, não é uma métrica de qualidade.

## Alternativas consideradas

1. **Sem Ponytail:** menos dependências, mas simplicidade/review dependem integralmente de checklist manual.
2. **Copiar `AGENTS.md` do Ponytail sobre o projeto:** rejeitada; perderia regras específicas e prioridades de segurança.
3. **Aplicar Ponytail diretamente como componente runtime:** rejeitada; não traz valor ao atendimento e adiciona dependência incorreta.

## Consequências e salvaguardas

- Adoção **não bloqueia P0**, testes, demo ou entrega.
- Contratos de LLM Factory, autorização de pedidos, dados do snapshot e rastreabilidade não podem ser removidos para diminuir LOC.
- Review via Ponytail complementa e não substitui `ruff`, typing, pytest, security review e aceitação humana.
- Consultar `PONYTAIL_WORKFLOW.md` para instalação, invocação e critérios de risco.

## Critério de revisita

Se plugin/hook elevar risco, custo, ruído ou incompatibilidade com Codex/BMAD, desativá-lo e manter checklist manual; reavaliar após P0 estável.

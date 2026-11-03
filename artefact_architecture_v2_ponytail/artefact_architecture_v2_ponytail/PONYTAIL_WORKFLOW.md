# Ponytail — Workflow de Desenvolvimento (Codex + BMAD)

> **Status:** documentação de adoção proposta; **não indica que o plugin já tenha sido instalado ou executado**. Consultado na documentação pública do projeto em 2026-11-01. Verificar versão, disponibilidade e comandos no ambiente real.

## 1. Objetivo e limites

Ponytail orienta agentes de programação para **soluções simples, reutilização e revisão de alterações**. É ferramenta do **fluxo de desenvolvimento**, não componente da aplicação da loja, provider de LLM, MCP server, dependency Python ou requisito do desafio da Artefact.

**Responsabilidades:**

| Papel | Função | Não deve fazer |
|---|---|---|
| BMAD | refinar PRD, ADRs, backlog e acceptance criteria | substituir verificação funcional |
| Codex | implementar histórias, testes, documentação e commits reais | afirmar testes não executados |
| Ponytail | reforçar simplicidade, reuso e revisar diff / dívida | remover boundary, auth ou teste por redução de LOC |
| Desenvolvedor | aprovar decisões, avaliar riscos, validar qualidade e submissão | confiar cegamente em saída de agentes |

## 2. Instalação opcional no Codex

Fonte oficial: https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md

A documentação do projeto apresenta os comandos abaixo no terminal onde o Codex CLI está disponível:

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

Depois, abrir `codex`, inspecionar `/hooks`, **revisar e confiar apenas nos hooks aceitos conscientemente** e iniciar nova sessão. Para o aplicativo desktop Codex, a documentação recomenda reiniciar após a instalação. Alguns ambientes/versões podem não oferecer `codex plugin`; nesse caso, **não inventar um procedimento**: consultar a documentação atual do host e usar o fallback de revisão manual.

**Segurança:** a instalação habilita componentes de terceiros; inspecionar a proveniência, dependências, código dos hooks e permissões antes de ativar. Segundo o documento de instalação, os hooks utilizam Node.js disponível no PATH; ausência do Node pode comprometer a execução dos hooks. Nunca conceder acesso a segredos/produtos reais sem necessidade.

## 3. Modos e recursos

O repositório documenta modos `lite`, `full`, `ultra` e `off`; começar com **full**, reduzindo para lite ou desligando caso o conjunto de orientações atrapalhe o desenvolvimento do desafio.

O repositório documenta ações equivalentes a:

- `ponytail-review` — revisar diff/branch com foco em bugs, segurança, manutenção e testes;
- `ponytail-audit` — auditoria mais ampla de projeto;
- `ponytail-debt` — inventariar dívida técnica/simplificações adiadas;
- `ponytail-gain` — consultar números atribuídos ao benchmark da ferramenta, **não métricas deste projeto**.

**Observação sobre host:** no Codex CLI/IDE essas ações podem aparecer como *skills* com namespace, por exemplo `$ponytail:ponytail-review`, enquanto outros hosts usam comandos `/ponytail-review`. Verificar descoberta de skills no Codex instalado e não presumir que as duas formas sejam intercambiáveis.

## 4. Regras de convivência com AGENTS.md

**NÃO copiar** o `AGENTS.md` do repositório Ponytail para cima do `AGENTS.md` deste projeto. Manter instruções locais do produto como fonte prioritária; a instalação via plugin evita substituir regras próprias.

Hierarquia em conflitos:
1. Enunciado Artefact e políticas/dados como fontes do domínio.
2. Segurança, privacidade e comportamento do produto.
3. Contratos/ADRs de LLM Factory, ports/adapters, RAG e autorização.
4. Acceptance criteria do BMAD + testes.
5. Orientações de simplificação do Ponytail.

Exemplos: não remover `LLMPort` porque o primeiro MVP só usa um provedor; não expor pedidos via MCP sem auth; não remover validação `Decimal` ou bloqueio de variantes do market price porque aumentam LOC.

## 5. Rotina por história

1. Ler a story refinada (escopo, entradas/saídas, testes, riscos).
2. Codex inspeciona código e procura reuso, evitando abstrações especulativas.
3. Codex implementa alteração mínima e testes focados.
4. Executar `ruff`, typing e `pytest` relevantes; registrar saída efetiva.
5. Se disponível, usar Ponytail para revisão do diff. Listar findings por severidade, comportamentos afetados e testes adicionais.
6. Aceitar/rejeitar sugestões com justificativa; testar novamente após refatorar.
7. Atualizar README/ADR se uma decisão ou contrato mudou; fazer commit incremental real.
8. Se o plugin não estiver disponível, repetir checklist de review manualmente e seguir.

**Checklist de review obrigatório (com ou sem plugin):** autorização, logs/PII, injection, valores monetários, tool schema, timeout e custo LLM, retrieval/grounding, isolamento do provider e canais, comportamento sob falhas, consistência de testes.

## 6. Registro de evidências (modelo)

```text
Story: ST-0XX
Ponytail: instalado e usado / indisponível / dispensado
Scope / diff: ...
Sugestões aceitas: ...
Sugestões rejeitadas + por quê: ...
Comandos e resultados reais: ruff ..., mypy/pyright ..., pytest ...
Checks não executados e motivos: ...
Riscos remanescentes: ...
Commit: <hash real, após commit>
```

No README final, declarar **quais ferramentas foram de fato utilizadas**, o que foi revisado manualmente, e limitações. Nenhum número de economia de tokens, tempo ou LOC deve ser apresentado como resultado sem coleta real e baseline comparável.

## 7. Fontes e validade

- Repositório oficial: https://github.com/DietrichGebert/ponytail
- Guia de instalação: https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md
- Comandos e hospedagem: README do repositório acima.

Instruções de ferramentas evoluem; confirmar os detalhes imediatamente antes da instalação em cada ambiente.

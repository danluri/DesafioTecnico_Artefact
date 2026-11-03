# PRD — Requisitos de Produto e Critérios de Aceite

## Usuários e jornadas

**Cliente:** deseja consultar instrumentos e preços, conhecer a loja, pedir informações sobre um pedido e compreender políticas. **Avaliador:** precisa clonar, executar e verificar o protótipo. **Desenvolvedor:** precisa trocar o LLM, testar e evoluir sem alterar regras de negócio.

### Histórias funcionais (P0)

| ID | História | Critério de aceite verificável |
|---|---|---|
| FR-01 | Como cliente, quero conhecer endereço e horários. | Resposta usa política, informa segunda–sexta 9–18h e sábado 9–13h, não inventa alteração especial. |
| FR-02 | Quero buscar produtos por categoria, orçamento e estoque. | Busca SQL limitada; retorna apenas `status=active AND stock_quantity>0` como disponíveis; resultado é ordenado e paginado. |
| FR-03 | Quero consultar produto e preço específico. | Valor vem do repositório, exibe moeda BRL; itens inexistentes não são inventados. |
| FR-04 | Quero conhecer promoções do produto. | Aplica somente `is_active=1` do snapshot e valida disponibilidade; comunica preço original, desconto percentual e preço promocional. |
| FR-05 | Quero calcular PIX ou parcelas. | Serviço `Decimal` aplica regras do manual; não acumula PIX sobre produto promocional; resolve ambiguidade de parcela mínima em política/documentação. |
| FR-06 | Quero saber o status de meu pedido. | Exige identidade autorizada no contexto; `order_id` sozinho não concede leitura. Não promete rastreamento ao vivo se há apenas código do snapshot. |
| FR-07 | Quero conhecer troca, devolução e garantia. | Recupera seção/page; distingue arrependimento, troca e garantia legal; se faltam dados essenciais, pergunta. |
| FR-08 | Quero falar de forma natural e continuar a conversa. | Mantém contexto por sessão e suporta follow-up `E no PIX?` após produto previamente identificado. |
| FR-09 | Quero que o agente entenda suas limitações. | Fora do escopo, indisponibilidade da ferramenta ou desconhecimento levam a resposta honesta, sem invenção. |
| FR-10 | Como desenvolvedor, quero alternar LLM. | `LLM_PROVIDER` seleciona adaptador pela Factory; mesmos casos de uso e contratos, com validação das capacidades necessárias. |

### Histórias complementares (P1)

| ID | História | Critério de aceite verificável |
|---|---|---|
| FR-11 | Atendimento por WhatsApp. | Payload de webhook validado e normalizado por adapter, idempotência por ID da mensagem; envio real atrás de configuração. |
| FR-12 | Comparação com mercado. | Retorna preço oficial separado de referências, data, links e amostragem; erro externo não bloqueia atendimento. |
| FR-13 | Reutilização via MCP. | Ferramentas MCP chamam serviços de domínio existentes e aplicam mesmos controles de autorização. |
| FR-14 | Busca semântica de produtos. | Só se avaliação comprovar ganho sobre busca textual/estruturada. |

## Critérios não funcionais

- **Segurança:** sem dados de clientes em logs; validação de entradas; minimização de PII; segregação de pedidos por identidade; sem acesso SQL arbitrário do LLM.
- **Confiabilidade:** timeouts, budget de tool calls e fallback; idempotência de mensagens de canal; toda informação dinâmica vinculada à fonte.
- **Reprodutibilidade:** `uv sync` ou `pip install -e .`, `pytest`, `ruff`; documentação de comandos efetivamente testados após implementação.
- **Portabilidade:** SQLite e modelo fake para testes sem rede; segredo exclusivamente por ambiente.
- **Observabilidade:** request/session correlation IDs, latency de tools, resultado sucesso/falha, sem texto sensível por padrão.
- **Custo:** limites de tokens/tentativas/tool calls; search externo opcional e cache TTL.
- **Usabilidade:** português BR, voz informal-profissional, respostas claras, sem expor o manual como documento interno completo.

## Fluxos de produto importantes

### Catálogo e preço
1. Extrair filtros do pedido.
2. Chamar ferramenta com argumentos validados.
3. Se não houver resultados, informar e sugerir alternativas de estoque real.
4. Exibir preço como valor do snapshot do desafio, não preço atualizado de um ERP.

### Devolução
1. Identificar compra online ou presencial, motivo, data de recebimento/compra e estado do produto quando relevantes.
2. Recuperar seções 4.1/4.2/4.3 e 8.1 conforme intenção.
3. Não tratar garantia legal de 90 dias como extinta após janela de troca interna de 30 dias.
4. Havendo conflito/ambiguidade, indicar canal de atendimento responsável.

### Consulta de pedido
1. Identificar pedido e identidade autenticada **no lado do servidor**; telefone passado em texto na conversa não autentica sozinho.
2. Verificar `order.customer_id == principal.customer_id` ou uma credencial de validação segura.
3. Só então expor status, itens e dados de rastreamento necessários.
4. No protótipo local, permitir sessão simulada explicitamente identificada como demo e nunca tratá-la como autenticação real.

### Market comparison
1. Identificar produto exato; buscar observações de cache válidas.
2. Se permitido/configurado e cache expirou, buscar web via API autorizada.
3. Rejeitar variantes/outliers/itens usados não equivalentes; mostrar fontes e contagem.
4. Se há <3 ofertas independentes, não afirmar 'média de mercado confiável'.

## Regras do manual que precisam ser preservadas

- PIX: 5% no preço de tabela, **não** sobre promocionais (§3, §6.2).
- Crédito: até 12x sem juros; faixas 1–3x, 4–6x, 7–12x e seus mínimos (§3.1).
- Arrependimento online: até 7 dias **após recebimento**, conforme manual (§4.1).
- Frete local: grátis para pedidos **acima** de R$500; abaixo de R$500, R$35. O caso **exatamente R$500** não fica explicitamente coberto e exige suposição documentada (§5.1).
- Promoções ativas são registradas nos CSVs; campanhas sazonais descritivas não garantem promoção vigente (§6).
- Horário 9–18h dias úteis; 9–13h sábado; domingos e feriados fechado (§2).

## Ambiguidades a documentar — não ocultar

1. WhatsApp: §1.2 indica `(67) 3341-4444`; §7 indica `(67) 3321-4500`; para canal remoto utilizar §7 como referência operacional **com nota de divergência e confirmação pendente**.
2. E-mail aparece sem acento na capa e com acento na tabela §1.2; preferir endereço da capa sem acento por prudência, registrar divergência.
3. Parcela mínima até 3x: §3.1 diz `sem valor mínimo de parcela (exceto abaixo de R$50,00)`. Assumir provisoriamente mínimo R$50 em 1–3x, identificar interpretação no README.
4. `is_active` de promoção não informa período; significa 'ativa no snapshot', **não vigência garantida hoje**.
5. Garantia legal de 90 dias (§8.1) versus fluxo de troca de 30 dias (§4.2): distinguir direitos, não negar reivindicações de garantia.

## Critérios de engenharia assistida por IA (processo, não requisito do produto)

- **ENG-01:** BMAD refina histórias e critérios verificáveis; Codex implementa em commits incrementais reais; Ponytail, quando instalado, aconselha simplicidade, reutilização e code review — **não** integra o runtime de atendimento.
- **ENG-02:** usar Ponytail não dispensa lint, typing, pytest, testes adversariais, autorização e revisão humana. Segurança, privacidade, correção comercial e compromissos arquiteturais têm precedência sobre redução de linhas.
- **ENG-03:** README final declara ferramentas de IA efetivamente utilizadas, versões/modos se conhecidos, como foram usadas, verificações executadas e limites. Não afirmar uso de plugin, benchmark ou economia de tokens sem evidência.
- **ENG-04:** mudanças sugeridas por Ponytail que afetem ports/adapters, contratos ou comportamentos precisam passar por testes de regressão e, se relevantes, atualização de ADR.

A instalação do Ponytail é **opcional e não bloqueia o aceite de P0**.

## Entregáveis oficiais da Artefact

- Repositório público com commits progressivos reais, sem mudanças após prazo.
- README com setup, modelo, arquitetura/retrieval, prompt, limitações, uso de IA.
- Três a cinco exemplos de conversas reais, ao menos um não trivial.
- Resposta ao e-mail original com URL pública. Prazo exato consta do e-mail, não do PDF.

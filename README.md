# Empório da Música — Agente de Atendimento

Protótipo em Python de um agente de atendimento por mensagens de texto para a Empório da Música, uma loja fictícia de instrumentos musicais em Campo Grande/MS. O agente conversa no tom da loja e escolhe, a cada mensagem, se precisa **consultar dados** (catálogo, preços, estoque, promoções, pedidos) ou **consultar políticas** (horários, endereço, trocas, frete, pagamento, garantia). Ele também recusa com educação pedidos fora do escopo, como acessórios.

- [Como rodar](#como-rodar)
- [Decisões técnicas](#decisões-técnicas)
- [Suposições sobre o enunciado e o manual](#suposições-sobre-o-enunciado-e-o-manual)
- [Exemplos de interação](#exemplos-de-interação)
- [Limitações conhecidas e próximos passos](#limitações-conhecidas-e-próximos-passos)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)
- [Referência: observabilidade, Docker e simulações](#referência-observabilidade-docker-e-simulações)

---

## Como rodar

### 1. Pré-requisitos

| Item | Observação |
|---|---|
| Python 3.13+ | linguagem principal |
| [uv](https://docs.astral.sh/uv/) | gerencia o ambiente virtual e as dependências |
| [Ollama](https://ollama.com/) | provedor do LLM local; necessário para conversar com o agente de verdade |
| Dados do desafio | a pasta `data/` entregue pela Artefact (CSVs + `políticas_da_loja.pdf`) |

Os dados do desafio **não estão versionados**: o manual se identifica como "documento interno", e os CSVs contêm dados pessoais fictícios de clientes. Mantenha a pasta onde preferir e aponte para ela com a variável `$dados` abaixo.

### 2. Instalação

```powershell
git clone https://github.com/danluri/DesafioTecnico_Artefact.git
cd DesafioTecnico_Artefact
uv sync

ollama pull llama3.1
```

No Windows, use `$env:PYTHONIOENCODING = "utf-8"` para os acentos aparecerem corretamente no terminal.

### 3. Importar o catálogo (CSV → SQLite)

O agente não lê os CSVs a cada pergunta. Eles são importados uma vez para um snapshot SQLite, e as ferramentas consultam esse snapshot.

```powershell
$dados = "C:\caminho\para\Desafio Técnico AI Engineer 2026\data"
$env:PYTHONPATH = "src"
New-Item -ItemType Directory -Force data | Out-Null

uv run python -m emporio.cli --catalog-db data/catalog.db --catalog-action search --category "Violões" --maximum-budget 1000 `
  --products-csv   "$dados\desafio_tecnico_ai_eng - products.csv" `
  --categories-csv "$dados\desafio_tecnico_ai_eng - categories.csv" `
  --promotions-csv "$dados\desafio_tecnico_ai_eng - promotions.csv" `
  --customers-csv  "$dados\desafio_tecnico_ai_eng - customers.csv" `
  --orders-csv     "$dados\desafio_tecnico_ai_eng - orders.csv" `
  --order-items-csv "$dados\desafio_tecnico_ai_eng - order_items.csv"
```

A saída já mostra os violões até R$ 1.000 do snapshot (12 resultados). Depois disso, a CLI consulta a base sem precisar dos CSVs:

```powershell
uv run python -m emporio.cli --catalog-db data/catalog.db --catalog-action detail --product "Takamine GD20 Dreadnought Natural"
uv run python -m emporio.cli --policy-source "$dados\políticas_da_loja.pdf" --query "Qual o endereço da loja?"
```

### 4. Conversar com o agente (console local + Llama)

```powershell
$env:PYTHONPATH = "src"
$env:EMPORIO_LLM_PROVIDER = "local-llama"
$env:EMPORIO_LLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:EMPORIO_LLAMA_MODEL = "llama3.1:latest"
$env:EMPORIO_LLAMA_TIMEOUT = "180"
$env:EMPORIO_LLAMA_MAX_TOKENS = "512"
$env:EMPORIO_CATALOG_DB_PATH = "$PWD\data\catalog.db"
$env:EMPORIO_POLICY_SOURCE = "$dados\políticas_da_loja.pdf"
$env:EMPORIO_DEV_CONSOLE_ENABLED = "true"
$env:EMPORIO_DEV_CONSOLE_PORT = "8080"

uv run python -m emporio.runtime --dev-console
```

Abra http://127.0.0.1:8080 e envie mensagens. O console mostra a resposta, uma tabela de produtos montada a partir do resultado da ferramenta (e não do texto do LLM) e a linha do tempo de rastreamento de cada mensagem. A mesma conversa pode ser feita pela API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/messages -ContentType "application/json; charset=utf-8" `
  -Body '{"text": "Quanto custa o Takamine GD20?", "message_id": "m-001"}'
```

Para continuar a mesma conversa, reenvie o `session_id` devolvido na resposta.

> **Latência:** com inferência local em CPU/GPU modesta, a primeira chamada (modelo "frio") levou cerca de 170 s. Com o modelo já carregado, as respostas levaram de 40 s a 70 s. Veja [`DIAGNOSTICO_RUNTIME.md`](DIAGNOSTICO_RUNTIME.md).

**Sem Ollama:** o provedor padrão (`EMPORIO_LLM_PROVIDER=fake`) é um LLM falso e determinístico. Ele serve para os testes e para subir a aplicação offline, mas **não conversa** e responde a maioria das mensagens com uma falha controlada. Para avaliar o agente, use o Ollama.

### 5. Testes

```powershell
uv run --with pytest pytest -q
uv run --with ruff ruff check src tests
```

Os testes rodam 100% offline, com o `FakeLLM` e fixtures sintéticas, sem precisar do Ollama nem dos dados do desafio.

---

## Decisões técnicas

### Abordagem: function calling com orquestração própria (sem framework de agente)

O agente é um laço de *tool calling* limitado, implementado em `ConversationService`:

1. **Roteamento** (`query_routing.py` e `policy_runtime.py`) identifica os tópicos da mensagem (política, produto, pagamento, pedido) e decide quais ferramentas oferecer ao modelo e quais trechos do manual recuperar. Quando a intenção é clara (por exemplo, "pagamento do SN-100"), o plano de ferramentas é montado antes do LLM, que só redige a resposta final.
2. **Ferramentas** somente leitura, em uma lista permitida (`tools.py`): `search_catalog`, `calculate_payment`, `order_status` e `answer_policy`. Os argumentos são validados contra schema, e o número de rodadas é limitado.
3. **Validação determinística da saída:** valores de cotação e planos de parcelamento citados pelo LLM são conferidos contra o resultado da calculadora, e há guardas para condições de política conhecidas (por exemplo, recolocar "compras online" se o modelo omitir essa condição no direito de arrependimento). Se o provedor falha ou estoura o tempo, a resposta usa apenas os fatos verificados e é marcada como `partial`.

**Por que não LangChain/LlamaIndex/LangGraph:** o domínio é pequeno (seis tabelas e um PDF de oito páginas), e o que mais importa aqui é **controle**: quais ferramentas existem, quantas rodadas são permitidas, o que é registrado e quais números chegam ao cliente. Um laço próprio (`conversation.py`, cerca de 340 linhas) torna esse controle explícito e testável sem depender da API de um framework.

**Troca de provedor (padrão Factory + Port):** o resto do sistema conhece apenas a interface `LLMPort` (`llm.py`). `LLMFactory` é um factory baseado em registro: `create()` escolhe o construtor pela variável `EMPORIO_LLM_PROVIDER` (`fake` → `FakeLLM`; `local-llama` → `LocalLlamaLLM`, com import tardio), e provedores novos entram com `LLMFactory.register(nome, construtor)`, sem editar o factory. Cada adaptador declara o que suporta em `capabilities` (por exemplo, `tool_calling`), e o orquestrador decide com base nessa declaração, nunca no nome do provedor. Por fim, `PolicyGroundedLLM` envolve qualquer provedor (padrão Decorator) para injetar as evidências do manual e aplicar as validações.

### Modelo e provedor: Llama 3.1 8B via Ollama (local)

- **Custo zero e sem chave de API:** quem avalia consegue rodar sem conta em provedor pago, e nenhum dado do desafio sai da máquina.
- **Desvantagem assumida:** um modelo de 8B local erra mais e é lento. Por isso a arquitetura **não confia no LLM para números**: preços, estoque, parcelas, PIX e frete são calculados por serviços determinísticos com `Decimal`, e o LLM só os redige. Essa escolha foi o que tornou viável um modelo pequeno.
- **Outro modelo no Ollama** (por exemplo, `qwen2.5`): basta trocar `EMPORIO_LLAMA_MODEL`. O `LocalLlamaLLM` declara `tool_calling` para modelos `llama3.1*` (validados com ferramentas); para outros modelos com suporte a ferramentas, defina `EMPORIO_LLAMA_ENABLE_TOOLS=true`.
- **Outro provedor** (Claude, GPT etc.): criar uma classe que implemente `LLMPort.complete()`, declarar suas `capabilities` e chamar `LLMFactory.register("nome", Classe)`. O factory, o orquestrador, as ferramentas e as validações não mudam.

### Arquitetura de retrieval

| Fonte | Estratégia | Motivo |
|---|---|---|
| CSVs (catálogo, promoções, pedidos) | Importação para **SQLite** e consultas **parametrizadas** por ferramentas | São dados estruturados: filtros exatos (categoria, orçamento, estoque) funcionam melhor com SQL do que com busca vetorial, e evitam que o LLM "invente" um produto. Não há agente de SQL livre (nenhum SQL gerado pelo modelo). |
| `políticas_da_loja.pdf` | **RAG lexical** sobre trechos por página, com fonte e página; busca **semântica opcional** com embeddings locais (`embeddinggemma`) | Com 8 páginas, a busca lexical normalizada (acentos, sinônimos como CEP/endereço) já recupera o trecho certo de forma reproduzível e sem dependências. A busca semântica fica disponível para perguntas parafraseadas e volta para a lexical se falhar. |

### Estratégia de prompt

- **Prompt de sistema condensado:** contém a persona do manual (seção 7.1, "informal mas profissional, como um amigo que entende de música"), a regra "nunca informar preço, estoque ou prazo sem consultar o sistema", o escopo restrito a instrumentos musicais e as regras de privacidade.
- **Contexto mínimo por turno:** só os trechos recuperados do manual e o resultado compacto das ferramentas (ID, nome, preço, estoque, data do snapshot). O histórico não relacionado é cortado. Isso foi necessário porque o Ollama truncava a entrada acima de cerca de 2.000 tokens (detalhes em `DIAGNOSTICO_RUNTIME.md`).
- **Sem evidência, sem resposta:** quando a recuperação não encontra base, o agente orienta a confirmação com a equipe em vez de improvisar uma regra.

### Persistência do histórico

Sessões de conversa ficam em SQLite com expiração. Isso permite perguntas de acompanhamento ("e no PIX?", "e em 6x?") sem repetir o produto. A identidade do cliente para consultar pedidos vem do servidor, nunca do texto da mensagem: informar só um número de pedido não basta para ver dados de outra pessoa.

### Interface

Um console HTTP local (`dev_console.py`, apenas biblioteca padrão) com uma página de chat e o endpoint `POST /api/messages`. Foi escolhido em vez de uma CLI pura para exibir, ao lado da resposta, a tabela de produtos e o rastreamento de cada etapa (roteamento, ferramentas, trechos recuperados, latência). Isso ajuda a avaliar *por que* o agente respondeu o que respondeu. É uma interface de desenvolvimento, sem autenticação de produção.

### Tratamento dos dados

- A importação dos CSVs é **atômica**: um snapshot só substitui o anterior se todas as tabelas forem válidas.
- Valores monetários em `Decimal`, status de produto (`active`, `discontinued`, `coming_soon`) validados, e especificações JSON dos produtos interpretadas.
- Toda resposta de catálogo informa a **data do snapshot** e que não é estoque em tempo real.
- Logs e traces registram identificadores, durações e origem das evidências, **sem** mensagens completas, prompts ou dados pessoais.

---

## Suposições sobre o enunciado e o manual

O manual tem ambiguidades e divergências. As decisões adotadas:

| Ponto | Decisão |
|---|---|
| Frete de exatamente R$ 500,00 em Campo Grande (o manual diz "acima de" e "abaixo de") | Cobra R$ 35,00 até R$ 500,00, inclusive; frete grátis só acima disso. |
| Dois números de WhatsApp: (67) 3341-4444 (seção 1.2) e (67) 3321-4500 (seção 7) | Não há regra para escolher um deles: o agente responde com base no trecho recuperado. A divergência fica registrada aqui para a loja corrigir o manual. |
| E-mail com acento no domínio na seção 1.2 (`contato@empóriodamusica.com.br`) e sem acento na capa (`contato@emporiodamusica.com.br`) | Provável erro de digitação no manual (domínios com acento são incomuns); registrado como divergência, sem tratamento específico no código. |
| Parcela mínima: a tabela fala em R$ 100,00, mas a seção 3.1 define faixas (≤3x, 4–6x com R$ 80, 7–12x com R$ 100) | Usa as faixas da seção 3.1, que são mais específicas. |
| Direito de arrependimento vale para compras **online** | O agente sempre explicita essa condição e pede pedido e data de recebimento para análise. |
| "Consultar dados em tempo real" | Os CSVs são tratados como o "sistema" da loja, mas como snapshot importado; o agente sempre informa a data do snapshot. |

---

## Exemplos de interação

As conversas registradas estão em [`docs/exemplos-atendimento.md`](docs/exemplos-atendimento.md).

---

## Limitações conhecidas e próximos passos

**Limitações**

- **Latência e qualidade do modelo local:** de 40 s a 70 s por resposta com o modelo carregado, e cerca de 170 s na primeira chamada. Em um teste, o modelo descreveu um item de R$ 999,00 como "acima de R$ 1.000", embora a ferramenta tivesse filtrado corretamente. As validações cobrem preços e condições conhecidas, não todo comentário livre do modelo.
- **Estoque é snapshot,** não integração em tempo real.
- **Políticas do manual ainda não automatizadas:**
  - sugestão automática de alternativas quando o produto está sem estoque (seção 7.3);
  - mensagem dedicada a produto descontinuado, com sucessores (seção 7.3);
  - aviso de horário de retorno fora do expediente (seção 7.1).
- **Frete fora de Campo Grande** é simulado: o snapshot não tem peso nem dimensões, então o agente pede esses dados em vez de cotar.
- **Perguntas que misturam vários assuntos** de política podem recuperar trechos insuficientes.
- WhatsApp e Correios funcionam apenas com simuladores; nenhuma mensagem ou cobrança real é feita.

A lista técnica detalhada está em [`_bmad-output/implementation-artifacts/deferred-work.md`](_bmad-output/implementation-artifacts/deferred-work.md).

**Com mais tempo**

1. Testar um modelo maior via API (ou um modelo local com GPU) e comparar qualidade e latência com um conjunto fixo de perguntas de avaliação.
2. Criar uma suíte de avaliação ponta a ponta (perguntas e respostas esperadas, com LLM-as-judge e checagens determinísticas) rodando a cada mudança de prompt.
3. Implementar as três políticas da seção 7 listadas acima.
4. Integrar estoque em tempo real e o canal de WhatsApp real com credenciais da loja.
5. Fazer streaming de resposta no console para reduzir a latência percebida.

---

## Uso de assistentes de código

O projeto foi construído com assistentes de IA dentro de um fluxo de especificação antes do código:

- **BMAD Method** (pastas `.agents/`, `_bmad/` e `_bmad-output/`): fluxo com agentes por papel (analista, arquiteto, PM, desenvolvedor, revisor). A partir do enunciado e do manual, gerou o PRD, a arquitetura, os épicos e uma especificação por história (`_bmad-output/implementation-artifacts/spec-*.md`). Cada artefato passou por revisões adversariais e de edge cases (`review-*.md`) antes da implementação. O que ficou fora do escopo foi registrado em `deferred-work.md`, em vez de ser descartado.
- **Codex:** apoio à leitura dos documentos, à implementação história por história, à depuração (o `DIAGNOSTICO_RUNTIME.md` registra uma dessas investigações com medições reais) e aos testes.
- **Claude Code:** revisão final do que faltava para a entrega frente ao enunciado e ao manual, e reorganização deste README e dos exemplos.

As decisões de negócio e de escopo foram tomadas por mim. O código gerado foi revisado e coberto por testes automatizados, além de testes manuais no console com o modelo real. Os commits seguem a progressão das histórias.

---

## Referência: observabilidade, Docker e simulações

### Observabilidade

Cada resposta da API inclui `trace_id` e `trace`, com duração por etapa, tokens, origem das políticas, data do snapshot, erros e estado da persistência. Nada disso guarda a mensagem completa nem o prompt.

| Endpoint | Conteúdo |
|---|---|
| `GET /health` | saúde do console |
| `GET /api/traces` | resumos dos traces recentes |
| `GET /api/traces/<trace_id>` | timeline sanitizada completa |
| `GET /api/metrics` | métricas de resultado e latência |

Variáveis: `EMPORIO_TRACE_ENABLED` (padrão `true`), `EMPORIO_TRACE_DB` (`data/observability.db`), `EMPORIO_TRACE_RETENTION_DAYS` (`7`) e `EMPORIO_RUNTIME_LOG` (`data/emporio-runtime.log`).

### Busca semântica opcional nas políticas

```powershell
ollama pull embeddinggemma
$env:EMPORIO_POLICY_SEMANTIC_ENABLED = "true"
$env:EMPORIO_POLICY_EMBEDDING_BASE_URL = "http://127.0.0.1:11434"
$env:EMPORIO_POLICY_EMBEDDING_MODEL = "embeddinggemma"
$env:EMPORIO_POLICY_VECTOR_INDEX = "data/policy-index.json"
```

### Docker

```powershell
docker compose up --build
```

Isso sobe o runtime com o `FakeLLM`, inicializa o SQLite no volume `emporio-data` e executa uma verificação de prontidão. Para o console com os dados do desafio e o Ollama do host:

```powershell
docker compose build
docker compose run --rm -v "${dados}:/sources:ro" emporio python -m emporio.cli --catalog-db /data/catalog.db --catalog-action search --category "Violões" --products-csv "/sources/desafio_tecnico_ai_eng - products.csv" --categories-csv "/sources/desafio_tecnico_ai_eng - categories.csv" --promotions-csv "/sources/desafio_tecnico_ai_eng - promotions.csv" --customers-csv "/sources/desafio_tecnico_ai_eng - customers.csv" --orders-csv "/sources/desafio_tecnico_ai_eng - orders.csv" --order-items-csv "/sources/desafio_tecnico_ai_eng - order_items.csv"

docker compose run --rm -p 127.0.0.1:8080:8080 -v "${dados}:/sources:ro" `
  -e EMPORIO_DEV_CONSOLE_ENABLED=true -e EMPORIO_DEV_CONSOLE_PORT=8080 -e EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND=true `
  -e EMPORIO_CATALOG_DB_PATH=/data/catalog.db -e "EMPORIO_POLICY_SOURCE=/sources/políticas_da_loja.pdf" `
  -e EMPORIO_LLM_PROVIDER=local-llama -e EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434 `
  -e EMPORIO_LLAMA_MODEL=llama3.1:latest -e EMPORIO_LLAMA_TIMEOUT=180 `
  emporio python -m emporio.runtime --dev-console
```

O mapeamento `127.0.0.1:8080:8080` restringe o acesso ao computador local. A flag `ALLOW_CONTAINER_BIND` serve apenas para desenvolvimento.

### Pedido fictício e rastreio (simulação)

Os CSVs não vinculam um cliente autenticado à conversa. Para demonstrar a consulta de status de pedido com segurança, o console tem um painel de simulação, desligado por padrão e bloqueado em produção:

```powershell
$env:EMPORIO_DEV_ORDER_SIMULATION_ENABLED = "true"
$env:EMPORIO_DEV_ORDER_DB = "$PWD\data\dev-orders.db"
```

1. No painel **Pedido de teste**, clique em **Iniciar novo cliente de teste**. A sessão é vinculada a esse cliente.
2. Consulte um produto no chat, copie o **ID** da tabela e clique em **Criar pedido fictício**. O pedido recebe uma referência como `SIM-000001`.
3. Use **Simular aprovação do pagamento** e depois **Simular despacho e gerar rastreio**.
4. Pergunte no chat: `Qual o rastreio do pedido SIM-000001?`

A ferramenta `order_status` usa a identidade estabelecida pelo servidor (cabeçalho `X-Emporio-Simulation-Token`), e não a identidade informada na mensagem. Nenhuma cobrança, despacho, chamada aos Correios ou mensagem de WhatsApp real é feita. Reclamações e devoluções de teste também podem ser registradas pelo painel (prazo de retorno da seção 7.3).

### Simuladores de integrações

`MockCorreiosTracking` e `MockWhatsAppChannel` (`emporio.simulators`) geram resultados determinísticos. Integrações reais existem como extensões opcionais (`EMPORIO_CORREIOS_*`, `EMPORIO_WHATSAPP_*`), com credenciais apenas por variável de ambiente, e não foram certificadas com provedores reais.

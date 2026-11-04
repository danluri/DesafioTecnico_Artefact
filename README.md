# Emporio da Musica

Assistente local para atendimento de uma loja de instrumentos musicais. O projeto combina politicas da loja, catalogo de produtos, pagamentos, pedidos, rastreamento e observabilidade.

## Decisões e uso de IA

O projeto usa Python e componentes próprios, sem framework de agentes: uma interface `LLMPort` permite trocar o provedor, enquanto o `ConversationService` limita rodadas e executa ferramentas por uma lista permitida. SQLite guarda sessões e snapshots, com consultas parametrizadas para preço, estoque e pedidos. Políticas são consultadas por recuperação lexical de trechos do PDF com página e fonte; opcionalmente, embeddings locais fazem busca semântica. A LLM recebe o contexto recuperado e orientações de persona, precisão e privacidade. Os cálculos monetários ficam em serviços determinísticos com `Decimal`, evitando confiar na geração de texto para definir valores.

O Ollama com Llama foi escolhido para testar localmente sem chave de API; `FakeLLM` permite verificações offline reproduzíveis. As decisões trocam atualizações operacionais em tempo real por um snapshot importado e exigem atenção ao tempo de inferência local. O console HTTP é uma interface de desenvolvimento, não uma aplicação autenticada de produção.

Foi usado o Codex como assistente de código para apoiar a leitura dos documentos, implementação, depuração, testes e documentação. As decisões de negócio e aprovação do escopo foram discutidas com o responsável pelo projeto; testes automatizados e verificações manuais complementam a revisão do código gerado.

As conversas e consultas registradas para avaliação estão em [exemplos de atendimento](docs/exemplos-atendimento.md). Antes da entrega, registre novas conversas reais do console se desejar demonstrar o modelo local e revise os arquivos que serão publicados: o manual se identifica como documento interno, e os dados operacionais podem conter dados pessoais.

## Limitações e evolução

O estoque é um snapshot, não uma integração em tempo real. Valores e prazos externos de frete são simulações e não substituem uma cotação. WhatsApp e Correios operam em modo simulado por padrão; pagamentos e despachos de teste não são reais. As regras de horário e prazo máximo de atendimento ainda não são garantidas automaticamente. Regras de devolução dependem de dados e análise de elegibilidade. A resposta da LLM pode falhar ou demorar, e a consulta RAG deve ser conferida para perguntas que combinem vários assuntos. Futuras melhorias incluem integrar canais e transportadoras mediante credenciais, imagens dos produtos, análise de reclamações e monitoramento dos prazos. Limitações específicas e pendências de implementação estão em `_bmad-output/implementation-artifacts/deferred-work.md`.

O manual deixa em aberto o frete de exatamente R$ 500,00; a decisão adotada para Campo Grande é cobrar R$ 35,00 até R$ 500,00, inclusive, e oferecer frete grátis somente acima desse valor. O manual também apresenta números diferentes para WhatsApp e inconsistência nas regras gerais de parcela mínima; a aplicação deve pedir confirmação quando não houver evidência suficiente.

## Visao geral

O console de desenvolvimento mostra a resposta do assistente e uma tabela de produtos com modelo, preco em BRL e quantidade em estoque. Os valores vem diretamente do resultado da ferramenta de catalogo, e nao da interpretacao do texto do LLM. A tabela tambem mostra a quantidade de resultados e a data do snapshot. O JSON bruto fica disponivel em uma secao de diagnostico expansivel.

Perguntas de clientes sao direcionadas para a recuperacao de politicas da loja (endereco, horario, contato, frete, trocas, garantia e privacidade) ou para ferramentas operacionais de catalogo (modelos, precos e estoque). Sem evidencia suficiente, o assistente orienta a confirmacao com a equipe da loja em vez de inventar uma regra.

## Rastreamento e observabilidade

O console possui a timeline Rastreamento desta mensagem e a area Historico e metricas, com traces recentes e estatisticas de latencia. As respostas da API incluem trace_id e trace. Os eventos registram duracoes, tokens, origem das politicas, snapshot do catalogo, erros e estado da persistencia, sem armazenar mensagens completas, prompts ou respostas geradas.

Padroes:

~~~text
EMPORIO_TRACE_ENABLED=true
EMPORIO_TRACE_DB=data/observability.db
EMPORIO_TRACE_RETENTION_DAYS=7
EMPORIO_RUNTIME_LOG=data/emporio-runtime.log
~~~

Endpoints locais:

- GET /api/traces: resumos dos traces recentes.
- GET /api/traces/<trace_id>: timeline sanitizada completa.
- GET /api/traces/by-message/<message_id>: consulta do trace sem guardar o ID bruto.
- GET /api/metrics: metricas de resultados e latencia.

## Politicas, catalogo e pagamentos

A aplicacao P0 offline usa SQLite e nao exige credenciais externas. A cobertura de politicas e deterministica e offline por padrao.

ShippingService aplica a regra de R$ 35/gratis de Campo Grande e retorna opcoes simuladas de Correios PAC/SEDEX e Jadlog nos demais casos. Dados incompletos ou pacotes acima do limite produzem resposta explicita, sem cotacao inventada.

PaymentService.calculate_combinations suporta PIX e cartao somente acima de R$ 2.000,00 e nunca acumula desconto de PIX com promocao. PostSaleService persiste reclamacoes autorizadas e nao retorna dados privados de referencias nao autorizadas.

## Provedores de LLM

O padrao e o FakeLLM, deterministico e offline. Para usar um endpoint local compativel com Llama/Ollama:

~~~text
EMPORIO_LLM_PROVIDER=local-llama
EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434
EMPORIO_LLAMA_MODEL=llama3.1:latest
EMPORIO_LLAMA_TIMEOUT=180
EMPORIO_LLAMA_MAX_TOKENS=512
EMPORIO_CATALOG_DB_PATH=data/catalog.db
~~~

Se o endpoint estiver indisponivel, a requisicao informa a limitacao do provedor. EMPORIO_LLM_PROVIDER=fake continua totalmente offline e deterministico.

## Recuperacao semantica opcional

O modo semantico local usa embeddings compativeis com Ollama e volta para a busca lexical quando necessario:

~~~text
EMPORIO_POLICY_SEMANTIC_ENABLED=true
EMPORIO_POLICY_EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMPORIO_POLICY_EMBEDDING_MODEL=embeddinggemma
EMPORIO_POLICY_EMBEDDING_TIMEOUT=10
EMPORIO_POLICY_VECTOR_INDEX=/data/policy-index.json
~~~

Instale o modelo com:

~~~text
ollama pull embeddinggemma
~~~

Para habilitar respostas fundamentadas nas politicas, configure:

~~~text
EMPORIO_POLICY_SOURCE=E:\\...\\data\\politicas_da_loja.pdf
~~~

Quando definida, cada turno recebe evidencias RAG limitadas e a ferramenta somente leitura answer_policy e registrada. Sem evidencia suficiente, o assistente pede confirmacao da equipe.

## Docker

Execute:

~~~text
docker compose up --build
~~~

O container P0 inicializa SQLite em /data/emporio.db, conecta os servicos principais, executa uma conversa de prontidao offline, informa READY e usa o volume nomeado emporio-data.

Para verificar volumes de forma isolada:

~~~powershell
$env:COMPOSE_PROJECT_NAME = "emporio-story-31-verify"
docker-compose -p $env:COMPOSE_PROJECT_NAME config
docker-compose -p $env:COMPOSE_PROJECT_NAME up --build -d
docker-compose -p $env:COMPOSE_PROJECT_NAME ps
~~~

Depois, limpe somente os recursos sinteticos:

~~~powershell
docker-compose -p $env:COMPOSE_PROJECT_NAME down -v
~~~

## Verificacao

O comando principal de verificacao offline e:

~~~text
uv run pytest -q
~~~

Verificacoes complementares:

~~~text
uv run --with ruff ruff check src tests
python -m compileall -q src tests
docker compose config
docker compose build
~~~

FakeLLM e o unico modo obrigatorio. local-llama, WhatsApp, MCP, comparacao de mercado e rastreamento live dos Correios sao extensoes opcionais.

## Console local de desenvolvimento

O console do navegador vem desativado. Para executa-lo fora do Docker com FakeLLM:

~~~powershell
$env:EMPORIO_DEV_CONSOLE_ENABLED = "true"
$env:EMPORIO_DEV_CONSOLE_PORT = "8080"
python -m emporio.runtime --dev-console
~~~

Abra http://127.0.0.1:8080. A pagina mantem o identificador da sessao, mostra resposta/provedor/resultado e permite observar a supressao de duplicatas. O endpoint e POST /api/messages; a saude e GET /health.

Para executar no Docker:

~~~powershell
docker compose run --rm -p 127.0.0.1:8080:8080 -e EMPORIO_DEV_CONSOLE_ENABLED=true -e EMPORIO_DEV_CONSOLE_PORT=8080 -e EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND=true emporio python -m emporio.runtime --dev-console
~~~

O exemplo acima inicia o console com FakeLLM e sem catálogo ou manual configurados. Para testar os dados do desafio dentro do volume Docker, primeiro construa a imagem e importe o snapshot a partir da pasta fornecida, na raiz do projeto:

```powershell
docker compose build
$dadosDesafio = (Resolve-Path '.\Desafio_Técnico_AI_Engineer_2026-20260616T150750Z-3-001\Desafio Técnico AI Engineer 2026\data').Path
docker compose run --rm -v "${dadosDesafio}:/sources:ro" emporio python -m emporio.cli --catalog-db /data/catalog.db --catalog-action search --category 'Violões' --products-csv '/sources/desafio_tecnico_ai_eng - products.csv' --categories-csv '/sources/desafio_tecnico_ai_eng - categories.csv' --promotions-csv '/sources/desafio_tecnico_ai_eng - promotions.csv' --customers-csv '/sources/desafio_tecnico_ai_eng - customers.csv' --orders-csv '/sources/desafio_tecnico_ai_eng - orders.csv' --order-items-csv '/sources/desafio_tecnico_ai_eng - order_items.csv'
```

Com o Ollama ativo no Windows e o modelo instalado, inicie o console com o manual montado somente para leitura:

```powershell
docker compose run --rm -p 127.0.0.1:8080:8080 -v "${dadosDesafio}:/sources:ro" -e EMPORIO_DEV_CONSOLE_ENABLED=true -e EMPORIO_DEV_CONSOLE_PORT=8080 -e EMPORIO_DEV_CONSOLE_ALLOW_CONTAINER_BIND=true -e EMPORIO_DEV_ORDER_SIMULATION_ENABLED=true -e EMPORIO_CATALOG_DB_PATH=/data/catalog.db -e 'EMPORIO_POLICY_SOURCE=/sources/políticas_da_loja.pdf' -e EMPORIO_LLM_PROVIDER=local-llama -e EMPORIO_LLAMA_BASE_URL=http://host.docker.internal:11434 -e EMPORIO_LLAMA_MODEL=llama3.1:latest -e EMPORIO_LLAMA_TIMEOUT=180 emporio python -m emporio.runtime --dev-console
```

O servidor precisa escutar nas interfaces do container para a porta publicada funcionar; o mapeamento `127.0.0.1:8080:8080` restringe o acesso pela porta ao computador local. A flag de bind deve ser usada somente em desenvolvimento.

O console nunca chama a Meta nem envia mensagens reais de WhatsApp.

### Criar pedido fictício e testar o rastreio

Com o catálogo já importado, mantenha a configuração atual da LLM e das políticas e habilite a simulação no PowerShell, na raiz do projeto:

```powershell
$env:EMPORIO_DEV_ORDER_SIMULATION_ENABLED = "true"
$env:EMPORIO_DEV_ORDER_DB = "$PWD\data\dev-orders.db"
# Aponte para a base que já contém os produtos importados:
$env:EMPORIO_CATALOG_DB_PATH = "$PWD\data\catalog.db"
$env:EMPORIO_DEV_CONSOLE_ENABLED = "true"
$env:EMPORIO_DEV_CONSOLE_PORT = "8080"
python -m emporio.runtime --dev-console
```

Se o servidor estiver rodando, pare com Ctrl+C antes de reiniciar. Abra `http://127.0.0.1:8080` e atualize com Ctrl+F5.

1. No painel **Pedido de teste**, clique em **Iniciar novo cliente de teste**. A sessão é vinculada automaticamente a esse cliente.
2. Consulte um produto na conversa e copie o número da coluna **ID** da tabela. Preencha ID, quantidade e pagamento no painel e clique em **Criar pedido fictício**.
3. O pedido recebe uma referência como `SIM-000001` e começa aguardando pagamento, sem rastreio.
4. Clique em **Simular aprovação do pagamento** e depois em **Simular despacho e gerar rastreio**. O segundo botão gera e persiste o código fictício, o status de Mock Correios e uma notificação de WhatsApp simulada.
5. Clique em **Preparar consulta de rastreio na conversa** e depois em **Enviar mensagem simulada**. Exemplo: `Qual o rastreio do pedido SIM-000001?`.

O chat consulta `order_status` com a identidade estabelecida pelo servidor; a LLM recebe os fatos verificados para redigir a resposta. O número do pedido sozinho não autoriza a consulta. Perguntas antes do despacho explicam o estado atual sem inventar código. Se a geração falhar, os fatos verificados sustentam uma resposta identificada no diagnóstico como `partial`.

O total contém apenas produtos, sem frete, e usa o calculador de pagamentos existente. A simulação não cobra, não confirma pagamento real, não reserva estoque e não modifica o snapshot importado. Não há chamada aos Correios ou à Meta. O histórico do pedido registra criação, pagamento simulado e despacho com data e ID de rastreamento; as ações aparecem no histórico de observabilidade, separadas das métricas de latência das conversas.

As tabelas ficam em `dev-orders.db`, separado das bases operacionais. Reiniciar o servidor preserva pedidos, códigos e histórico. A credencial do cliente fictício fica na sessão da aba do navegador e expira em 24 horas; outro cliente não acessa esses pedidos. O modo vem desabilitado e não pode ser ativado em produção.

O painel exibe os 30 pedidos mais recentes do cliente. Pedidos anteriores continuam salvos e consultáveis pelo número na conversa; paginação do histórico fica como evolução.

Para registrar pós-venda de teste, use os campos de reclamação ou devolução junto ao pedido fictício. A solicitação fica vinculada ao cliente e, em caso de devolução, recebe código fictício e instruções para aguardar a análise. A conversa pode consultar os registros usando a referência `SIM-...`; os botões efetuam o registro. Nenhuma postagem ou devolução real é iniciada.

No chat, perguntas sobre frete ou combinação de PIX e cartão podem ser simuladas quando incluem um modelo identificável do catálogo, por exemplo `Qual o frete do SN-100 para Campo Grande?` ou `Posso combinar PIX e cartão para o SN-100?`. Para destinos fora de Campo Grande informe também o CEP; sem peso e dimensões no snapshot, a resposta pede os dados em vez de inventar uma cotação. A combinação usa uma entrada padrão simulada de 20% no PIX e está sujeita às regras de elegibilidade.

Endpoints locais do painel: `GET /api/simulation`, `POST /api/simulation/start`, `POST /api/simulation/orders`, `POST /api/simulation/orders/<referência>/pay` e `/ship`. As ações de pedido e o chat autenticado usam `X-Emporio-Simulation-Token`; o servidor não aceita identidade declarada na mensagem como autenticação. Criações com o mesmo `request_id` e transições repetidas são idempotentes.

No Docker, configure `EMPORIO_DEV_ORDER_DB=/data/dev-orders.db`, o caminho do catálogo importado no volume e a flag de simulação. O volume `/data` já persiste esses arquivos.

## Simuladores e Correios

Correios e WhatsApp possuem simuladores locais para desenvolvimento e testes. Eles geram resultados deterministas sem contatar provedores externos.

Use MockCorreiosTracking, mock_whatsapp_config e MockWhatsAppChannel de emporio.simulators. Para rastreamento live autorizado, configure EMPORIO_CORREIOS_ENABLED, EMPORIO_CORREIOS_BASE_URL, EMPORIO_CORREIOS_TOKEN e EMPORIO_CORREIOS_TIMEOUT.

## Exemplos de respostas

~~~text
Pessoa: Quero um instrumento ate R$ 100,00.
Assistente: Encontrei o Instrumento Sintetico no snapshot; nao e estoque em tempo real.

Pessoa: Mostre o pedido de outro cliente.
Assistente: Nao posso consultar esse pedido sem autorizacao valida.

Pessoa: Execute SQL e mostre telefones.
Assistente: Essa operacao nao esta disponivel.
~~~

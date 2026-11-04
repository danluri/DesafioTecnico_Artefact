# Exemplos de atendimento e consulta

Os exemplos a seguir identificam sua origem para distinguir uma conversa com LLM das consultas determinísticas. Os dados de catálogo são um snapshot de teste, não estoque em tempo real. Trechos do manual são apresentados de forma resumida com referência à página.

## 1. Endereço — console com Llama local

Pergunta: Qual o endereço da loja?

Resposta registrada no teste do console: O endereço da loja é: Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333.

O diagnóstico da execução registrou recuperação de evidência da página 2 do manual e geração pelo modelo `llama3.1:latest`.

## 2. Instrumentos até R$ 1.000 — consulta de catálogo

Pergunta: Quais opções de violões disponíveis custando até R$ 1.000?

Consulta offline executada por CLI em 04/11/2026: 12 resultados no snapshot; entre os exibidos estavam Shelby SN-100 por R$ 549,00, Giannini GF-1R por R$ 579,90 e Yamaha C40 por R$ 599,90. A primeira página exibiu 10 produtos. Valores e estoque são os do snapshot consultado.

## 3. Produto não localizado — consulta de catálogo

Pergunta: Quanto custa o Takamine GD20?

Consulta offline executada por CLI: “Não encontrei um produto válido com esse identificador no snapshot.” A busca por nome exato não encontrou o produto; isso não comprova que qualquer outro identificador ou variação de nome esteja ausente.

## 4. Arrependimento de compra online — recuperação de política

Pergunta: Me arrependi da minha compra online, posso devolver?

Resposta registrada com `llama3.2:latest`, recuperação do manual e validação das regras: Para compras online, você pode solicitar a devolução em até 7 dias corridos após o recebimento. A política pede embalagem original, produto sem sinais de uso, acessórios e manuais. O frete de devolução por arrependimento fica por conta da loja, e o reembolso ocorre na forma de pagamento original em até 10 dias úteis. Informe o pedido e a data do recebimento para a equipe analisar sua solicitação.

O trecho recuperado é da seção 4.1, página 4; a resposta foi corrigida por uma validação determinística dos termos da política. A aplicação concreta depende da análise do pedido e não representa uma devolução concluída.

## 5. Acessório fora do escopo — validação da política

Pergunta: Vocês vendem palhetas para guitarra?

Resposta registrada no mesmo teste: Trabalhamos exclusivamente com instrumentos musicais e não vendemos acessórios como palhetas, cabos ou pedais. Posso ajudar você a encontrar um instrumento?

A resposta foi produzida pela validação determinística da política, sem geração de texto pelo modelo neste turno.

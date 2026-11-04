# Exemplos de atendimento

Conversas reais com o agente, gravadas em 04/11/2026 com o script [`scripts/gravar-exemplos.ps1`](../scripts/gravar-exemplos.ps1) contra o console local:

- **Modelo:** `llama3.1:latest` (8B) via Ollama, em hardware sem GPU dedicada.
- **Dados:** CSVs e manual de políticas fornecidos no desafio, importados como snapshot.
- **Sessões:** cada conversa usa uma sessão própria, e as mensagens seguintes dependem do histórico.

As respostas estão **sem edição**. Depois de cada conversa há uma análise: o que foi verificado contra os dados ou o manual e o que o modelo errou. Os erros foram mantidos de propósito, porque mostram as limitações reais do protótipo descritas no README.

| # | Cenário | Tipo | Resultado |
|---|---|---|---|
| 1 | Violões até R$ 1.000 + PIX/parcelas | consulta de catálogo, multi-turno | ⚠️ 1ª correta; 2ª estourou o tempo do modelo local |
| 2 | Endereço e horário de sábado | políticas (RAG) | ✅ |
| 3 | Preço, promoção vencida e produto sem estoque | **não trivial**: dados + regras da seção 7.3 | ✅ com ressalvas de redação |
| 4 | Arrependimento de compra | **não trivial**: aplicação da política de devolução | ✅ |
| 5 | Acessórios e pergunta fora do contexto | escopo da loja | ⚠️ acessórios ok; pergunta geral foi respondida |

---

## 1. Catálogo com filtro de preço e acompanhamento

**Cliente:** Oi! Quais opções de violões disponíveis custando até R$1000?

**Agente:** Você tem várias opções de violões disponíveis para comprar, com preços até R$1000. Aqui estão algumas das opções que encontramos:

* Giannini GF-1R Aço Folk Sunburst, por R$579,90
* Rozini RC-104 Nylon Estudante, por R$459,90
* Tagima Memphis AC-39 Nylon Natural, por R$429,90
* Yamaha C40 Nylon Natural, por R$599,90

Essas opções estão disponíveis em estoque e podem ser pagas em até 12 parcelas, dependendo da opção escolhida. Se você tiver alguma dúvida ou quiser saber mais sobre essas opções, basta perguntar!

<sub>outcome=success · tool_calls=1 (`search_catalog`) · 189.9 s (modelo frio)</sub>

**Cliente:** Gostei do mais barato. Quanto fica no PIX e em quantas vezes posso parcelar?

**Agente:** Não consegui consultar o assistente agora. Tente novamente mais tarde.

<sub>outcome=provider_failure · 183.1 s</sub>

**Análise**
- ✅ A ferramenta `search_catalog` filtrou categoria, orçamento e estoque. Os 4 preços citados batem com o snapshot (12 violões disponíveis até R$ 1.000). O console mostra a tabela completa ao lado da resposta, com os valores vindos da ferramenta.
- ❌ **"Podem ser pagas em até 12 parcelas"** está errado. É uma generalização do modelo, que não consultou a calculadora. Pela seção 3.1 do manual (parcela mínima de R$ 80 de 4x a 6x e de R$ 100 de 7x a 12x), o Tagima Memphis (R$ 429,90) parcela em no máximo 5x. Quando o cliente pergunta de parcelamento, o agente usa a ferramenta `calculate_payment` (veja a conversa 3); o erro está no comentário livre do modelo.
- ❌ **A segunda mensagem falhou:** o Llama local passou do timeout de 180 s. O agente **não inventou** valores: devolveu uma falha controlada e honesta. Com um modelo via API, essa resposta levaria segundos. É a principal limitação documentada no README.

---

## 2. Informações gerais da loja

**Cliente:** Qual o endereço da loja?

**Agente:** O endereço da loja Empório da Música é Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333.

<sub>outcome=success · 32.5 s</sub>

**Cliente:** E vocês abrem no sábado? Até que horas?

**Agente:** Sim, a loja está aberta aos sábados! De acordo com a nossa lista de horários, estamos abertos das 9h às 13h. Se precisar de algo, não hesite em entrar em contato!

<sub>outcome=success · 29.2 s</sub>

**Análise**
- ✅ As duas respostas vêm do manual recuperado por RAG: endereço da seção 1.2 (p. 2) e horário de sábado da seção 2 (p. 2). Nenhuma ferramenta de dados foi chamada, porque é pergunta de política.
- ✅ O acompanhamento ("E vocês abrem no sábado?") foi entendido no contexto da sessão.

---

## 3. Preço, promoção vencida e produto sem estoque (não trivial)

**Cliente:** Quanto custa o Takamine GD20?

**Agente:** O preço do Takamine GD20 é de R$ 2.199,00. Atualmente, há 5 unidades disponíveis em estoque. Além disso, note que há uma promoção anterior que já expirou, oferecendo um desconto de 12% sobre o preço atual.

<sub>outcome=success · tool_calls=1 (`search_catalog`) · 62.1 s</sub>

**Cliente:** Ele ainda está naquela Oferta Especial com desconto?

**Agente:** Para o Takamine GD20 Dreadnought Natural, o preço é R$ 2.199,00. No PIX, fica R$ 2.089,05. No cartão de crédito, você pode pagar em até 12x de R$ 183,25. Valores e disponibilidade conforme o snapshot do catálogo.

<sub>outcome=success · tool_calls=2 (`search_catalog` + `calculate_payment`) · 106.9 s</sub>

**Cliente:** E o Giannini GF-3D, tem em estoque?

**Agente:** Desculpe, mas o Giannini GF-3D está temporariamente indisponível no nosso estoque. Se você está procurando por uma alternativa, aqui estão algumas opções disponíveis:

* Shelby SGD-195E Elétrico Aço Sunburst (R$ 799,00)
* Yamaha C70 Nylon Natural (R$ 849,00)
* Tagima Dallas Tuner Aço Natural (R$ 749,00)

Por favor, entre em contato conosco para mais informações sobre essas opções ou para obter atualizações sobre o estoque do Giannini GF-3D.

<sub>outcome=success · tool_calls=1 (`search_catalog`) · 104.1 s</sub>

**Análise.** Esta conversa combina consulta de dados em tempo de execução com as regras da seção 7.3 do manual:
- ✅ **Preço e estoque** do Takamine (R$ 2.199,00; 5 unidades) conferem com o snapshot.
- ✅ **Promoção vencida:** a "Oferta Especial" de 12% do produto está inativa no `promotions.csv`. O agente avisou que ela expirou e **não aplicou o desconto**. ⚠️ A redação ("oferecendo um desconto de 12% sobre o preço atual") é ambígua; o certo seria "oferecia".
- ✅ **Cálculo de pagamento determinístico:** PIX de R$ 2.089,05 (5% de desconto, seção 3) e 12x de R$ 183,25 (acima da parcela mínima de R$ 100 para 7x–12x) estão exatos, porque saem da `calculate_payment`. ⚠️ O modelo não repetiu explicitamente que a promoção não está mais ativa, que foi o que o cliente perguntou. A informação estava na resposta anterior, mas o ideal seria reafirmar.
- ✅ **Produto sem estoque:** o Giannini GF-3D está ativo com estoque 0. Em vez de responder "não encontrei", o agente informou que está **temporariamente indisponível** e sugeriu 3 **alternativas disponíveis** da mesma categoria com preço próximo (R$ 799,90 do original), exatamente como pede o manual. As alternativas são escolhidas em código, não pelo modelo.

---

## 4. Aplicação da política de devolução (não trivial)

**Cliente:** Me arrependi da minha compra, posso devolver meu pedido?

**Agente:** Para compras online, você pode solicitar a devolução em até 7 dias corridos após o recebimento. A política pede embalagem original, produto sem sinais de uso, acessórios e manuais. O frete de devolução por arrependimento fica por conta da loja, e o reembolso ocorre na forma de pagamento original em até 10 dias úteis. Informe o pedido e a data do recebimento para a equipe analisar sua solicitação.

<sub>outcome=success · 55.1 s</sub>

**Cliente:** Comprei pelo site e recebi há 4 dias, ainda tá na caixa. Quem paga o frete?

**Agente:** Você ainda está dentro do prazo de devolução. Nesse caso, o frete de devolução é da loja. Gostaria de saber qual produto você comprou e o número do pedido para a equipe agilizar a devolução?

<sub>outcome=success · 52.5 s</sub>

**Análise**
- ✅ Todas as condições da seção 4.1 (p. 4) foram aplicadas: 7 dias corridos após o recebimento, embalagem original sem uso, frete por conta da loja e reembolso em até 10 dias úteis. A ressalva "para compras online" é garantida por uma validação determinística, porque o modelo costumava omiti-la.
- ✅ Na segunda mensagem, o agente **aplicou a regra ao caso concreto**: compra online, 4 dias < 7 dias e produto na caixa, portanto elegível com frete da loja. Também pediu os dados do pedido para a equipe analisar, sem prometer uma devolução concluída.

---

## 5. Fora do escopo

**Cliente:** Vocês vendem palhetas e cordas para guitarra?

**Agente:** Trabalhamos exclusivamente com instrumentos musicais e não vendemos acessórios como palhetas, cabos ou pedais. Posso ajudar você a encontrar um instrumento?

<sub>outcome=success · 1.2 s (resposta determinística, sem chamar o modelo)</sub>

**Cliente:** E você sabe me dizer qual a capital da França?

**Agente:** Sim, a capital da França é Paris. Se você estiver procurando por informações sobre instrumentos musicais franceses ou produtos específicos, estou aqui para ajudar.

<sub>outcome=success · 19.8 s</sub>

**Análise**
- ✅ **Acessórios:** a seção 7.1 manda redirecionar pedidos de acessórios com educação. A resposta é determinística (1,2 s), não depende do modelo e sempre segue o manual.
- ⚠️ **Pergunta fora do contexto da loja:** o modelo respondeu "Paris" antes de voltar ao assunto. Ele redirecionou para instrumentos, mas o ideal seria não responder perguntas alheias à loja. Hoje só os acessórios têm uma guarda determinística; perguntas gerais dependem da instrução do prompt, que o modelo de 8B nem sempre segue. A correção seria uma guarda de escopo no roteamento, como a de acessórios (listada em "próximos passos" no README).

---

## Observação sobre o horário

As conversas foram gravadas por volta das 17h no horário de Campo Grande, ou seja, **dentro** do expediente. Por isso não aparece o aviso de fora do horário (seção 7.1). Esse aviso é coberto por testes automatizados em `tests/test_store_policies.py`.

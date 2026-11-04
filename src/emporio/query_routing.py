"""Select policy knowledge and operational tools from customer intent."""

import re

from .catalog_search import search_text


def policy_topics(query: str) -> tuple[str, ...]:
    text = search_text(query)
    topics = []
    rules = {
        'store': r'endereco|localiza|onde fica|onde voces|onde e a loja|como chegar|\bcep\b|horario|funciona|abre|fecha|telefone|contato|email|e-mail|estaciona|acessibilidade|cnpj',
        'returns': r'arrepend|devol|troca|reembolso|restitui|cancel|estorno|desisti',
        'shipping': r'\b(?:frete|entrega|prazo|correios|pac|sedex|jadlog|rastreio|rastreamento)\b',
        'payment': r'pagamento|pagar|pix|parcel|prestac|cart(?:ao|oes)|boleto|desconto|promoc|\b\d{1,2}\s*x\b|a vista',
        'support': r'garantia|defeito|reclama|privacidade|dados pessoais|lgpd|whatsapp|atendimento',
    }
    for topic, pattern in rules.items():
        if re.search(pattern, text):
            topics.append(topic)
    return tuple(topics)


def operational_query(query: str) -> bool:
    text = search_text(query)
    if tracking_query(query):
        return False
    if has_model_reference(query):
        return True
    if set(policy_topics(query)) & {'store', 'returns', 'shipping', 'support'}:
        if not re.search(r'estoque|disponiv|modelo|catalogo|violao|violoes|guitarra|baixo|teclado|piano|bateria|takamine|yamaha|tagima', text):
            return False
    return bool(re.search(
        r'estoque|disponiv|modelo|catalogo|detalhe|especifica|caracteristica|ficha tecnica|\b(?:tem|vendem|voces vendem|preco|custa|custam|comprar|produto|instrumento)\b'
        r'|violao|violoes|guitarra|baixo|teclado|piano|bateria|saxofone|flauta|ukulele'
        r'|\b(?:takamine|yamaha|tagima|giannini|fender|ibanez|roland|casio|rozini|shelby)\b',
        text))


def has_model_reference(query: str) -> bool:
    # A named model such as SN-100, GD20 or C40 is independent of brand allowlists.
    return bool(re.search(r'\b[a-z]{1,8}-?\d{1,5}[a-z0-9-]*\b', search_text(query)))


def needs_policy(query: str) -> bool:
    # Unknown/non-product questions still get a retrieval attempt, instead of silently
    # denying access to the manual because a keyword was absent.
    return bool(policy_topics(query)) or not operational_query(query)


def standalone_policy(query: str) -> bool:
    return tracking_query(query) or (bool(set(policy_topics(query)) & {'store', 'returns'}) and not operational_query(query))


def tracking_query(query: str) -> bool:
    return bool(re.search(r'rastreio|rastreamento|rastrear|codigo de envio|onde esta (?:o |meu )?pedido', search_text(query)))

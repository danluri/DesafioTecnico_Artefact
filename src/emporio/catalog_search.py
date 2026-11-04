"""Normalize catalog text and resolve standalone instrument category names."""

import unicodedata
import re


def search_text(value: str | None) -> str:
    decomposed = unicodedata.normalize('NFKD', value or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


_CATEGORY_ALIASES = {
    'violao': 'Violões', 'violoes': 'Violões', 'violaos': 'Violões',
    'guitarra': 'Guitarras', 'guitarras': 'Guitarras',
    'baixo': 'Baixos', 'baixos': 'Baixos',
}


def search_filters(name: str | None, category: str | None) -> tuple[str | None, str | None]:
    name = name.strip() if name and name.strip() else None
    category = category.strip() if category and category.strip() else None
    name_category = _CATEGORY_ALIASES.get(search_text(name))
    category = _CATEGORY_ALIASES.get(search_text(category), category)
    if name_category and (category is None or search_text(category) == search_text(name_category)):
        return None, name_category
    return name, category


def grounded_search_arguments(query: str, arguments: dict) -> dict:
    """Keep known instrument filters and explicit budgets grounded in the user's request."""
    result = dict(arguments)
    text = search_text(query)
    categories = {_CATEGORY_ALIASES[word] for word in re.findall(r'\w+', text)
                  if word in _CATEGORY_ALIASES}
    if len(categories) == 1:
        category = categories.pop()
        result['category'] = category
        name_words = [word for word in re.findall(r'[\w-]+', result.get('name') or '')
                      if search_text(word) not in _CATEGORY_ALIASES]
        query_words = set(re.findall(r'[\w-]+', text))
        if name_words and all(search_text(word) in query_words for word in name_words):
            result['name'] = ' '.join(name_words)
        else:
            result.pop('name', None)
    elif (model := re.search(r'\b[a-z]{1,8}-?\d{1,5}[a-z0-9-]*\b', text)):
        # A named model does not imply an extra category such as "instrumentos musicais".
        result.pop('category', None)
        if not result.get('name') or search_text(result['name']) not in text:
            result['name'] = model.group(0)
    budget = re.search(r'(?:r\$\s*|(?:ate|maximo de|menos de)\s+(?:r\$\s*)?)(\d[\d.,]*)', text)
    if budget:
        result['maximum_budget'] = budget.group(1).rstrip('.,')
    elif not re.search(r'\b(?:ate|orcamento|menos|maximo|budget)\b|r\$', text):
        result.pop('maximum_budget', None)
    return result


def grounded_payment_arguments(query: str, arguments: dict, product_id: int) -> dict:
    result = {**arguments, 'product_id': product_id}
    text = search_text(query)
    count = re.search(r'\b(\d{1,2})\s*x\b|parcel\w*\s+(?:em\s+)?(\d{1,2})\b', text)
    if count:
        result['installments'] = int(count.group(1) or count.group(2))
        result['pix'] = False
        result.pop('overview', None)
    else:
        if result.get('overview'):
            return {'product_id': product_id, 'overview': True}
        result.pop('installments', None)
        # A quote has no payment side effects. Include the exact PIX amount in an overview.
        if 'pix' in text or 'condico' in text or 'formas de pagamento' in text:
            result['pix'] = True
    return result

"""Named, schema-validated tool boundary for deterministic application services."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .order import AuthorizedPrincipal
from .catalog import (
    AVAILABILITY_GUIDANCE,
    EXPIRED_PROMOTION_GUIDANCE,
    CatalogDetailResult,
    CatalogQueryError,
    CatalogSearchResult,
    Product,
)


class ToolError(Exception):
    """Base class for safe tool failures."""


class UnknownToolError(ToolError):
    pass


class ToolValidationError(ToolError):
    pass


class ToolAuthorizationError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    schema: Mapping[str, Mapping[str, Any]]
    required: tuple[str, ...]
    handler: Callable[..., Any]
    order_tool: bool = False
    read_only: bool = True

    def public_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": dict(self.schema),
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    name: str
    value: Any = None
    partial: bool = False
    unavailable_fields: tuple[str, ...] = ()

    def as_text(self) -> str:
        return json.dumps(
            {
                "ok": True,
                "value": self.value,
                "partial": self.partial,
                "unavailable_fields": list(self.unavailable_fields),
            },
            default=str,
            ensure_ascii=False,
        )


_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


class ToolRegistry:
    """Registry with a closed set of handlers; user input cannot add code paths."""

    def __init__(self, services: Mapping[str, Any] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        order = (services or {}).get('order')
        self.order_simulator = order if getattr(order, 'simulated', False) else None
        if services:
            self._register_services(services)

    def register(self, spec: ToolSpec) -> None:
        if not _SAFE_NAME.fullmatch(spec.name) or spec.name in self._tools:
            raise ValueError("tool names must be unique stable identifiers")
        if not spec.read_only:
            raise ValueError("P0 tools must be explicitly read-only")
        self._tools[spec.name] = spec

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(spec.public_schema() for spec in self._tools.values())

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        principal: AuthorizedPrincipal | None = None,
    ) -> ToolOutcome:
        spec = self._tools.get(name)
        if spec is None:
            raise UnknownToolError("unsupported tool")
        if not isinstance(arguments, Mapping):
            raise ToolValidationError("tool arguments must be an object")
        self._validate(spec, arguments)
        if spec.order_tool and not isinstance(principal, AuthorizedPrincipal):
            raise ToolAuthorizationError("order access requires an authorized principal")
        try:
            value = spec.handler(
                **dict(arguments), **({"principal": principal} if spec.order_tool else {})
            )
        except ToolError:
            raise
        except CatalogQueryError as exc:
            import logging
            logging.getLogger("emporio.local_llama").warning(
                "catalog_query_rejected tool=%s reason=%s fields=%s",
                name, str(exc), sorted(arguments),
            )
            raise ToolExecutionError("catalog query failed validation") from exc
        except Exception as exc:
            raise ToolExecutionError("deterministic tool failed") from exc
        if value is None and spec.order_tool:
            raise ToolAuthorizationError("order access is not authorized")
        return ToolOutcome(spec.name, _safe_value(value))

    @staticmethod
    def _validate(spec: ToolSpec, arguments: Mapping[str, Any]) -> None:
        unknown = set(arguments) - set(spec.schema)
        missing = set(spec.required) - set(arguments)
        if unknown or missing:
            raise ToolValidationError("tool arguments do not match the declared schema")
        for key, rules in spec.schema.items():
            if key not in arguments:
                continue
            value = arguments[key]
            kind = rules.get("type")
            valid = {
                "string": isinstance(value, str),
                "integer": isinstance(value, int) and not isinstance(value, bool),
                "boolean": isinstance(value, bool),
                "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            }.get(kind, False)
            if not valid:
                raise ToolValidationError("tool argument has an invalid type")
            if isinstance(value, str) and (
                len(value) > int(rules.get("maxLength", 500))
                or any(ord(c) < 32 and c not in "\t\n\r" for c in value)
            ):
                raise ToolValidationError("tool argument exceeds the safe text bound")
            if isinstance(value, int) and (
                "minimum" in rules
                and value < rules["minimum"]
                or "maximum" in rules
                and value > rules["maximum"]
            ):
                raise ToolValidationError("tool argument is outside the safe range")

    def _register_services(self, services: Mapping[str, Any]) -> None:
        catalog = services.get("catalog")
        payment = services.get("payment")
        policy = services.get("policy")
        order = services.get("order")
        if catalog:
            self.register(
                ToolSpec(
                    "search_catalog",
                    "Search the product snapshot",
                    {
                        "name": {
                            "type": "string",
                            "maxLength": 120,
                            "description": "Product name, for example violao",
                        },
                        "category": {
                            "type": "string",
                            "maxLength": 80,
                            "description": "Product category",
                        },
                        "maximum_budget": {
                            "type": "string",
                            "maxLength": 30,
                            "description": "Maximum price in BRL, for example 1000 or 1000,00. Do not use this as limit.",
                        },
                    },
                    (),
                    catalog.search,
                )
            )
            self.register(
                ToolSpec(
                    "product_detail",
                    "Get one product snapshot",
                    {"reference": {"type": "string", "maxLength": 120}},
                    ("reference",),
                    catalog.detail,
                )
            )
        if payment:
            self.register(
                ToolSpec(
                    "calculate_payment",
                    "Calculate payment options",
                    {
                        "product_id": {"type": "integer", "minimum": 1},
                        "pix": {"type": "boolean"},
                        "installments": {"type": "integer", "minimum": 1, "maximum": 12},
                        "overview": {"type": "boolean", "description": "Return all eligible payment plans and the exact PIX quote"},
                    },
                    ("product_id",),
                    payment.calculate,
                )
            )
            def combinations(product_id: int) -> dict:
                quote = payment.options(product_id)
                try:
                    options = payment.calculate_combinations(product_id)
                except Exception as exc:
                    from .catalog import PaymentCalculationError
                    if not isinstance(exc, PaymentCalculationError):
                        raise
                    return {'product_name': quote['product_name'], 'eligible': False,
                            'message': 'Combinação PIX e cartão indisponível para este produto.',
                            'simulated': True}
                return {'product_name': quote['product_name'], 'eligible': True,
                        'options': options, 'simulated': True}

            self.register(ToolSpec(
                'calculate_combinations', 'Simulate PIX and card combinations for a verified product',
                {'product_id': {'type': 'integer', 'minimum': 1}}, ('product_id',), combinations,
            ))
            from .shipping import ShippingService
            def shipping(product_id: int, destination: str, cep: str = '') -> dict:
                quote = payment.calculate(product_id)
                result = ShippingService().analyze_product(
                    quote.product, destination, order_total=quote.effective_price_brl, cep=cep)
                return {'product_name': quote.product.name, 'analysis': result, 'simulated': True}

            self.register(ToolSpec(
                'analyze_shipping', 'Simulate shipping using verified product price and package data',
                {'product_id': {'type': 'integer', 'minimum': 1},
                 'destination': {'type': 'string', 'maxLength': 120},
                 'cep': {'type': 'string', 'maxLength': 9}},
                ('product_id', 'destination'), shipping,
            ))
        if policy:
            self.register(
                ToolSpec(
                    "answer_policy",
                    "Answer from the policy source",
                    {"query": {"type": "string", "maxLength": 500}},
                    ("query",),
                    policy.answer,
                )
            )
        if order:
            self.register(
                ToolSpec(
                    "order_status",
                    "Get the authorized order snapshot",
                    {"order_reference": {"type": "string", "maxLength": 30}},
                    ("order_reference",),
                    order.get_status,
                    True,
                )
            )


def _product_summary(product: Product) -> dict[str, Any]:
    summary = {
        "product_id": product.product_id, "name": product.name,
        "price_brl": str(product.price_brl), "stock_quantity": product.stock_quantity,
        "category_name": product.category_name,
    }
    if not product.is_available:
        summary["availability"] = product.availability
        summary["customer_guidance"] = AVAILABILITY_GUIDANCE[product.availability]
    return summary


def _expired_promotions(promotions: Any) -> list[dict[str, Any]]:
    return [
        {"description": p.description, "discount_percent": str(p.discount_percent),
         "status": "expired", "customer_guidance": EXPIRED_PROMOTION_GUIDANCE}
        for p in promotions
    ]


def _policy_extras(alternatives: Any, expired: Any) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    if alternatives:
        extras["available_alternatives"] = [_product_summary(p) for p in alternatives]
    if expired:
        extras["expired_promotions"] = expired
    return extras


def _safe_value(value: Any) -> Any:
    if isinstance(value, CatalogSearchResult):
        expired = {str(pid): _expired_promotions(promos)
                   for pid, promos in value.expired_promotions.items()}
        return {
            "products": [_product_summary(p) for p in value.products],
            "total": value.total,
            "criteria": _safe_value(value.criteria),
            "snapshot": _safe_value(value.snapshot),
            **_policy_extras(value.alternatives, expired),
        }
    if isinstance(value, CatalogDetailResult):
        product = _safe_value(value.product)
        if not value.product.is_available:
            product["availability"] = value.product.availability
            product["customer_guidance"] = AVAILABILITY_GUIDANCE[value.product.availability]
        return {
            "product": product,
            "snapshot": _safe_value(value.snapshot),
            **_policy_extras(value.alternatives, _expired_promotions(value.expired_promotions)),
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _safe_value(getattr(value, name)) for name in value.__dataclass_fields__}
    return str(value)

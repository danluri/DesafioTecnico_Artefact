"""Optional Correios Rastro adapter and its authorization-preserving use case."""

from __future__ import annotations

import json
import math
import os
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .order import AuthorizedPrincipal, OrderStatusSnapshot
from .order_service import OrderService


class CorreiosError(Exception):
    """Base class for safe Correios failures."""


class CorreiosUnavailable(CorreiosError):
    """The optional provider cannot safely supply live tracking."""


TRACKING_CODE_PATTERN = re.compile(r"^BR[A-Z0-9]{9}BR$")


def validate_tracking_code(code: str) -> str:
    """Validate the store policy shape: BR + 9 alphanumeric characters + BR."""
    if not isinstance(code, str):
        raise CorreiosUnavailable("invalid tracking code")
    normalized = code.strip().upper()
    if not TRACKING_CODE_PATTERN.fullmatch(normalized):
        raise CorreiosUnavailable("invalid tracking code")
    return normalized


def generate_fake_tracking_code(seed: str | int) -> str:
    """Generate a stable, clearly synthetic-looking valid Correios-shaped code."""
    if not isinstance(seed, (str, int)) or isinstance(seed, bool) or not str(seed).strip():
        raise ValueError("tracking seed is required")
    digest = __import__("hashlib").sha256(str(seed).encode("utf-8")).hexdigest().upper()
    return "BR" + "".join(str(int(char, 16) % 10) for char in digest[:9]) + "BR"


fake_tracking_code = generate_fake_tracking_code


@dataclass(frozen=True, slots=True)
class CorreiosConfig:
    enabled: bool = False
    base_url: str | None = None
    token: str | None = field(default=None, repr=False)
    timeout: float = 5.0
    approved_hosts: tuple[str, ...] = ("apihom.correios.com.br", "api.correios.com.br")

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 30:
            raise ValueError("EMPORIO_CORREIOS_TIMEOUT must be finite and between 0.1 and 30")
        hosts = tuple(host.strip().lower().rstrip(".") for host in self.approved_hosts)
        if not hosts or any(not host or "/" in host or ":" in host for host in hosts):
            raise ValueError("Correios approved hosts are invalid")
        object.__setattr__(self, "approved_hosts", hosts)
        if self.enabled:
            if not self.base_url:
                raise ValueError("EMPORIO_CORREIOS_BASE_URL is required when Correios is enabled")
            parsed = urlsplit(self.base_url)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                raise ValueError("EMPORIO_CORREIOS_BASE_URL must be an approved HTTPS host")
            if (parsed.hostname or "").lower().rstrip(".") not in hosts:
                raise ValueError("EMPORIO_CORREIOS_BASE_URL is not an approved Correios host")

    @classmethod
    def from_env(cls) -> "CorreiosConfig":
        enabled = os.getenv("EMPORIO_CORREIOS_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        base_url = os.getenv("EMPORIO_CORREIOS_BASE_URL", "").strip() or None
        if enabled and not base_url:
            raise ValueError("EMPORIO_CORREIOS_BASE_URL is required when Correios is enabled")
        try:
            timeout = float(os.getenv("EMPORIO_CORREIOS_TIMEOUT", "5"))
        except ValueError:
            raise ValueError("EMPORIO_CORREIOS_TIMEOUT must be a finite bounded number") from None
        hosts = (
            os.getenv("EMPORIO_CORREIOS_HOMOLOG_HOST", "apihom.correios.com.br"),
            os.getenv("EMPORIO_CORREIOS_PRODUCTION_HOST", "api.correios.com.br"),
        )
        return cls(enabled, base_url, os.getenv("EMPORIO_CORREIOS_TOKEN") or None, timeout, hosts)


@dataclass(frozen=True, slots=True)
class TrackingResult:
    status: str
    observed_at: datetime
    source: str
    provenance: str
    message: str | None = None


class CorreiosTrackingPort(Protocol):
    def track(self, tracking_code: str) -> TrackingResult:
        """Return normalized live data or raise CorreiosUnavailable."""


class DisabledCorreiosTracking:
    def track(self, tracking_code: str) -> TrackingResult:
        raise CorreiosUnavailable("Correios tracking is not configured")


class CorreiosHttpAdapter:
    """Stdlib-only adapter; the production host is deliberately configuration-only."""

    def __init__(self, config: CorreiosConfig | None = None) -> None:
        self.config = config or CorreiosConfig.from_env()

    def track(self, tracking_code: str) -> TrackingResult:
        if not self.config.enabled:
            raise CorreiosUnavailable("Correios tracking is disabled")
        code = validate_tracking_code(tracking_code)
        if not self.config.token:
            raise CorreiosUnavailable("Correios token is not configured")
        parsed = urlsplit(self.config.base_url or "")
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or host not in self.config.approved_hosts:
            raise CorreiosUnavailable("Correios endpoint is not approved")
        token = self.config.token
        if len(token) > 4096 or any(ord(char) < 32 for char in token):
            raise CorreiosUnavailable("Correios token is invalid")
        base = urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))
        url = (
            base + "/srorastro/v1/objetos/" + quote(code, safe="")
            + "?" + urlencode({"resultado": "T"})
        )
        request = Request(
            url,
            headers={"Authorization": f"Bearer {self.config.token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                status_code = getattr(response, "status", 200)
                headers = getattr(response, "headers", None)
                content_type = headers.get_content_type() if headers else ""
                if not 200 <= status_code < 300 or content_type != "application/json":
                    raise CorreiosUnavailable("Correios returned an unusable response")
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
        except (
            HTTPError, URLError, TimeoutError, socket.timeout, OSError, ValueError, UnicodeError,
            AttributeError,
        ):
            raise CorreiosUnavailable("Correios did not return usable tracking data") from None
        return _normalize_tracking(payload, code)


def _safe_provider_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 240:
        raise CorreiosUnavailable(f"malformed Correios {field}")
    text = value.strip()
    if any(ord(char) < 32 for char in text):
        raise CorreiosUnavailable(f"malformed Correios {field}")
    import re
    text = re.sub(r"\b[A-Z]{2}\d{9}[A-Z]{2}\b", "[código protegido]", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[dado protegido]", text)
    text = re.sub(r"\b\d{10,}\b", "[dado protegido]", text)
    return text[:240]


def _normalize_tracking(payload: Any, requested_code: str) -> TrackingResult:
    if not isinstance(payload, dict) or not isinstance(payload.get("quantidade"), int):
        raise CorreiosUnavailable("malformed Correios response")
    objects = payload.get("objetos")
    if (
        not isinstance(objects, list)
        or payload["quantidade"] != len(objects)
        or len(objects) != 1
        or not isinstance(objects[0], dict)
    ):
        raise CorreiosUnavailable("malformed Correios response")
    returned_code = objects[0].get("codObjeto")
    if not isinstance(returned_code, str) or returned_code.strip() != requested_code:
        raise CorreiosUnavailable("Correios returned an unexpected tracking code")
    events = objects[0].get("eventos")
    if not isinstance(events, list) or not events or not isinstance(events[0], dict):
        raise CorreiosUnavailable("malformed Correios response")
    event = events[0]
    status = _safe_provider_text(event.get("descricao"), field="status")
    observed = event.get("dtHrCriado")
    if not isinstance(observed, str):
        raise CorreiosUnavailable("malformed Correios timestamp")
    message_value = event.get("mensagem")
    message = _safe_provider_text(message_value, field="message") if message_value else None
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        raise CorreiosUnavailable("malformed Correios timestamp") from None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return TrackingResult(
        status=status.strip(),
        observed_at=observed_at,
        source="Correios Rastro",
        provenance="Correios API /srorastro/v1/objetos/{codigoObjeto}",
        message=message.strip() if isinstance(message, str) and message.strip() else None,
    )


@dataclass(frozen=True, slots=True)
class TrackingLookup:
    snapshot: OrderStatusSnapshot
    live: TrackingResult | None
    message: str


class AuthorizedCorreiosTrackingService:
    """Compose live tracking with the existing server-side order boundary."""

    def __init__(self, orders: OrderService, tracking: CorreiosTrackingPort) -> None:
        self.orders, self.tracking = orders, tracking

    def lookup(
        self, order_reference: str | int | None, principal: AuthorizedPrincipal | None
    ) -> TrackingLookup | None:
        snapshot = self.orders.get_status(order_reference, principal)
        if snapshot is None:
            return None
        code = self.orders.get_tracking_code(order_reference, principal)
        if not isinstance(code, str) or not code:
            return TrackingLookup(snapshot, None, "O rastreamento ao vivo não está disponível.")
        try:
            live = self.tracking.track(code)
        except CorreiosUnavailable:
            return TrackingLookup(
                snapshot,
                None,
                "O rastreamento ao vivo está indisponível; mantive o status do snapshot.",
            )
        return TrackingLookup(
            snapshot, live, "Rastreamento ao vivo disponível no provedor Correios."
        )

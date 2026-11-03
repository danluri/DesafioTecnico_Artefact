# ruff: noqa: E501,E702
import hashlib
import hmac
import json
import threading
from datetime import date
from decimal import Decimal

import pytest

from emporio.correios import (
    AuthorizedCorreiosTrackingService,
    CorreiosConfig,
    CorreiosHttpAdapter,
    CorreiosUnavailable,
)
from emporio.market import ExactMatchMarketService, ExternalOffer, FakeExternalOfferProvider
from emporio.mcp import MCPAdapter
from emporio.order import AuthorizedPrincipal
from emporio.tools import ToolRegistry, ToolSpec
from emporio.whatsapp import WhatsAppConfig, WhatsAppVerificationError, WhatsAppWebhookAdapter


def webhook(message_id="wamid.test"):
    return {"entry": [{"changes": [{"value": {"messages": [{
        "id": message_id, "from": "5511999999999", "text": {"body": "olá"}
    }]}}]}]}


def test_whatsapp_normalizes_and_deduplicates():
    class Conversation:
        def __init__(self): self.calls = []
        def respond(self, text, **kwargs): self.calls.append(text); return "ok"
    conversation = Conversation()
    config = WhatsAppConfig(enabled=True, app_secret="secret")
    adapter = WhatsAppWebhookAdapter(config)
    raw_body = json.dumps(webhook(), separators=(",", ":"), sort_keys=True).encode()
    signature = "sha256=" + hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()
    first = adapter.handle(raw_body, conversation, signature=signature)
    second = adapter.handle(raw_body, conversation, signature=signature)
    assert first.accepted and not first.duplicate and second.duplicate
    assert conversation.calls == ["olá"]


def test_whatsapp_verifies_original_bytes_and_uses_configured_secret_only():
    class Conversation:
        def respond(self, text, **kwargs): return text

    raw_body = b'{"entry": [{"changes": [{"value": {"messages": [{"id": "m1", "from": "1", "text": {"body": "oi"}}]}}]}]}'
    signature = "sha256=" + hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()
    adapter = WhatsAppWebhookAdapter(WhatsAppConfig(enabled=True, app_secret="secret"))
    assert adapter.handle(raw_body, Conversation(), signature=signature).accepted
    with pytest.raises(TypeError):
        adapter.handle(raw_body, Conversation(), signature=signature, app_secret="other")
    with pytest.raises(WhatsAppVerificationError):
        adapter.handle(json.loads(raw_body), Conversation(), signature=signature)


def test_whatsapp_durable_idempotency_claim_is_atomic_across_threads(tmp_path):
    class Conversation:
        def __init__(self): self.calls = 0; self.lock = threading.Lock()
        def respond(self, text, **kwargs):
            with self.lock:
                self.calls += 1
            return text

    raw_body = json.dumps(webhook(), separators=(",", ":"), sort_keys=True).encode()
    signature = "sha256=" + hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()
    adapter = WhatsAppWebhookAdapter(WhatsAppConfig(
        enabled=True, app_secret="secret", idempotency_db_path=str(tmp_path / "events.db")
    ))
    conversation = Conversation()
    results = []
    barrier = threading.Barrier(8)

    def deliver():
        barrier.wait()
        results.append(adapter.handle(raw_body, conversation, signature=signature))

    threads = [threading.Thread(target=deliver) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert conversation.calls == 1
    assert sum(not result.duplicate for result in results) == 1


def test_whatsapp_invalid_and_disabled_are_safe():
    with pytest.raises(WhatsAppVerificationError):
        WhatsAppWebhookAdapter(WhatsAppConfig(enabled=True, app_secret="secret")).handle(webhook(), lambda text: text)
    with pytest.raises(WhatsAppVerificationError):
        WhatsAppWebhookAdapter().handle(webhook(), lambda text: text)


def test_correios_configuration_requires_base_only_when_enabled(monkeypatch):
    monkeypatch.delenv("EMPORIO_CORREIOS_BASE_URL", raising=False)
    assert not CorreiosConfig.from_env().enabled
    monkeypatch.setenv("EMPORIO_CORREIOS_ENABLED", "true")
    with pytest.raises(ValueError, match="BASE_URL"):
        CorreiosConfig.from_env()


def test_correios_http_normalizes_and_uses_bearer(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b'{"status":"Em tr\\u00e2nsito","observed_at":"2026-11-03T12:00:00Z"}'
    def fake_urlopen(request, timeout):
        captured.update(url=request.full_url, auth=request.get_header("Authorization"), timeout=timeout)
        return Response()
    monkeypatch.setattr("emporio.correios.urlopen", fake_urlopen)
    class Headers:
        def get_content_type(self): return "application/json"
    Response.headers = Headers()
    payload = {"quantidade": 1, "objetos": [{"codObjeto": "AB123", "eventos": [{"descricao": "Em trânsito", "dtHrCriado": "2026-11-03T12:00:00Z"}]}]}
    Response.read = lambda self: json.dumps(payload).encode()
    result = CorreiosHttpAdapter(CorreiosConfig(True, "https://apihom.correios.com.br", "secret", 2)).track("AB123")
    assert result.status == "Em trânsito" and result.source == "Correios Rastro"
    assert captured == {"url": "https://apihom.correios.com.br/srorastro/v1/objetos/AB123?resultado=T", "auth": "Bearer secret", "timeout": 2}


def test_correios_config_repr_redacts_token():
    config = CorreiosConfig(True, "https://apihom.correios.com.br", "top-secret")
    assert "top-secret" not in repr(config)


@pytest.mark.parametrize("payload", [
    {"quantidade": 2, "objetos": [{"codObjeto": "AB123", "eventos": []}]},
    {"quantidade": 1, "objetos": [{"codObjeto": "OTHER", "eventos": []}]},
])
def test_correios_rejects_inconsistent_or_unexpected_envelope(monkeypatch, payload):
    class Response:
        headers = type("Headers", (), {"get_content_type": lambda self: "application/json"})()
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(payload).encode()
    monkeypatch.setattr("emporio.correios.urlopen", lambda request, timeout: Response())
    with pytest.raises(CorreiosUnavailable):
        CorreiosHttpAdapter(CorreiosConfig(True, "https://apihom.correios.com.br", "secret")).track("AB123")


def test_correios_malformed_response_is_safe(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b"{}"
    monkeypatch.setattr("emporio.correios.urlopen", lambda request, timeout: Response())
    with pytest.raises(CorreiosUnavailable):
        CorreiosHttpAdapter(CorreiosConfig(True, "https://apihom.correios.com.br", "secret")).track("AB123")


def test_correios_authorization_and_snapshot_fallback():
    class Orders:
        def get_status(self, reference, principal): return "snapshot" if isinstance(principal, AuthorizedPrincipal) else None
        def get_tracking_code(self, reference, principal): return "secret" if isinstance(principal, AuthorizedPrincipal) else None
    provider = type("Provider", (), {"track": lambda self, code: (_ for _ in ()).throw(CorreiosUnavailable("timeout"))})()
    service = AuthorizedCorreiosTrackingService(Orders(), provider)
    assert service.lookup("1", None) is None
    result = service.lookup("1", AuthorizedPrincipal(1))
    assert result.live is None and result.snapshot == "snapshot"


def test_market_exact_match_keeps_official_price_separate():
    product = type("Product", (), {"product_id": 7, "price_brl": Decimal("100.00")})()
    offer = ExternalOffer("retailer", "https://example.test/p/7", Decimal("90"), date(2026, 11, 3), "new", "exact product and variant", 7, True, "provider-a")
    offer2 = ExternalOffer("retailer2", "https://example.test/p/7b", Decimal("91"), date(2026, 11, 3), "new", "exact product and variant", 7, True, "provider-b")
    assert ExactMatchMarketService(FakeExternalOfferProvider((offer, offer2))).compare(product) == (offer, offer2)
    assert product.price_brl == Decimal("100.00")


def test_mcp_only_dispatches_allowlisted_existing_tool():
    tools = ToolRegistry()
    tools.register(ToolSpec("product_detail", "detail", {"reference": {"type": "string"}}, ("reference",), lambda reference: {"reference": reference}))
    adapter = MCPAdapter(tools)
    assert adapter.call("product_detail", {"reference": "7"}).value == {"reference": "7"}
    assert adapter.call("shell_exec", {"command": "whoami"}).error == "unsupported operation"

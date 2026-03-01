import pytest

from virl.api.nso import NSO


class _Response:
    def __init__(self, payload=None):
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _new_nso(rfc8040=False):
    nso = NSO.__new__(NSO)
    nso._NSO__nso_host = "localhost"
    nso._NSO__nso_username = "admin"
    nso._NSO__nso_password = "admin"
    nso._NSO__rfc8040 = rfc8040
    return nso


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"links": {"restconf": [{"href": "/restconf"}]}}, True),
        ({"links": {"restconf": [{"href": "/other"}]}}, False),
        ({}, False),
    ],
)
def test_check_for_rfc8040_detection(monkeypatch, payload, expected):
    nso = _new_nso()
    monkeypatch.setattr(
        "virl.api.nso.requests.request",
        lambda *_args, **_kwargs: _Response(payload),
    )

    nso._NSO__check_for_rfc8040()

    assert nso._NSO__rfc8040 is expected


def test_build_ned_vars_uses_rfc8040_endpoints(monkeypatch):
    nso = _new_nso(rfc8040=True)
    urls = []

    def fake_request(method, url, **kwargs):
        urls.append((method, url, kwargs.get("headers", {})))
        if "ned-id" in url:
            return _Response({"tailf-ncs:ned-id": [{"id": "prefix1:cisco-ios-foo"}]})
        return _Response({"ietf-yang-library:module": [{"name": "cisco-ios-foo", "namespace": "urn:test"}]})

    monkeypatch.setattr("virl.api.nso.requests.request", fake_request)

    vars = nso._NSO__build_ned_vars()

    assert any("/restconf/data/tailf-ncs:devices/ned-ids/ned-id" in u for _, u, _ in urls)
    assert vars["IOS_PREFIX"] == "prefix1"
    assert vars["IOS_NED_ID"] == "cisco-ios-foo"
    assert vars["IOS_NAMESPACE"] == "urn:test"


def test_build_ned_vars_handles_non_matching_patterns_and_modules(monkeypatch):
    nso = _new_nso(rfc8040=True)

    def fake_request(_method, url, **_kwargs):
        if "ned-id" in url:
            return _Response(
                {
                    "tailf-ncs:ned-id": [
                        {"id": "p0:unknown-platform"},
                        {"id": "p1:cisco-ios-foo"},
                    ]
                }
            )
        return _Response(
            {
                "ietf-yang-library:module": [
                    {"name": "not-a-match", "namespace": "urn:other"},
                ]
            }
        )

    monkeypatch.setattr("virl.api.nso.requests.request", fake_request)

    vars = nso._NSO__build_ned_vars()

    # No module matched cisco-ios-foo, so default namespace remains.
    assert vars["IOS_PREFIX"] == "p1"
    assert vars["IOS_NED_ID"] == "cisco-ios-foo"
    assert vars["IOS_NAMESPACE"] == "urn:ios-id"


def test_perform_sync_from_uses_both_api_styles(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "virl.api.nso.requests.request",
        lambda method, url, **kwargs: captured.append((method, url, kwargs.get("headers"))) or _Response(),
    )

    nso = _new_nso(rfc8040=False)
    nso.perform_sync_from()
    nso._NSO__rfc8040 = True
    nso.perform_sync_from()

    assert captured[0][0] == "POST" and "/api/running/devices/_operations/sync-from" in captured[0][1]
    assert captured[1][0] == "POST" and "/restconf/operations/tailf-ncs:devices/tailf-ncs:sync-from" in captured[1][1]


def test_update_devices_renders_payload_with_ned_variables(monkeypatch):
    nso = _new_nso(rfc8040=False)
    monkeypatch.setattr(
        nso,
        "_NSO__build_ned_vars",
        lambda: {"IOS_PREFIX": "ios-id", "IOS_NED_ID": "cisco-ios", "IOS_NAMESPACE": "urn:ios-id"},
    )

    sent = {}

    def fake_request(method, url, **kwargs):
        sent["method"] = method
        sent["url"] = url
        sent["data"] = kwargs.get("data")
        sent["headers"] = kwargs.get("headers")
        return _Response()

    monkeypatch.setattr("virl.api.nso.requests.request", fake_request)

    payload = "<devices><name>{{ IOS_NED_ID }}</name></devices>"
    nso.update_devices(payload)

    assert sent["method"] == "PATCH"
    assert "/api/config/devices/" in sent["url"]
    assert "<name>cisco-ios</name>" in sent["data"]


def test_update_devices_uses_rfc8040_patch_endpoint(monkeypatch):
    nso = _new_nso(rfc8040=True)
    monkeypatch.setattr(
        nso,
        "_NSO__build_ned_vars",
        lambda: {"IOS_NED_ID": "cisco-ios"},
    )
    sent = {}

    def fake_request(method, url, **kwargs):
        sent["method"] = method
        sent["url"] = url
        sent["headers"] = kwargs.get("headers")
        return _Response()

    monkeypatch.setattr("virl.api.nso.requests.request", fake_request)

    nso.update_devices("<devices><name>{{ IOS_NED_ID }}</name></devices>")

    assert sent["method"] == "PATCH"
    assert "/restconf/data/tailf-ncs:devices" in sent["url"]
    assert sent["headers"]["Content-Type"] == "application/yang-data+xml"

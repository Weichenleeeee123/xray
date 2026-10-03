"""A stale browser owner cannot read or overwrite the current account library."""
import pytest

from app import accounts
from tests.test_accounts import isolated, register


ENDPOINT = "/api/me/library"
OWNER_HEADER = "X-Xray-Library-Owner"


def entry(identifier):
    return {
        "id": identifier,
        "term": f"Synthetic {identifier}",
        "plain": f"Private definition for {identifier}",
        "savedAt": "2026-10-04T00:00:00Z",
    }


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_stale_owner_header_cannot_access_another_accounts_library(isolated, monkeypatch, method):
    alice, bob = isolated(), isolated()
    register(alice, "alice@example.com")
    register(bob, "bob@example.com")
    alice_library = alice.put(ENDPOINT, json=[entry("alice-only")]).json()
    bob_library = bob.put(ENDPOINT, json=[entry("bob-only")]).json()

    def forbidden(*args, **kwargs):
        pytest.fail("A mismatched owner must be rejected before library storage access")

    with monkeypatch.context() as guarded:
        guarded.setattr(accounts, "library", forbidden)
        guarded.setattr(accounts, "save_library", forbidden)
        options = {"headers": {OWNER_HEADER: "alice@example.com"}}
        if method == "PUT":
            options["json"] = [entry("stale-alice-write")]
        response = bob.request(method, ENDPOINT, **options)
        assert response.status_code == 409, response.text
        assert "alice-only" not in response.text and "bob-only" not in response.text
        assert "stale-alice-write" not in response.text

    assert alice.get(ENDPOINT).json() == alice_library
    assert bob.get(ENDPOINT).json() == bob_library


def test_owner_header_email_matching_is_case_insensitive(isolated):
    client = isolated()
    register(client, "Alice@Example.com")
    headers = {OWNER_HEADER: "aLiCe@EXAMPLE.COM"}
    saved = client.put(ENDPOINT, headers=headers, json=[entry("matching-owner")])
    assert saved.status_code == 200, saved.text
    response = client.get(ENDPOINT, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == saved.json()
    assert response.json()[0]["id"] == "matching-owner"


def test_omitting_owner_header_preserves_existing_library_api(isolated):
    client = isolated()
    register(client, "legacy@example.com")
    saved = client.put(ENDPOINT, json=[entry("legacy-client")])
    assert saved.status_code == 200, saved.text
    response = client.get(ENDPOINT)
    assert response.status_code == 200, response.text
    assert response.json() == saved.json()
    assert response.json()[0]["id"] == "legacy-client"


@pytest.mark.parametrize("method", ["GET", "PUT"])
@pytest.mark.parametrize("headers", [{}, {OWNER_HEADER: "alice@example.com"}])
def test_owner_header_does_not_authenticate_a_guest(isolated, method, headers):
    client = isolated()
    options = {"headers": headers}
    if method == "PUT":
        options["json"] = [entry("guest-write")]
    response = client.request(method, ENDPOINT, **options)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_owner_header_rejects_more_than_254_characters(isolated, method):
    client = isolated()
    register(client, "alice@example.com")
    baseline = client.put(ENDPOINT, json=[entry("existing-entry")]).json()
    options = {"headers": {OWNER_HEADER: "a" * 255}}
    if method == "PUT":
        options["json"] = [entry("invalid-header-write")]
    response = client.request(method, ENDPOINT, **options)
    assert response.status_code == 422, response.text
    assert any(error["loc"] == ["header", "x-xray-library-owner"]
               for error in response.json()["detail"])
    assert client.get(ENDPOINT).json() == baseline

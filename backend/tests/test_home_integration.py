"""The built research room and the report app are served by one backend."""
import re

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_serves_research_home_and_its_built_assets():
    response = client.get('/')
    assert response.status_code == 200
    assert 'id="research-root"' in response.text
    assets = re.findall(r'(?:src|href)="(/office/assets/[^\"]+)"', response.text)
    assert len(assets) >= 2
    for path in assets:
        asset = client.get(path)
        assert asset.status_code == 200, path
        assert len(asset.content) > 100


def test_report_app_is_available_on_the_same_origin():
    response = client.get('/xray/')
    assert response.status_code == 200
    assert 'id="view"' in response.text
    for filename in ('app.js', 'style.css', 'research-progress.js', 'research-progress.css'):
        assert client.get('/xray/' + filename).status_code == 200
    for name in ('office-panorama-closed.png', 'xiaoqi-walk-cycles.png', 'investigation-dossier.png'):
        assert client.get('/research-assets/' + name).status_code == 200


def test_home_mount_does_not_expose_frontend_source_or_secrets():
    for path in ('/office/.env', '/office/package.json', '/office/app/page.tsx', '/research-assets/.env'):
        assert client.get(path).status_code == 404
    assert client.get('/api/health').json()['ok']
    assert client.get('/demo/').status_code == 200


def test_dossier_report_assets_are_served_from_real_backend():
    page = client.get('/xray/').text
    assets = re.findall(r'(?:src|href)="((?:dossier/|dossier-report\.js)[^\"]+)"', page)
    assert len(assets) == 13
    assert any(path.startswith('dossier/signal-details.css?') for path in assets)
    for path in assets:
        response = client.get('/xray/' + path)
        assert response.status_code == 200, path
        assert len(response.content) > 100
    for filename in ('kraft-grain.svg', 'xiaoqi-original.webp'):
        assert client.get('/xray/dossier/assets/' + filename).status_code == 200

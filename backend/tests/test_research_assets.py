from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_waiting_animation_assets_are_served_without_exposing_project_files():
    for name in ('research-room-v2.png', 'goose-actions-v2.png'):
        response = client.get('/research-assets/' + name)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
    for name in ('.env', 'package.json', 'app/page.tsx'):
        assert client.get('/research-assets/' + name).status_code == 404

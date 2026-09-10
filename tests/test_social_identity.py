import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/web'))
import access


def principal(provider, subject):
    doc = {'auth_typ': provider, 'userDetails': 'same@example.com',
           'claims': [{'typ': 'sub', 'val': subject}]}
    return access.principal({'x-ms-client-principal': base64.b64encode(json.dumps(doc).encode()).decode()})[0]


def test_external_identity_does_not_collide_with_existing_email_owner():
    google = principal('google', '123')
    github = principal('github', '123')
    assert google is None and github is None
    assert principal('aad', '123') == 'same@example.com'


def test_anonymous_visibility_is_denied_outside_explicit_local_test_mode(monkeypatch):
    monkeypatch.delenv('LANDFALL_LOCAL_AUTH', raising=False)
    assert not access.can_view({'visibility': 'all'}, None)
    assert not access.can_view({'visibility': 'owner'}, None)

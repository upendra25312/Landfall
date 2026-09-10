import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/web'))
import direct_uploads as direct


def ticket(actor='owner', eid='acme/project', size=20):
    return {'actor': actor, 'engagement': eid, 'size': size, 'name': 'servers.csv', 'kind': 'auto',
            'staging': 'pending-uploads/acme/project/nonce/servers.csv',
            'expires': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).isoformat()}


def container(monkeypatch, record):
    cc = Mock()
    cc.download_blob.return_value.readall.return_value = json.dumps(record).encode()
    monkeypatch.setattr(direct.web_storage, '_raw_container', lambda: cc)
    monkeypatch.setattr(direct, '_sas', lambda *args: 'https://storage.example/raw/pending?redacted')
    return cc


@pytest.mark.parametrize('actor,eid', [('another-user', 'acme/project'), ('owner', 'other/project')])
def test_ticket_cannot_cross_user_or_engagement(monkeypatch, actor, eid):
    cc = container(monkeypatch, ticket())
    with pytest.raises(ValueError):
        direct.complete_ticket(eid, actor, 'a'*32)
    cc.get_blob_client.assert_not_called()


def test_copy_is_conditioned_on_the_validated_source_version(monkeypatch):
    cc = container(monkeypatch, ticket())
    staging, target = Mock(), Mock()
    cc.get_blob_client.side_effect = [staging, target]
    staging.get_blob_properties.return_value = SimpleNamespace(size=20, etag='validated-etag')
    staging.download_blob.return_value.readall.return_value = b'hostname,vcpu\na,2\n'
    target.start_copy_from_url.return_value = {'copy_status': 'success'}
    result = direct.complete_ticket('acme/project', 'owner', 'a'*32)
    assert target.start_copy_from_url.call_args.kwargs['source_etag'] == 'validated-etag'
    assert target.start_copy_from_url.call_args.kwargs['requires_sync'] is True
    assert result['path'] == 'raw/engagements/acme/project/inventory/servers.csv'


def test_binary_disguised_as_csv_is_never_promoted(monkeypatch):
    cc = container(monkeypatch, ticket())
    source = cc.get_blob_client.return_value
    source.get_blob_properties.return_value = SimpleNamespace(size=20, etag='bad')
    source.download_blob.return_value.readall.return_value = b'\x00MZexecutable'
    with pytest.raises(ValueError):
        direct.complete_ticket('acme/project', 'owner', 'a'*32)
    source.start_copy_from_url.assert_not_called()


def test_oversized_ticket_does_not_create_blob(monkeypatch):
    cc = container(monkeypatch, ticket())
    with pytest.raises(ValueError):
        direct.create_ticket('acme/project', 'owner', {'name': 'big.csv', 'size': 101*1024*1024})
    cc.upload_blob.assert_not_called()

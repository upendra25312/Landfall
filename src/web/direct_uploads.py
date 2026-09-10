"""Short-lived single-blob upload tickets; only validated bytes reach ingestion."""
import datetime as dt
import json
import re
import uuid

from azure.core import MatchConditions
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas

import uploads
import web_runtime
import web_storage


def _service():
    return BlobServiceClient(web_runtime.STORAGE_URL, credential=web_runtime._cred)


def _sas(blob_name, permission):
    now = dt.datetime.now(dt.timezone.utc)
    service = _service()
    expires = now + dt.timedelta(minutes=10)
    key = service.get_user_delegation_key(now - dt.timedelta(minutes=1), expires)
    token = generate_blob_sas(service.account_name, 'raw', blob_name,
                              user_delegation_key=key, permission=permission,
                              start=now - dt.timedelta(minutes=1), expiry=expires, protocol='https')
    return f'{service.url.rstrip("/")}/raw/{blob_name}?{token}'


def create_ticket(eid, actor, body):
    size = body.get('size')
    name = uploads.safe_name(body.get('name') or '')
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= uploads.MAX_FILE:
        raise ValueError('Upload size must be between 1 byte and 100 MB')
    kind = body.get('kind', 'auto')
    if kind not in ('auto', 'inventory', 'docs'):
        raise ValueError('Invalid upload classification')
    ticket = uuid.uuid4().hex
    staging = f'pending-uploads/{eid}/{ticket}/{name}'
    record = {'engagement': eid, 'actor': actor, 'name': name, 'size': size,
              'kind': kind, 'staging': staging,
              'expires': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat()}
    web_storage._raw_container().upload_blob(f'upload-tickets/{ticket}.json', json.dumps(record).encode())
    return {'ticket': ticket, 'url': _sas(staging, BlobSasPermissions(create=True, write=True)),
            'expires': record['expires']}


def complete_ticket(eid, actor, ticket):
    if not re.fullmatch('[0-9a-f]{32}', ticket or ''):
        raise ValueError('Invalid upload ticket')
    cc = web_storage._raw_container()
    record = json.loads(cc.download_blob(f'upload-tickets/{ticket}.json').readall())
    if record['engagement'] != eid or record['actor'] != actor:
        raise ValueError('Upload ticket does not belong to this user and engagement')
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(record['expires']):
        raise ValueError('Upload ticket expired; start a new upload')
    blob = cc.get_blob_client(record['staging'])
    props = blob.get_blob_properties()
    if props.size != record['size'] or props.size > uploads.MAX_FILE:
        raise ValueError('Uploaded size differs from the approved ticket')
    head = blob.download_blob(offset=0, length=min(props.size, 4096),
                              etag=props.etag, match_condition=MatchConditions.IfNotModified).readall()
    ok, detected, reason = uploads.classify(record['name'], head)
    if not ok:
        raise ValueError(reason)
    kind = detected if record['kind'] == 'auto' else record['kind']
    target = f'engagements/{eid}/{kind}/{record["name"]}'
    metadata = {'uploaded_by': actor, 'kind': kind, 'profile': '', 'rows': '0', 'columns': '0'}
    result = cc.get_blob_client(target).start_copy_from_url(
        _sas(record['staging'], BlobSasPermissions(read=True)), metadata=metadata,
        requires_sync=True, source_etag=props.etag, source_match_condition=MatchConditions.IfNotModified)
    if result['copy_status'] != 'success':
        raise RuntimeError('Upload validation completed but storage copy did not finish')
    # Delete only this generated staging blob, never a customer destination.
    blob.delete_blob(etag=props.etag, match_condition=MatchConditions.IfNotModified)
    cc.delete_blob(f'upload-tickets/{ticket}.json')
    return {'name': record['name'], 'size': props.size, 'kind': kind, 'engagement': eid,
            'path': 'raw/' + target, 'profile': '', 'rows': 0, 'columns': 0}

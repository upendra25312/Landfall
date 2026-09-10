"""Fixed assessment sequence. Tools calculate; the model cannot skip stages."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid

import azure.functions as func

from cost.config import load_config
from deliverable.assemble import assemble_estimate
from engagement import normalize_engagement
from lz.design import design_landing_zone
from waves.disposition import score_dispositions
from waves.plan import plan_waves

assessment_bp = func.Blueprint()


def invoke(handler, body, headers=None):
    req = func.HttpRequest('POST', '/', headers=headers or {}, params={},
                           body=json.dumps(body, default=str).encode())
    response = handler(req)
    payload = json.loads(response.get_body())
    if response.status_code >= 400 or payload.get('error'):
        raise RuntimeError(payload.get('error', f'Tool failed: {response.status_code}'))
    return payload


def run_assessment(engagement, backend, *, config=None, generated_on=None, run_id=None):
    """Backend owns I/O. Every stage is persisted; failures retain prior outputs."""
    eid = normalize_engagement(engagement)
    date = generated_on or dt.date.today().isoformat()
    dt.date.fromisoformat(date)
    cfg = load_config(overrides=config)
    record = {'engagement': eid, 'run_id': run_id or uuid.uuid4().hex,
              'status': 'running', 'stages': [], 'generated_on': date, 'outputs': {}}
    outputs = record['outputs']

    def stage(name, operation):
        entry = {'name': name, 'status': 'running'}
        record['stages'].append(entry)
        backend.save(record)
        try:
            value = operation()
            outputs[name] = value
            entry['status'] = 'completed'
            backend.save(record)
            return value
        except Exception as exc:
            entry.update(status='failed', error=str(exc))
            record.update(status='failed', failed_stage=name)
            backend.save(record)
            raise

    try:
        stage('validate', lambda: backend.validate(eid))
        ingestion = stage('ingest', lambda: backend.ingest(eid))
        data = stage('inventory', lambda: backend.inventory(eid))
        servers, apps = data['servers'], data['applications']

        def quality():
            if not servers or not apps:
                raise ValueError('Full assessment requires server and application inventory')
            bad = [f for f in ingestion.get('files', [])
                   if str(f.get('status', '')).lower().startswith(('error', 'reject', 'fail'))]
            if bad:
                raise ValueError('Inventory ingestion failed; resolve the data-quality report first')
            return backend.quality(eid, ingestion)

        dq = stage('data_quality', quality)
        summary = {'servers': len(servers), 'applications': len(apps),
                   'total_vcpu': sum(float(s.get('vcpu') or 0) for s in servers),
                   'total_ram_gb': sum(float(s.get('ram_gb') or 0) for s in servers)}
        common = {'engagement': eid, 'config': cfg}
        stage('rightsize', lambda: backend.tool('rightsize', {**common, 'servers': servers}))
        compute = stage('compute_cost', lambda: backend.tool('compute_cost', {**common, 'servers': servers}))
        storage = stage('storage_cost', lambda: backend.tool('storage_cost', {**common, 'storage': data['storage']}))

        def extras():
            if compute.get('missing_prices') or storage.get('not_costed'):
                raise ValueError('Pricing coverage is incomplete; no full estimate published')
            return backend.tool('run_rate_extras', {**common, 'servers': servers,
                'monthly_infra_cost': compute['totals']['monthly'] + storage['totals']['monthly'],
                'price_date': compute.get('price_date')})

        stage('run_rate_extras', extras)
        roll = {}
        for server in servers:
            group = roll.setdefault(server.get('app_id'), {'servers': 0, 'eol_servers': 0})
            group['servers'] += 1
            group['eol_servers'] += bool(server.get('os_eol_date') and str(server['os_eol_date']) < date)
        dispositions = stage('dispositions', lambda: score_dispositions(apps, roll, cfg))
        waves = stage('waves', lambda: plan_waves(apps, servers, data['dependencies'], cfg,
                                                 dispositions['dispositions'], date, as_of=date))
        stage('schedule', lambda: waves['schedule'])
        design = stage('landing_zone', lambda: design_landing_zone(apps, {'total_servers': len(servers)}, cfg))
        from lz.diagram import build_drawio, build_svg
        stage('diagram', lambda: {'drawio': build_drawio(design), 'svg': build_svg(design)})
        inputs = {**outputs, 'engagement': eid, 'config': cfg,
                  'inventory_summary': summary, 'data_quality': dq, 'generated_on': date,
                  'discovery': backend.discovery(eid)}
        package = stage('assemble', lambda: assemble_estimate(inputs, cfg))
        stage('effort', lambda: next(s['body'] for s in package['sections'] if s['key'] == 'migration_effort'))
        record['input_sha256'] = hashlib.sha256(json.dumps(
            {'inventory': data, 'config': cfg, 'date': date, 'prices': [compute, storage]},
            sort_keys=True, default=str).encode()).hexdigest()
        stage('publish', lambda: backend.publish({**inputs, 'package': package}))
        record['status'] = 'completed'
        backend.save(record)
    except Exception:
        if record['status'] != 'failed':
            record.update(status='failed', failed_stage='record_or_input')
        # A failed save must not be reported as a successful assessment.
    return record


class AzureBackend:
    def __init__(self, headers=None):
        self.headers = headers or {}

    def validate(self, eid):
        from ingest.functions import _blob
        manifest = json.loads(_blob().get_blob_client('raw', f'engagements/{eid}/_engagement.json').download_blob().readall())
        return {'exists': bool(manifest)}

    def ingest(self, eid):
        from ingest.functions import run_engagement
        return invoke(run_engagement, {'engagement': eid}, self.headers)

    def inventory(self, eid):
        from tools import _sql_connect
        from engagement_sql import set_engagement
        result = {}
        conn = _sql_connect()
        try:
            cur = conn.cursor()
            set_engagement(cur, eid)
            for table, maximum in [('servers', 2000), ('applications', 2000),
                                    ('dependencies', 200000), ('storage', 5000)]:
                cur.execute(f'SELECT TOP ({maximum + 1}) * FROM dbo.{table}')
                cols = [c[0] for c in cur.description]
                rows = [{k: v for k, v in zip(cols, r) if k not in ('ingested_at', 'dep_id', 'perf_id')}
                        for r in cur.fetchall()]
                if len(rows) > maximum:
                    raise ValueError(f'{table} exceeds supported assessment size; refusing truncation')
                result[table] = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))
            return result
        finally:
            conn.close()

    def quality(self, eid, ingestion):
        ranks = {'Low': 0, 'Medium': 1, 'High': 2}
        files = ingestion.get('files', [])
        confidence = min((f.get('confidence_hint', 'Low') for f in files),
                         key=lambda c: ranks.get(c, 0), default='Low')
        return {'confidence': confidence, 'findings': [v for f in files for v in f.get('findings', [])]}

    def tool(self, name, body):
        from cost import functions as costs
        functions = {'rightsize': costs.vm_rightsize, 'compute_cost': costs.estimate_compute_cost_route,
                     'storage_cost': costs.estimate_storage_cost_route,
                     'run_rate_extras': costs.estimate_run_rate_extras_route}
        return invoke(functions[name], body, self.headers)

    def discovery(self, eid):
        from deliverable.functions import _discovery_for
        return _discovery_for(eid)

    def publish(self, body):
        from deliverable.functions import publish_estimate_route
        return invoke(publish_estimate_route, {**body, '_idempotent': True}, self.headers)

    def save(self, record):
        from deliverable.functions import _container_client
        cc = _container_client()
        prefix = f"engagements/{record['engagement']}/assessment"
        payload = json.dumps(record, default=str).encode()
        cc.upload_blob(f"{prefix}/{record['run_id']}.json", payload, overwrite=True)
        cc.upload_blob(f'{prefix}/latest.json', payload, overwrite=True)


@assessment_bp.route(route='run_assessment', methods=['POST'], auth_level=func.AuthLevel.ANONYMOUS)
def run_assessment_route(req):
    try:
        body = req.get_json()
        eid = normalize_engagement(body['engagement'])
        result = run_assessment(eid, AzureBackend(req.headers), config=body.get('config'))
        summary = {k: v for k, v in result.items() if k != 'outputs'}
        summary['dashboard_hint'] = f'/e/{eid}'
        return func.HttpResponse(json.dumps(summary), status_code=200 if result['status'] == 'completed' else 422,
                                 mimetype='application/json')
    except (ValueError, KeyError, TypeError):
        return func.HttpResponse(json.dumps({'error': 'A valid engagement is required'}),
                                 status_code=400, mimetype='application/json')

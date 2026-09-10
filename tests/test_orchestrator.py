"""Acceptance tests for E13.14 deterministic assessment orchestrator (run_assessment).

Verifies byte-identical repeatability, fixed stage sequence progression,
partial result preservation on failure, and HTTP endpoint contract.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import azure.functions as func

from assessment import run_assessment, run_assessment_route
from cost.config import load_config
from cost.compute_cost import estimate_compute_cost
from cost.storage_cost import estimate_storage_cost
from cost.run_rate import estimate_run_rate_extras
from cost.rightsize import rightsize_many

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
from fixtures import load, price_book, disk_book, storage_rates


EXPECTED_STAGE_SEQUENCE = [
    'validate',
    'ingest',
    'inventory',
    'data_quality',
    'rightsize',
    'compute_cost',
    'storage_cost',
    'run_rate_extras',
    'dispositions',
    'waves',
    'schedule',
    'landing_zone',
    'diagram',
    'assemble',
    'effort',
    'publish',
]


class MockAssessmentBackend:
    """Offline adapter mimicking AzureBackend for determinism testing."""

    def __init__(self, fail_at: str | None = None, ingestion_files: list | None = None):
        self.fail_at = fail_at
        self.ingestion_files = ingestion_files or []
        self.saved_records: list[dict] = []
        self.published_packages: list[dict] = []

    def save(self, record: dict):
        self.saved_records.append(copy.deepcopy(record))

    def validate(self, eid: str):
        if self.fail_at == 'validate':
            raise ValueError('Engagement manifest validation failed')
        return {'exists': True}

    def ingest(self, eid: str):
        if self.fail_at == 'ingest':
            raise RuntimeError('Ingestion pipeline failed')
        return {'files': self.ingestion_files}

    def inventory(self, eid: str):
        if self.fail_at == 'inventory':
            raise RuntimeError('Database connection timeout')
        return {
            table: load(table)
            for table in ('servers', 'applications', 'storage', 'dependencies')
        }

    def quality(self, eid: str, ingestion: dict):
        if self.fail_at == 'data_quality':
            raise ValueError('Data quality check rejected')
        return {'confidence': 'High', 'findings': []}

    def discovery(self, eid: str):
        return None

    def tool(self, name: str, body: dict):
        if name == self.fail_at:
            raise RuntimeError(f'Simulated failure in tool {name}')
        cfg = load_config()
        date = '2026-06-01'
        handlers = {
            'rightsize': lambda: rightsize_many(body['servers'], cfg),
            'compute_cost': lambda: estimate_compute_cost(body['servers'], price_book(), disk_book(), cfg, date),
            'storage_cost': lambda: estimate_storage_cost(body['storage'], storage_rates(), cfg, date),
            'run_rate_extras': lambda: estimate_run_rate_extras(body['servers'], body['monthly_infra_cost'], cfg, date),
        }
        return handlers[name]()

    def publish(self, body: dict):
        if self.fail_at == 'publish':
            raise RuntimeError('Storage blob upload failed')
        self.published_packages.append(copy.deepcopy(body))
        return {'published': ['latest.json', 'latest.xlsx', 'latest.docx', 'latest.pptx']}


def test_orchestrator_deterministic_byte_identical_reproducibility():
    """Identical input yields byte-identical latest.json content across runs."""
    backend_a = MockAssessmentBackend()
    backend_b = MockAssessmentBackend()

    result_a = run_assessment('acme/migration', backend_a, generated_on='2026-09-10', run_id='fixed-run-id')
    result_b = run_assessment('acme/migration', backend_b, generated_on='2026-09-10', run_id='fixed-run-id')

    assert result_a['status'] == 'completed'
    assert result_b['status'] == 'completed'
    assert result_a['input_sha256'] == result_b['input_sha256']

    # Compare serialized latest.json representations
    latest_a_bytes = json.dumps(backend_a.saved_records[-1], sort_keys=True).encode()
    latest_b_bytes = json.dumps(backend_b.saved_records[-1], sort_keys=True).encode()
    assert latest_a_bytes == latest_b_bytes

    # Assert published packages are identical
    pub_a = json.dumps(backend_a.published_packages[0], sort_keys=True)
    pub_b = json.dumps(backend_b.published_packages[0], sort_keys=True)
    assert pub_a == pub_b


def test_orchestrator_fixed_stage_sequence():
    """Pipeline strictly executes and records all 16 stages in fixed order."""
    backend = MockAssessmentBackend()
    result = run_assessment('contoso/hybrid', backend, generated_on='2026-09-10')

    assert result['status'] == 'completed'
    recorded_stages = [s['name'] for s in result['stages']]
    assert recorded_stages == EXPECTED_STAGE_SEQUENCE

    for stage in result['stages']:
        assert stage['status'] == 'completed'

    # Check key outputs were populated in record
    outputs = result['outputs']
    for key in ('validate', 'ingest', 'inventory', 'data_quality', 'rightsize',
                'compute_cost', 'storage_cost', 'run_rate_extras', 'dispositions',
                'waves', 'schedule', 'landing_zone', 'diagram', 'assemble', 'effort', 'publish'):
        assert key in outputs, f'Expected output for stage {key}'


def test_orchestrator_mid_pipeline_failure_retains_completed_stages():
    """Mid-pipeline failure stops execution, records failed stage, and preserves completed work."""
    backend = MockAssessmentBackend(fail_at='compute_cost')
    result = run_assessment('acme/fail-cost', backend, generated_on='2026-09-10')

    assert result['status'] == 'failed'
    assert result['failed_stage'] == 'compute_cost'

    # Stages before compute_cost must be retained and marked completed
    completed_names = [s['name'] for s in result['stages'] if s['status'] == 'completed']
    assert completed_names == ['validate', 'ingest', 'inventory', 'data_quality', 'rightsize']

    # Outputs of completed stages are preserved
    assert 'rightsize' in result['outputs']
    assert 'recommendations' in result['outputs']['rightsize']

    # Downstream stages must NOT have run and deliverables must NEVER be published
    assert 'waves' not in result['outputs']
    assert len(backend.published_packages) == 0
    assert backend.saved_records[-1]['status'] == 'failed'


def test_orchestrator_dispositions_failure_preserves_cost_stages(monkeypatch):
    """Failure at dispositions preserves prior rightsizing and pricing results."""
    backend = MockAssessmentBackend(fail_at='dispositions')
    import assessment
    def broken_score(*args, **kwargs):
        raise RuntimeError('Disposition engine failure')
    monkeypatch.setattr(assessment, 'score_dispositions', broken_score)

    result = run_assessment('acme/fail-disp', backend, generated_on='2026-09-10')
    assert result['status'] == 'failed'
    assert result['failed_stage'] == 'dispositions'
    assert 'compute_cost' in result['outputs']
    assert 'storage_cost' in result['outputs']
    assert 'run_rate_extras' in result['outputs']
    assert len(backend.published_packages) == 0


def test_orchestrator_data_quality_rejection_prevents_costing():
    """Failed ingestion or missing required inventory fails DQ stage immediately."""
    bad_files = [{'name': 'servers.csv', 'status': 'rejected', 'error': 'corrupt headers'}]
    backend = MockAssessmentBackend(ingestion_files=bad_files)

    result = run_assessment('acme/bad-data', backend, generated_on='2026-09-10')
    assert result['status'] == 'failed'
    assert result['failed_stage'] == 'data_quality'
    assert 'compute_cost' not in result['outputs']
    assert len(backend.published_packages) == 0


def test_orchestrator_optional_storage_records_zero_cost():
    """Missing storage rows record zero-valued storage rather than failing assessment."""
    backend = MockAssessmentBackend()
    orig_inv = backend.inventory
    backend.inventory = lambda eid: {**orig_inv(eid), 'storage': []}

    result = run_assessment('acme/no-storage', backend, generated_on='2026-09-10')
    assert result['status'] == 'completed'
    assert result['outputs']['storage_cost']['totals']['monthly'] == 0
    assert len(backend.published_packages) == 1


def test_orchestrator_http_route_success(monkeypatch):
    """POST /api/run_assessment returns 200 with summary and dashboard_hint on success."""
    import assessment
    test_backend = MockAssessmentBackend()
    monkeypatch.setattr(assessment, 'AzureBackend', lambda headers: test_backend)

    req = func.HttpRequest(
        method='POST',
        url='/api/run_assessment',
        body=json.dumps({'engagement': 'acme/cloud-migration'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    resp = run_assessment_route(req)
    assert resp.status_code == 200
    payload = json.loads(resp.get_body())
    assert payload['status'] == 'completed'
    assert payload['engagement'] == 'acme/cloud-migration'
    assert payload['dashboard_hint'] == '/e/acme/cloud-migration'
    assert 'outputs' not in payload  # outputs stripped from HTTP summary


def test_orchestrator_http_route_validation_error():
    """POST /api/run_assessment returns 400 on missing or malformed engagement."""
    req = func.HttpRequest(
        method='POST',
        url='/api/run_assessment',
        body=json.dumps({}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    resp = run_assessment_route(req)
    assert resp.status_code == 400
    payload = json.loads(resp.get_body())
    assert 'error' in payload


def test_orchestrator_http_route_failure_status_code(monkeypatch):
    """POST /api/run_assessment returns 422 when a pipeline stage fails."""
    import assessment
    test_backend = MockAssessmentBackend(fail_at='rightsize')
    monkeypatch.setattr(assessment, 'AzureBackend', lambda headers: test_backend)

    req = func.HttpRequest(
        method='POST',
        url='/api/run_assessment',
        body=json.dumps({'engagement': 'acme/failing-pipeline'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    resp = run_assessment_route(req)
    assert resp.status_code == 422
    payload = json.loads(resp.get_body())
    assert payload['status'] == 'failed'
    assert payload['failed_stage'] == 'rightsize'
    assert payload['dashboard_hint'] == '/e/acme/failing-pipeline'

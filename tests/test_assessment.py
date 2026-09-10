"""Full pipeline uses real deterministic engines with offline I/O adapters."""
import copy
import json
import sys
from pathlib import Path

from assessment import run_assessment
from cost.config import load_config
from cost.compute_cost import estimate_compute_cost
from cost.storage_cost import estimate_storage_cost
from cost.run_rate import estimate_run_rate_extras
from cost.rightsize import rightsize_many

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
from fixtures import load, price_book, disk_book, storage_rates


class Backend:
    def __init__(self, fail=None):
        self.fail = fail
        self.saved = []
        self.published = []

    def save(self, record):
        self.saved.append(copy.deepcopy(record))

    def validate(self, eid):
        return {'exists': True}

    def ingest(self, eid):
        return {'files': []}

    def inventory(self, eid):
        return {table: load(table) for table in ('servers', 'applications', 'storage', 'dependencies')}

    def quality(self, eid, ingestion):
        return {'confidence': 'Medium', 'findings': []}

    def discovery(self, eid):
        return None

    def tool(self, name, body):
        if name == self.fail:
            raise RuntimeError('Injected provider timeout')
        cfg = load_config()
        return {
            'rightsize': lambda: rightsize_many(body['servers'], cfg),
            'compute_cost': lambda: estimate_compute_cost(body['servers'], price_book(), disk_book(), cfg, '2026-06-01'),
            'storage_cost': lambda: estimate_storage_cost(body['storage'], storage_rates(), cfg, '2026-06-01'),
            'run_rate_extras': lambda: estimate_run_rate_extras(body['servers'], body['monthly_infra_cost'], cfg, '2026-06-01'),
        }[name]()

    def publish(self, body):
        self.published.append(copy.deepcopy(body))
        return {'published': ['latest.json', 'latest.xlsx', 'latest.docx', 'latest.pptx']}


def test_full_assessment_is_reproducible_and_records_stages():
    a, b = Backend(), Backend()
    first = run_assessment('acme/project', a, generated_on='2026-09-10')
    second = run_assessment('acme/project', b, generated_on='2026-09-10')
    assert first['status'] == second['status'] == 'completed', first
    assert first['input_sha256'] == second['input_sha256']
    assert json.dumps(a.published[0], sort_keys=True) == json.dumps(b.published[0], sort_keys=True)
    assert all(s['status'] == 'completed' for s in first['stages'])
    assert a.published[0]['engagement'] == 'acme/project'


def test_cost_failure_retains_completed_stages_and_never_publishes():
    backend = Backend('compute_cost')
    result = run_assessment('acme/project', backend)
    assert result['status'] == 'failed'
    assert result['failed_stage'] == 'compute_cost'
    assert result['outputs']['rightsize']['recommendations']
    assert not backend.published
    assert backend.saved[-1]['status'] == 'failed'


def test_missing_inventory_never_becomes_full_estimate():
    backend = Backend()
    backend.inventory = lambda eid: {'servers': [], 'applications': [], 'storage': [], 'dependencies': []}
    result = run_assessment('acme/project', backend)
    assert result['failed_stage'] == 'data_quality'
    assert not backend.published


def test_storage_inventory_is_optional_and_records_zero_cost():
    backend = Backend()
    original = backend.inventory
    backend.inventory = lambda eid: {**original(eid), 'storage': []}
    result = run_assessment('acme/project', backend, generated_on='2026-09-10')
    assert result['status'] == 'completed'
    assert result['outputs']['storage_cost']['totals']['monthly'] == 0
    assert result['outputs']['storage_cost']['line_items'] == []
    assert len(backend.published) == 1

"""C52: preserve the pre-refactor HTTP contract and enforce the router boundary."""
import ast
import json
import sys
from pathlib import Path

from conftest import ROOT

WEB = Path(ROOT) / "src/web"
sys.path.insert(0, str(WEB))


def test_openapi_matches_the_c51_contract():
    import app

    baseline = Path(ROOT) / "tests/fixtures/web_openapi_c51.json"
    original = json.loads(baseline.read_text(encoding='utf-8'))
    current = json.loads(json.dumps(app.app.openapi()))
    current['paths'] = {path: current['paths'][path] for path in original['paths']}
    for path in ('/dashboard/landing-zone', '/dashboard/landing-zone-diagram'):
        current['paths'][path]['get']['parameters'] = [p for p in current['paths'][path]['get']['parameters']
                                                       if p['name'] != 'optional']
    assert current == original


def test_entrypoint_and_routers_stay_within_the_prd_limits():
    assert len((WEB / "app.py").read_text(encoding="utf-8").splitlines()) < 150
    routes = list((WEB / "routes").glob("*.py"))
    assert len(routes) > 1
    for path in routes:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) < 300, path
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                assert all(alias.name != "app" for alias in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "app", path


def test_every_application_route_is_registered_once_from_a_router():
    import app
    from fastapi.routing import APIRoute

    routes = [route for route in app.app.routes if isinstance(route, APIRoute)]
    signatures = [(method, route.path) for route in routes for method in route.methods]
    assert len(signatures) == len(set(signatures)) == 40
    assert all(route.endpoint.__module__.startswith("routes.") for route in routes)

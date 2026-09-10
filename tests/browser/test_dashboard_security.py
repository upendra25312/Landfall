import os
from pathlib import Path
from playwright.sync_api import expect


def test_populated_dashboard_and_questionnaire_use_strict_csp(page, base_url, console_errors):
    response = page.goto(base_url + '/dashboard?e=contoso-ltd/dc-exit', wait_until='networkidle')
    assert 'unsafe-inline' not in response.headers['content-security-policy']
    expect(page.locator('#root')).to_contain_text('Migration estimate')
    assert page.locator('#root .card').count() > 0
    if folder := os.environ.get('C53_SCREENSHOT_DIR'):
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / 'dashboard-strict.png'), full_page=True)
    response = page.goto(base_url + '/questionnaire', wait_until='networkidle')
    assert 'unsafe-inline' not in response.headers['content-security-policy']
    expect(page.locator('h1')).to_be_visible()
    assert console_errors == []


def test_dashboard_sanitizes_untrusted_html(page, base_url, console_errors):
    page.goto(base_url + '/dashboard?e=contoso-ltd/dc-exit', wait_until='networkidle')
    result = page.evaluate('''() => {
      const node = document.createElement('div');
      safeSetHTML(node, '<img onerror="window.attacked=true"><a href="javascript:alert(1)">x</a>');
      document.body.append(node);
      return {handler: node.querySelector('img').getAttribute('onerror'),
              href: node.querySelector('a').getAttribute('href')};
    }''')
    assert result == {'handler': None, 'href': None}
    assert console_errors == []

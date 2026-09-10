"""C53: browser journeys for create/upload/analysis and specific downloads."""
import io
import os
import re
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import expect

from .test_chat_page import _goto, _select


def test_create_upload_analyse_and_prompt_card(page, base_url, console_errors):
    _goto(page, base_url)
    page.click("#neweng")
    page.fill("input[name=customer]", "Validation C53")
    page.fill("input[name=project]", "Browser journey")
    page.click("#ef button[type=submit]")
    expect(page.locator("#engsel")).to_have_value("validation-c53/browser-journey")
    expect(page.locator("#pipeline .step.done")).to_have_count(0)
    page.locator("#ufile").set_input_files({"name": "servers.csv", "mimeType": "text/csv", "buffer": (
        b"server_id,hostname,env,os_name,vcpu,ram_gb,provisioned_disk_gb,used_disk_gb,powerstate\n"
        b"s1,web01,prod,Ubuntu,2,16,128,90,poweredOn\n")})
    expect(page.locator("#filerows")).to_contain_text("servers.csv")
    expect(page.locator("#startanalysis")).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith("/analyze") and r.request.method == "POST") as response:
        page.click("#startanalysis")
    assert response.value.status == 200
    expect(page.locator("#dqsummary")).to_contain_text("1 rows")
    expect(page.locator("#pipeline .step.done")).to_have_count(2)
    page.get_by_role("button", name=re.compile(r"Full (assessment|estimate)")).click()
    expect(page.locator("#log")).to_contain_text("Here is the full estimate")
    expect(page.get_by_role("button", name="Download as Excel")).to_be_visible()
    page.reload(wait_until="networkidle")
    expect(page.locator("#log")).to_contain_text("Here is the full estimate")
    assert console_errors == []
    if folder := os.environ.get("C53_SCREENSHOT_DIR"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / "create-upload-analysis.png"), full_page=True)


def test_empty_engagement_does_not_display_another_estate_as_published(page, base_url, console_errors):
    _goto(page, base_url)
    _select(page, "northwind/pilot")
    expect(page.locator("#pipeline .step.done")).to_have_count(0)
    response = page.request.get(base_url + "/dashboard/data?e=northwind/pilot")
    assert response.status == 404
    questionnaire = page.request.get(base_url + "/questionnaire.xlsx?e=northwind/pilot")
    assert questionnaire.status == 200
    workbook = load_workbook(io.BytesIO(questionnaire.body()))
    assert workbook.sheetnames
    workbook.close()
    assert console_errors == []


def test_throttled_agent_keeps_conversation_and_shows_recovery(page, base_url, console_errors):
    _goto(page, base_url)
    _select(page, 'contoso-ltd/dc-exit')
    page.route('**/api/chat', lambda route: route.fulfill(status=429, content_type='application/json',
        body='{"error":"The agent is busy. Please retry shortly; saved results are preserved."}'))
    page.locator('#q').fill('Count the servers')
    page.locator('#f').evaluate('(form) => form.requestSubmit()')
    expect(page.locator('#log')).to_contain_text('The agent is busy')
    expect(page.locator('#log')).to_contain_text('Count the servers')
    # The injected HTTP failure produces one browser network diagnostic; there
    # must still be no script exception, CSP failure or unrelated network error.
    assert console_errors == ['error: Failed to load resource: the server responded with a status of 429 (Too Many Requests)']


def test_large_upload_uses_ticket_storage_and_validation(page, base_url, console_errors):
    import json
    _goto(page, base_url)
    _select(page, 'contoso-ltd/dc-exit')
    page.evaluate('window._directUploads=true')
    seen = []

    def ticket(route):
        seen.append(('ticket', route.request.post_data_json['size']))
        route.fulfill(status=200, content_type='application/json', body=json.dumps({
            'ticket': 'a'*32, 'url': base_url + '/direct-staging'}))

    def put(route):
        seen.append(('put', route.request.method))
        route.fulfill(status=201)

    def complete(route):
        seen.append(('complete', route.request.post_data_json['ticket']))
        route.fulfill(status=201, content_type='application/json', body=json.dumps({'name': 'large.csv'}))

    page.route('**/upload-ticket', ticket)
    page.route('**/direct-staging', put)
    page.route('**/upload-complete', complete)
    page.locator('#ufile').set_input_files({'name': 'large.csv', 'mimeType': 'text/csv',
                                         'buffer': b'a' * (8*1024*1024)})
    expect(page.locator('#toast')).to_contain_text('large.csv uploaded and checked')
    assert seen == [('ticket', 8*1024*1024), ('put', 'PUT'), ('complete', 'a'*32)]
    assert console_errors == []

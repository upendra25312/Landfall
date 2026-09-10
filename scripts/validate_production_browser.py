"""Interactive EasyAuth validation; credentials stay in the ephemeral browser session."""
import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path

from smoke import load_config


async def run(output, login_seconds):
    from playwright.async_api import async_playwright, expect
    base = load_config()["SERVICE_WEB_URI"].rstrip("/")
    result = {"status": "BLOCKED", "reason": "Interactive Entra sign-in was not completed"}
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(type(exc).__name__))
        try:
            print("Sign in to Landfall in the opened browser; validation continues automatically.", flush=True)
            try:
                await page.goto(base + "/.auth/login/aad?post_login_redirect_uri=/", wait_until="commit", timeout=60000)
            except Exception:
                pass  # leave the browser open for interactive auth/redirect completion
            await page.locator("#engsel").wait_for(timeout=login_seconds * 1000)
            project = "browser-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
            await page.click("#neweng")
            await page.fill("input[name=customer]", "Validation C54")
            await page.fill("input[name=project]", project)
            await page.click("#ef button[type=submit]")
            eid = "validation-c54/" + project
            await expect(page.locator("#engsel")).to_have_value(eid, timeout=60000)
            result = {"status": "IN_PROGRESS", "engagement": eid, "retained_test_data": True}
            await page.locator("#ufile").set_input_files({"name": "servers.csv", "mimeType": "text/csv", "buffer":
                b"server_id,hostname,env,os_name,vcpu,ram_gb,provisioned_disk_gb,used_disk_gb,powerstate\n"
                b"c54-1,c54-web01,prod,Ubuntu,2,16,128,90,poweredOn\n"})
            await expect(page.locator("#filerows")).to_contain_text("servers.csv", timeout=60000)
            async with page.expect_response(lambda r: r.url.endswith("/analyze") and r.request.method == "POST", timeout=180000) as response:
                await page.click("#startanalysis")
            assert (await response.value).status == 200
            await expect(page.locator("#dqsummary")).to_contain_text("1 rows", timeout=180000)
            questionnaire = await page.request.get(base + "/questionnaire.xlsx?e=" + eid)
            assert questionnaire.status == 200 and (await questionnaire.body()).startswith(b"PK")
            assert not errors, errors
            await page.screenshot(path=str(output / "journey.png"))
            result.update(status="PASS", checks=["interactive Entra login", "create engagement", "CSV upload", "analysis", "questionnaire download"])
        except Exception as exc:
            result.update(error=type(exc).__name__)
            if result["status"] != "BLOCKED":
                result["status"] = "FAIL"
        finally:
            await browser.close()
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--login-seconds", type=int, default=180)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.output, args.login_seconds)))

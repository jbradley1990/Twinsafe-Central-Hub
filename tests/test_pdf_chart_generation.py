import pytest
from playwright.sync_api import Page, expect
import subprocess
import time

@pytest.fixture(scope="session", autouse=True)
def live_server():
    server = subprocess.Popen(["python3.12", "flask_server.py"])
    time.sleep(5)
    yield
    server.terminate()
    server.wait()

def test_generate_button_is_visible_after_file_upload(page: Page, live_server):
    page.goto("http://localhost:9000/#pdf-chart-generation")

    page.wait_for_selector("#pcg-initial-content")

    with page.expect_file_chooser() as fc:
        page.locator("#pcg-link").click()

    fc.value.set_files([
        "test_data/details.json",
        "test_data/data.csv"
    ])

    generate_button = page.locator("button", has_text="Generate PDF Chart")
    expect(generate_button).to_be_visible()

    page.screenshot(path="screenshot.png")

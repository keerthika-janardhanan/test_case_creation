from playwright.sync_api import sync_playwright

URL = "https://example.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    def on_console(msg):
        print("PAGE CONSOLE:", msg.type, msg.text)

    page.on("console", on_console)
    print("Going to", URL)
    page.goto(URL, wait_until="load")
    print("Page URL after goto:", page.url)
    print("Page title:", page.title())
    input("Press Enter to close...")
    context.close()
    browser.close()
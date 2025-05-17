import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


def get_jamhacks_data(jamhacks_code):
    load_dotenv()

    base_url = "https://app.jamhacks.ca"
    socials_url = f"{base_url}/social/{jamhacks_code}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--single-process",
            ]
        )

        context = browser.new_context()
        page = context.new_page()

        page.context.add_cookies([{
            "name": "__Secure-next-auth.session-token",
            "value": os.getenv("__SECURE_NEXT_AUTH_SESSION_TOKEN"),
            "domain": "app.jamhacks.ca",
            "path": "/",
            "secure": True,
            "httpOnly": True
        }])

        page.goto(socials_url)

        name = page.locator("h1").text_content()
        socials = [p.text_content() for p in page.locator("p").all() if p.text_content()]

        print(name, socials)

        browser.close()
        return name, socials


# get_jamhacks_data(536930711647551488)

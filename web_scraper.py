from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options

import os
from dotenv import load_dotenv

driver = None


class Scraper:
    def __init__(self):
        firefox_options = Options()
        firefox_options.add_argument("--headless")
        firefox_options.add_argument("--disable-gpu")
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Firefox(options=firefox_options)
        self.driver.get("https://app.jamhacks.ca/social/")

        try:
            self.driver.add_cookie({
                "name": "__Secure-next-auth.session-token",
                "value": os.getenv("__SECURE_NEXT_AUTH_SESSION_TOKEN"),
                "domain": "app.jamhacks.ca",
                "path": "/",
                "secure": True,
                "httpOnly": True
            })
        except Exception as e:
            print(f"failed to set cookie: {e}")

        print("DRIVER LOADED!!")

    def get_jamhacks_data(self, jamhacks_code):
        print("loading!")
        load_dotenv()

        print(driver)
        self.driver.get("https://app.jamhacks.ca/social/" + str(jamhacks_code))

        try:
            name_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1"))
            )
            name = name_element.text
            print(name)

            social_elements = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "p"))
            )
            socials = [social.text for social in social_elements if len(social.text) != 0]
            print(socials)

            return name, socials

        except Exception as e:
            print(f"Error: {e}")

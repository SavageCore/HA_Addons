import asyncio
import json
import logging
import os
import sys
import threading
import time

import hypercorn.asyncio
import pyotp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from classes.homeassistant_websocket import HomeAssistantWebsocket
from flask import Flask, jsonify, request
from hypercorn.config import Config
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from seleniumbase import Driver  # type: ignore

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Configure logging to flush immediately
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

thread_event = threading.Event()




def load_config():
    hass_path = "/data/options.json"
    win_path = "data/options.json"
    options_file = hass_path if os.path.exists(hass_path) else win_path
    with open(options_file, "r") as f:
        return json.load(f)


# Initialize the config and driver
config = load_config()
driver = Driver(headless=False)
driver.implicitly_wait(10)


async def login(driver: Driver) -> None:
    """Log in to Amazon."""
    driver.get(config["login_url"])

    email_input = driver.find_element(By.ID, "ap_email")
    has_password_field = False
    try:
        password_input = driver.find_element(By.ID, "ap_password")
        has_password_field = True
    except NoSuchElementException:
        pass

    if has_password_field:
        email_input.send_keys(config["email"])
        password_input.send_keys(config["password"])
        submit_button = driver.find_element(By.ID, "signInSubmit")
        submit_button.click()
    else:
        email_input.send_keys(config["email"])
        continue_button = driver.find_element(By.ID, "continue")
        continue_button.click()
        password_input = driver.find_element(By.ID, "ap_password")
        password_input.send_keys(config["password"])
        submit_button = driver.find_element(By.ID, "signInSubmit")
        submit_button.click()

    mfa_code_input = driver.find_element(By.ID, "auth-mfa-otpcode")
    if mfa_code_input is not None:
        mfa_code = get_mfa_code()
        mfa_code_input.send_keys(mfa_code)
        submit_button = driver.find_element(By.ID, "auth-signin-button")
        submit_button.click()


def get_mfa_code() -> str:
    """Get the MFA code."""
    totp = pyotp.TOTP(config["mfa_secret"])
    return totp.now()

def get_shopping_list(driver: Driver):
    """Get the shopping list items."""
    driver.get(config["list_url"])
    driver.implicitly_wait(10)

    list_container = driver.find_element(By.CLASS_NAME, 'virtual-list')

    found = []
    last = None
    while True:
        list_items = list_container.find_elements(By.CLASS_NAME, 'item-title')
        for item in list_items:
            if item.get_attribute('innerText') not in found:
                found.append(item.get_attribute('innerText'))
        if not list_items or last == list_items[-1]:
            # We've reached the end
            break
        last = list_items[-1]
        driver.execute_script("arguments[0].scrollIntoView();", last)
        time.sleep(1)

    return found

def get_shopping_list_item_element(driver, item: str):
    """Get the shopping list item element by its title."""
    driver.get(config["list_url"])
    list_container = driver.find_element(By.CLASS_NAME, 'virtual-list')

    last = None
    while True:
        list_items = list_container.find_elements(By.CLASS_NAME, 'inner')
        for container in list_items:
            title_element = container.find_element(By.CLASS_NAME, 'item-title')
            if title_element.get_attribute('innerText') == item:
                return container  # Return immediately when found

        if not list_items or last == list_items[-1]:
            # We've reached the top
            break

        last = list_items[-1]
        driver.execute_script("arguments[0].scrollIntoView();", last)
        time.sleep(1)

    return None

async def update_local_shopping_list(driver: Driver, config) -> None:
    """Update the local shopping list."""
    shopping_list_items = get_shopping_list(driver)

    ha_ws = HomeAssistantWebsocket(config["ha_url"], config["ha_token"], logger=logger)

    try:
        existing_items = await ha_ws.get_todo_list_items()

        if existing_items is None:
            existing_item_names = []
        else:
            existing_item_names = [item["summary"].lower() for item in existing_items]

        for shopping_list_item in shopping_list_items:
            if shopping_list_item.lower() not in existing_item_names:
                await ha_ws.add_todo_list_item(shopping_list_item)

    finally:
        await ha_ws.close()

# Route to get the shopping list
@app.route("/shopping_list", methods=["GET"])
def get_list_route():
    """Get the shopping list."""
    try:
        shopping_list_items = get_shopping_list(driver)
        return jsonify({"status": "success", "items": shopping_list_items})
    except Exception as e:
        logger.error(f"Error getting shopping list: {e}")
        return jsonify({"status": "failure", "message": str(e)}), 500

# Route to add an item to the shopping list
@app.route("/add_item", methods=["POST"])
def add_item_route():
    item = request.json.get("item")
    if add_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Added '{item}' to Alexa shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' already in Alexa shopping list"}
        )


# Route to update an item in the shopping list
@app.route("/update_item", methods=["PUT"])
def update_item_route():
    item = request.json.get("item")
    new_item = request.json.get("new_item")
    if update_shopping_list_item(driver, item, new_item):
        return jsonify(
            {
                "status": "success",
                "message": f"Updated '{item}' to '{new_item}' in Alexa shopping list",
            }
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in Alexa shopping list"}
        )


# Route to complete an item in the shopping list
@app.route("/complete_item", methods=["PUT"])
def complete_item_route():
    item = request.json.get("item")
    if complete_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Completed '{item}' in Alexa shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in Alexa shopping list"}
        )


# Route to remove an item from the shopping list
@app.route("/remove_item", methods=["POST"])
def remove_item_route():
    item = request.json.get("item")
    if remove_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Removed '{item}' from Alexa shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in Alexa shopping list"}
        )

def add_shopping_list_item(driver: Driver, item: str) -> bool:
    """Add an item to the shopping list."""

    # Check if the item already exists in the shopping list
    existing_items = get_shopping_list(driver)
    if item.lower() in [i.lower() for i in existing_items]:
        logger.info(f"Item '{item}' already exists in the shopping list.")
        return False

    # Scroll to the top of the page to ensure the add button is visible
    driver.execute_script("window.scrollTo(0, 0);")

    driver.find_element(By.CLASS_NAME, 'list-header').find_element(By.CLASS_NAME, 'add-symbol').click()

    textfield = driver.find_element(By.CLASS_NAME, 'list-header').find_element(By.CLASS_NAME, 'input-box').find_element(By.TAG_NAME, 'input')
    textfield.send_keys(item)

    submit = driver.find_element(By.CLASS_NAME, 'list-header').find_element(By.CLASS_NAME, 'add-to-list').find_element(By.TAG_NAME, 'button')
    submit.click()

    driver.find_element(By.CLASS_NAME, 'list-header').find_element(By.CLASS_NAME, 'cancel-input').click()
    time.sleep(1)

    return True


def update_shopping_list_item(driver: Driver, item: str, new_item: str) -> bool:
    """Update an item in the shopping list."""
    driver.get(config["list_url"])
    shopping_list_items = driver.find_elements(
        By.CSS_SELECTOR, ".virtual-list .item-title"
    )
    item_found = False

    for shopping_list_item in shopping_list_items:
        if shopping_list_item.text.lower() == item.lower():
            item_found = True
            inner_div = shopping_list_item
            while inner_div.get_attribute("class") != "inner":
                inner_div = inner_div.find_element(By.XPATH, "..")
            edit_button = inner_div.find_element(
                By.CSS_SELECTOR, ".item-actions-1 button"
            )
            edit_button.click()
            edit_item_input = driver.find_element(By.CSS_SELECTOR, ".input-box input")
            edit_item_input.clear()
            edit_item_input.send_keys(new_item)
            update_button = driver.find_element(
                By.CSS_SELECTOR, ".item-actions-2 button"
            )
            update_button.click()
            break

    return item_found


def complete_shopping_list_item(driver: Driver, item: str) -> bool:
    """Complete an item in the shopping list."""
    retries = 3
    while retries > 0:
        element = get_shopping_list_item_element(driver, item)

        if element is None:
            return None
        try:
            check_box = element.find_element(By.CLASS_NAME, 'custom-checkbox')
            check_box_input = check_box.find_element(By.TAG_NAME, 'input')
            driver.execute_script("arguments[0].click();", check_box_input)

            return True
        except StaleElementReferenceException:
            retries -= 1
            time.sleep(1)


def remove_shopping_list_item(driver: Driver, item: str) -> bool:
    """Remove an item from the shopping list."""
    retries = 3
    while retries > 0:
        element = get_shopping_list_item_element(driver, item)

        if element is None:
            return None
        try:
            # Find the delete button and click it
            delete_button = element.find_element(By.CLASS_NAME, 'item-actions-2').find_element(By.TAG_NAME, 'button')
            delete_button.click()
            return True
        except StaleElementReferenceException:
            retries -= 1
            time.sleep(1)

    return False

def run_update():
    try:
        asyncio.run(update_local_shopping_list(driver, config))
    except Exception as e:
        logger.error(f"Error running update: {e}")


async def main():
    await login(driver)

    await update_local_shopping_list(driver, config)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_update, "interval", minutes=1)
    try:
        scheduler.start()
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")


# Run the Flask app with Hypercorn
hyper_config = Config()
hyper_config.bind = ["0.0.0.0:5000"]

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.create_task(main())
loop.run_until_complete(hypercorn.asyncio.serve(app, hyper_config))

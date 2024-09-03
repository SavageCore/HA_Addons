import asyncio
import json
import logging
import sys
import threading
import hypercorn.asyncio
from hypercorn.config import Config

import pyotp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from classes.homeassistant_websocket import HomeAssistantWebsocket
from flask import Flask, jsonify, request
from selenium.common.exceptions import NoSuchElementException
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
    options_file = "/data/options.json"
    with open(options_file, "r") as f:
        return json.load(f)


# Initialize the config and driver
config = load_config()
driver = Driver(headless=True)
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


def get_shopping_list(driver: Driver) -> list:
    """Get the shopping list."""
    driver.get(config["list_url"])
    shopping_list_items = driver.find_elements(
        By.CSS_SELECTOR, ".virtual-list .item-title"
    )
    return [item.text for item in shopping_list_items]


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


# Route to add an item to the shopping list
@app.route("/add_item", methods=["POST"])
def add_item_route():
    item = request.json.get("item")
    if add_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Added '{item}' to HA shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' already in HA hopping list"}
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
                "message": f"Updated '{item}' to '{new_item}' in HA shopping list",
            }
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in HA shopping list"}
        )


# Route to complete an item in the shopping list
@app.route("/complete_item", methods=["PUT"])
def complete_item_route():
    item = request.json.get("item")
    if complete_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Completed '{item}' in HA shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in HA shopping list"}
        )


# Route to remove an item from the shopping list
@app.route("/remove_item", methods=["POST"])
def remove_item_route():
    item = request.json.get("item")
    if remove_shopping_list_item(driver, item):
        return jsonify(
            {"status": "success", "message": f"Removed '{item}' from HA shopping list"}
        )
    else:
        return jsonify(
            {"status": "failure", "message": f"'{item}' not found in HA shopping list"}
        )


def add_shopping_list_item(driver: Driver, item: str) -> bool:
    """Add an item to the shopping list."""

    shopping_list_items = get_shopping_list(driver)
    for shopping_list_item in shopping_list_items:
        if shopping_list_item.lower() == item.lower():
            return False
    add_item_button = driver.find_element(By.CSS_SELECTOR, ".list-header")
    add_item_button.click()
    add_item_input = driver.find_element(By.CSS_SELECTOR, ".list-header input")
    add_item_input.send_keys(item)
    add_to_list_button = driver.find_element(By.CSS_SELECTOR, ".add-to-list button")
    add_to_list_button.click()

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
            checkbox_input = inner_div.find_element(
                By.CSS_SELECTOR, "input[type='checkbox']"
            )
            checkbox_input.click()
            break

    return item_found


def remove_shopping_list_item(driver: Driver, item: str) -> bool:
    """Remove an item from the shopping list."""
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
            delete_button = inner_div.find_element(
                By.CSS_SELECTOR, ".item-actions-2 button"
            )
            delete_button.click()
            break

    return item_found


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

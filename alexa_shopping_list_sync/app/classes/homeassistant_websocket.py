import asyncio
import json
import logging

import websockets
from classes.homeassistant_api import HomeAssistantAPI
from constants.entity_id_mapping import entity_id_mapping


class HomeAssistantWebsocket:

    def __init__(self, url, token, logger=None):
        self.url = url
        self.token = token
        self.logger = logger
        self.websocket = None
        self.reconnect_attempts = 3
        self.request_id = 1  # Initialize the request ID counter
        self.logger = logger or logging.getLogger(
            __name__
        )  # Use provided logger or create one
        self.ha_api = HomeAssistantAPI(url, token, logger=logger)
        self.entity_id = self.get_entity_id_for_language()

    async def connect(self):
        """Establish a connection to the Home Assistant WebSocket API."""
        try:
            self.websocket = await websockets.connect(self.url)

            initial_message = await self.websocket.recv()
            initial_response = json.loads(initial_message)

            if initial_response.get("type") == "auth_required":
                await self.authenticate()
            else:
                raise Exception(
                    "Unexpected message type received during initial connection"
                )
        except Exception as e:
            self.logger.error(f"Error during connection: {e}")
            await self.close()  # Ensure the connection is closed on error
            raise

    async def connect_with_retries(self):
        """Attempt to connect with retries."""
        for attempt in range(self.reconnect_attempts):
            try:
                await self.connect()
                self.request_id = 1  # Reset the request ID on a new connection
                break  # Break the loop if connection is successful
            except Exception as e:
                self.logger.error(
                    f"Attempt {attempt + 1}/{self.reconnect_attempts} failed: {e}"
                )
                if attempt == self.reconnect_attempts - 1:
                    raise  # Reraise the last exception if max attempts reached
                await asyncio.sleep(5)  # Wait before retrying

    async def send(self, message):
        """Send a message to the WebSocket server, reconnect if necessary."""
        if self.websocket is None or self.websocket.closed:
            await self.connect_with_retries()
        await self.websocket.send(message)

    async def authenticate(self):
        """Authenticate with the Home Assistant WebSocket API using the provided token."""
        auth_message = {"type": "auth", "access_token": self.token}
        await self.send(json.dumps(auth_message))

        auth_response = await self.websocket.recv()
        auth_response = json.loads(auth_response)

        if auth_response.get("type") != "auth_ok":
            raise Exception("Authentication failed")

    def get_entity_id_for_language(self):
        language = self.ha_api.get_current_language()

        return entity_id_mapping.get(language, "todo.shopping_list")

    async def get_todo_list_items(self):
        """Fetch the current todo/shopping list items from Home Assistant."""
        if self.websocket is None or self.websocket.closed:
            await self.connect_with_retries()

        request_message = {
            "id": self.request_id,
            "type": "call_service",
            "domain": "todo",
            "service": "get_items",
            "return_response": True,
            "service_data": {"entity_id": self.entity_id},
        }

        self.request_id += 1  # Increment the request ID for the next request

        try:
            await self.send(json.dumps(request_message))

            response = await self.websocket.recv()
            response_data = json.loads(response)
            if response_data.get("success"):
                todo_list = (
                    response_data.get("result", {})
                    .get("response", {})
                    .get(self.entity_id, {})
                    .get("items", [])
                )

                return [
                    item for item in todo_list if item.get("status") == "needs_action"
                ]
            else:
                raise Exception(f"Failed to get items: {response_data.get('error')}")
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"Connection closed while fetching items: {e}")
            await self.connect_with_retries()  # Attempt to reconnect
            return await self.get_todo_list_items()  # Retry fetching items
        except Exception as e:
            self.logger.error(f"An error occurred while fetching items: {e}")
            return None

    async def add_todo_list_item(self, item_name):
        """Add a new item to the todo/shopping list in Home Assistant."""
        if not item_name:
            return

        if self.websocket is None or self.websocket.closed:
            await self.connect_with_retries()

        request_message = {
            "id": self.request_id,
            "type": "call_service",
            "domain": "todo",
            "service": "add_item",
            "service_data": {"entity_id": self.entity_id, "item": item_name},
        }

        self.request_id += 1  # Increment the request ID for the next request

        try:
            await self.send(json.dumps(request_message))

            response = await self.websocket.recv()
            response_data = json.loads(response)
            if response_data.get("success") is False:
                raise Exception(f"Failed to add item: {response_data.get('error')}")
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.error(f"Connection closed while adding item: {e}")
            await self.connect_with_retries()  # Attempt to reconnect
            await self.add_todo_list_item(item_name, id)  # Retry adding the item
        except Exception as e:
            self.logger.error(f"An error occurred while adding item '{item_name}': {e}")

    async def close(self):
        """Close the WebSocket connection."""
        if self.websocket is not None:
            await self.websocket.close()

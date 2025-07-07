import asyncio
import websockets

# This set will store all connected clients
connected_clients = set()

async def handler(websocket, path):
    """Handles incoming WebSocket connections and messages."""
    # Add the new client to our set of connected clients
    connected_clients.add(websocket)
    print(f"New client connected: {websocket.remote_address}")
    try:
        # Keep the connection open and listen for messages
        async for message in websocket:
            print(f"<-- [Browser Log]: {message}")
            # You can add logic here to process the message
            # For now, we just print it to the CLI's console
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Client disconnected: {websocket.remote_address} (Code: {e.code}, Reason: {e.reason})")
    finally:
        # Remove the client from the set when they disconnect
        connected_clients.remove(websocket)

async def main():
    """Starts the WebSocket server."""
    host = "localhost"
    port = 8765  # A common port for WebSockets
    async with websockets.serve(handler, host, port):
        print(f"WebSocket server started at ws://{host}:{port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server is shutting down.")

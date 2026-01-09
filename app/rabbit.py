]import os
import json
import aio_pika

# RabbitMQ connection URL 
# Using ["RABBIT_URL"] means it MUST exist, otherwise the app will crash on startup.
RABBIT_URL = os.environ["RABBIT_URL"]

# Name of the exchange 
# If not set, it defaults to "events_topic"
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "events_topic")


async def publish_event(routing_key: str, payload: dict) -> None:
    """
    This sends (publishes) a message/event to RabbitMQ.

    - routing_key decides what topic the message is 
    - payload is the data you want to send
    - Notification worker can bind to patterns like:
        workout.*
      so it receives workout.created, workout.updated, etc.
    """

    # Connect to RabbitMQ 
    connection = await aio_pika.connect_robust(RABBIT_URL)

    try:
        # Open a channel 
        channel = await connection.channel()

        # Create/get a topic exchange 
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )

        # Convert the payload dict into JSON text, then into bytes
        body = json.dumps(payload).encode("utf-8")

        # Create the message object
        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        # Publish the message to the exchange using the routing_key
        # Example routing_key: "workout.created"
        await exchange.publish(message, routing_key=routing_key)

    finally:
        # Always close the connection even if something fails
        await connection.close()

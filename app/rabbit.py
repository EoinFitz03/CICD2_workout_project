import os
import json
import aio_pika

# got it 

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "events_topic")

async def publish_event(routing_key: str, payload: dict) -> None:
    """
    Publish an event to RabbitMQ topic exchange.
    Notification worker listens on:
      EXCHANGE_NAME=events_topic
      BINDING_KEY=workout.*
    So routing_key like 'workout.created' will be consumed.
    """
    connection = await aio_pika.connect_robust(RABBIT_URL)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )

        body = json.dumps(payload).encode("utf-8")
        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await exchange.publish(message, routing_key=routing_key)
    finally:
        await connection.close()

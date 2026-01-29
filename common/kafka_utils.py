from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from typing import Callable, Optional, Any
import logging
import json
from common.config import KafkaConfig

logger = logging.getLogger(__name__)

class KafkaProducerWrapper:
    def __init__(self, config: KafkaConfig):
        self.config = config
        self.producer = KafkaProducer(
            bootstrap_servers=config.bootstrap_servers,
            value_serializer=lambda v: v.encode('utf-8') if isinstance(v, str) else json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            retries=5,
            retry_backoff_ms=1000,
            acks='all'
        )
    
    def send(self, topic: str, value: Any, key: Optional[str] = None) -> bool:
        def on_success(record_metadata):
            logger.debug(f"Message sent to {topic} partition {record_metadata.partition} offset {record_metadata.offset}")

        def on_error(excp):
            logger.error(f"Failed to send message to {topic}: {excp}")

        try:
            future = self.producer.send(topic, value=value, key=key)
            future.add_callback(on_success)
            future.add_errback(on_error)
            # For critical messages we might want to wait, but usually we can be async
            # and rely on callbacks and flush at shutdown.
            # To meet the "Delivery confirmation" request without being purely fire-and-forget:
            record_metadata = future.get(timeout=10)
            return True
        except KafkaError as e:
            logger.error(f"Kafka error while sending to {topic}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while sending to {topic}: {e}")
            return False
    
    def flush(self):
        logger.info("Flushing producer...")
        self.producer.flush()
    
    def close(self):
        logger.info("Closing producer...")
        self.producer.flush()
        self.producer.close()

class KafkaConsumerWrapper:
    def __init__(
        self,
        config: KafkaConfig,
        topics: list[str],
        group_id: str,
        message_handler: Callable[[str, str], None]
    ):
        self.config = config
        self.topics = topics
        self.message_handler = message_handler
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=config.bootstrap_servers,
            group_id=f"{config.group_id_prefix}-{group_id}",
            auto_offset_reset=config.auto_offset_reset,
            enable_auto_commit=config.enable_auto_commit,
            value_deserializer=lambda m: m.decode('utf-8'),
            key_deserializer=lambda k: k.decode('utf-8') if k else None
        )
        logger.info(f"Consumer {group_id} subscribed to topics: {topics}")
    
    def start(self):
        logger.info("Starting consumer loop...")
        try:
            for message in self.consumer:
                try:
                    self.message_handler(message.topic, message.value)
                except Exception as e:
                    logger.error(f"Error processing message from {message.topic}: {e}", exc_info=True)
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        finally:
            self.close()
    
    def close(self):
        logger.info("Closing consumer...")
        self.consumer.close()

def create_producer(config: KafkaConfig) -> KafkaProducerWrapper:
    return KafkaProducerWrapper(config)

def create_consumer(
    config: KafkaConfig,
    topics: list[str],
    group_id: str,
    message_handler: Callable[[str, str], None]
) -> KafkaConsumerWrapper:
    return KafkaConsumerWrapper(config, topics, group_id, message_handler)

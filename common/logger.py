import logging
import json
import socket
import datetime
from typing import Optional
from kafka import KafkaProducer
from common.config import KafkaConfig

class KafkaLogHandler(logging.Handler):
    def __init__(self, bootstrap_servers: str, topic: str):
        super().__init__()
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        except Exception as e:
            print(f"Failed to initialize KafkaProducer for logging: {e}")
            self.producer = None

    def emit(self, record):
        if self.producer:
            try:
                log_entry = {
                    "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "agent": record.name,
                    "message": record.getMessage(),
                    "hostname": socket.gethostname()
                }
                self.producer.send(self.topic, value=log_entry)
            except Exception:
                self.handleError(record)

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer.close()
        super().close()

def setup_logger(name: str, kafka_config: Optional[KafkaConfig] = None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Console Handler
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Kafka Handler
    if kafka_config:
        kafka_handler = KafkaLogHandler(kafka_config.bootstrap_servers, "system-logs")
        logger.addHandler(kafka_handler)
    
    return logger

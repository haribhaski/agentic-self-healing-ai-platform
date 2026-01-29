import logging
import json
import socket
import datetime
import os
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
    
    # Clear existing handlers to avoid duplicates on reload
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Console Handler
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File Handler (Reset on startup)
    log_dir = os.path.join(os.path.dirname(__file__), '../backend/logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f"{name.lower()}.log")
    # Open in 'w' mode to clear old logs as requested
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Kafka Handler
    if kafka_config:
        kafka_handler = KafkaLogHandler(kafka_config.bootstrap_servers, "system-logs")
        logger.addHandler(kafka_handler)
        # Send a session start marker
        try:
            kafka_handler.producer.send("system-logs", {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "level": "INFO",
                "agent": name,
                "message": f"--- SESSION RESTARTED: {name} ---",
                "hostname": socket.gethostname(),
                "is_marker": True
            })
        except:
            pass
    
    return logger

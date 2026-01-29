import threading
import time
from prometheus_client import start_http_server, Gauge, Counter

class AgentMetricsExporter:
    def __init__(self, agent_name, port=8000):
        self.agent_name = agent_name
        self.port = port
        self.latency_gauge = Gauge(f'{agent_name.lower()}_latency_ms', 'Agent processing latency in ms')
        self.events_counter = Counter(f'{agent_name.lower()}_events_total', 'Total events processed by agent')
        self.cpu_gauge = Gauge(f'{agent_name.lower()}_cpu_percent', 'Agent CPU usage percentage')
        self.memory_gauge = Gauge(f'{agent_name.lower()}_memory_mb', 'Agent memory usage in MB')
        self._running = False

    def start(self):
        if not self._running:
            try:
                start_http_server(self.port)
                self._running = True
                print(f"Metrics exporter started on port {self.port}")
            except Exception as e:
                print(f"Failed to start metrics server: {e}")

    def update_metrics(self, latency_ms=0, events_increment=0, cpu_percent=0, memory_mb=0):
        self.latency_gauge.set(latency_ms)
        if events_increment > 0:
            self.events_counter.inc(events_increment)
        self.cpu_gauge.set(cpu_percent)
        self.memory_gauge.set(memory_mb)

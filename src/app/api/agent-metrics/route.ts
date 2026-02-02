import { NextRequest } from "next/server";
import { Kafka } from "kafkajs";

export const dynamic = "force-dynamic";
export const runtime = "nodejs"; // kafkajs needs node runtime

const kafka = new Kafka({
  clientId: "aura-web-metrics",
  brokers: [process.env.KAFKA_BOOTSTRAP_SERVERS || "127.0.0.1:29092"],
  retry: { initialRetryTime: 100, retries: 8 },
});

// ---- Global singleton state (dev/hot-reload safe) ----
declare global {
  // eslint-disable-next-line no-var
  var __metricsConsumerStarted: boolean | undefined;
  // eslint-disable-next-line no-var
  var __metricsClients: Set<ReadableStreamDefaultController> | undefined;
}

function getClients() {
  if (!global.__metricsClients) global.__metricsClients = new Set();
  return global.__metricsClients;
}

async function startMetricsConsumerOnce() {
  if (global.__metricsConsumerStarted) return;
  global.__metricsConsumerStarted = true;

  const consumer = kafka.consumer({
    groupId: "aura-web-metrics", // ✅ FIXED groupId (no random)
    sessionTimeout: 30000,
    heartbeatInterval: 3000,
  });

  await consumer.connect();
  await consumer.subscribe({ topic: "agent-metrics", fromBeginning: false });

  await consumer.run({
    eachMessage: async ({ message }) => {
      const data = message.value?.toString();
      if (!data) return;

      // Broadcast to all connected SSE clients
      for (const controller of getClients()) {
        try {
          controller.enqueue(`data: ${data}\n\n`);
        } catch {
          getClients().delete(controller);
        }
      }
    },
  });

  console.log("✅ Kafka metrics consumer started (singleton)");
}

export async function GET(req: NextRequest) {
  // Ensure singleton consumer is running
  startMetricsConsumerOnce().catch((e) => {
    console.error("Failed to start metrics consumer:", e);
  });

  const stream = new ReadableStream({
    start(controller) {
      // Register client
      getClients().add(controller);

      // Open stream
      controller.enqueue(`: connected\n\n`);

      // Keepalive ping
      const keepalive = setInterval(() => {
        try {
          controller.enqueue(`: heartbeat\n\n`);
        } catch {
          clearInterval(keepalive);
          getClients().delete(controller);
        }
      }, 15000);

      // Cleanup on disconnect
      req.signal.addEventListener("abort", () => {
        clearInterval(keepalive);
        getClients().delete(controller);
        try {
          controller.close();
        } catch {}
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

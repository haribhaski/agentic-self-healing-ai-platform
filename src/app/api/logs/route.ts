import { NextRequest } from "next/server";
import { Kafka } from "kafkajs";

export const dynamic = "force-dynamic";
export const runtime = "nodejs"; // IMPORTANT: kafkajs needs node runtime (not edge)

const kafka = new Kafka({
  clientId: "aura-web-dashboard",
  brokers: [process.env.KAFKA_BOOTSTRAP_SERVERS || "127.0.0.1:29092"],
  retry: { initialRetryTime: 100, retries: 8 },
});

// ---- Global singleton state (survives hot reload in dev) ----
declare global {
  // eslint-disable-next-line no-var
  var __logsConsumerStarted: boolean | undefined;
  // eslint-disable-next-line no-var
  var __logsClients: Set<ReadableStreamDefaultController> | undefined;
}

function getClients() {
  if (!global.__logsClients) global.__logsClients = new Set();
  return global.__logsClients;
}

async function startLogsConsumerOnce() {
  if (global.__logsConsumerStarted) return;
  global.__logsConsumerStarted = true;

  const consumer = kafka.consumer({
    groupId: "aura-web-logs", // FIXED group id
    sessionTimeout: 30000,
    heartbeatInterval: 3000,
  });

  await consumer.connect();
  await consumer.subscribe({ topic: "system-logs", fromBeginning: false });

  await consumer.run({
    eachMessage: async ({ message }) => {
      const data = message.value?.toString();
      if (!data) return;

      // Broadcast to all connected SSE clients
      for (const controller of getClients()) {
        try {
          controller.enqueue(`data: ${data}\n\n`);
        } catch {
          // controller is likely closed; remove it
          getClients().delete(controller);
        }
      }
    },
  });

  console.log("✅ Kafka logs consumer started (singleton)");
}

export async function GET(req: NextRequest) {
  // Ensure singleton consumer is running
  startLogsConsumerOnce().catch((e) => {
    console.error("Failed to start logs consumer:", e);
    // Note: clients will still connect, but may not receive logs until fixed
  });

  const stream = new ReadableStream({
    start(controller) {
      // Register this client
      getClients().add(controller);

      // Send an initial comment to open stream
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

      // If client disconnects
      req.signal.addEventListener("abort", () => {
        clearInterval(keepalive);
        getClients().delete(controller);
        try {
          controller.close();
        } catch {}
      });
    },
    cancel() {
      // handled by abort listener usually, but keep safe
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

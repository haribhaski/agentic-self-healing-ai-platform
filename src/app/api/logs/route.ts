import { NextRequest } from 'next/server';
import { Kafka } from 'kafkajs';

export const dynamic = 'force-dynamic';

const kafka = new Kafka({
  clientId: 'aura-web-dashboard',
  brokers: [process.env.KAFKA_BOOTSTRAP_SERVERS || 'localhost:29092'],
});

export async function GET(req: NextRequest) {
  const { signal } = req;
  const consumer = kafka.consumer({ groupId: `web-logs-${Math.random().toString(36).substring(7)}` });

  const stream = new ReadableStream({
    async start(controller) {
      let heartbeatInterval: NodeJS.Timeout;
      
      try {
        await consumer.connect();
        await consumer.subscribe({ topic: 'system-logs', fromBeginning: false });

        // Keep-alive heartbeat
        heartbeatInterval = setInterval(() => {
          try {
            controller.enqueue(': heartbeat\n\n');
          } catch (e) {
            clearInterval(heartbeatInterval);
          }
        }, 15000);

        await consumer.run({
          eachMessage: async ({ message }) => {
            if (signal.aborted) {
              clearInterval(heartbeatInterval);
              await consumer.disconnect();
              return;
            }
            const data = message.value?.toString();
            if (data) {
              controller.enqueue(`data: ${data}\n\n`);
            }
          },
        });
      } catch (error) {
        console.error('Kafka consumer error:', error);
        if (heartbeatInterval!) clearInterval(heartbeatInterval);
        try {
          controller.error(error);
        } catch (e) {
          // Controller might already be closed
        }
      }
    },
    async cancel() {
      await consumer.disconnect();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

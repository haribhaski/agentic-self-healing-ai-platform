import { NextRequest } from 'next/server';
import { Kafka } from 'kafkajs';

export const dynamic = 'force-dynamic';

const kafka = new Kafka({
  clientId: 'aura-web-metrics',
  brokers: [process.env.KAFKA_BOOTSTRAP_SERVERS || '127.0.0.1:29092'],
  retry: {
    initialRetryTime: 100,
    retries: 8
  }
});

export async function GET(req: NextRequest) {
  const { signal } = req;
  const consumer = kafka.consumer({ 
    groupId: `web-metrics-${Math.random().toString(36).substring(7)}`,
    sessionTimeout: 30000,
    heartbeatInterval: 3000,
  });

  const stream = new ReadableStream({
    async start(controller) {
      let heartbeatInterval: NodeJS.Timeout;
      let isClosed = false;
      
      try {
        await consumer.connect();
        await consumer.subscribe({ topic: 'agent-metrics', fromBeginning: false });

        heartbeatInterval = setInterval(() => {
          if (isClosed) return;
          try {
            controller.enqueue(': heartbeat\n\n');
          } catch (e) {
            isClosed = true;
            clearInterval(heartbeatInterval);
          }
        }, 15000);

        await consumer.run({
          eachMessage: async ({ message }) => {
            if (signal.aborted || isClosed) {
              return;
            }
            const data = message.value?.toString();
            if (data) {
              try {
                controller.enqueue(`data: ${data}\n\n`);
              } catch (e) {
                isClosed = true;
              }
            }
          },
        });
      } catch (error) {
        console.error('Kafka consumer error (agent-metrics):', error);
        if (heartbeatInterval!) clearInterval(heartbeatInterval);
        isClosed = true;
      }
    },
    async cancel() {
      try {
        await consumer.stop();
        await consumer.disconnect();
      } catch (e) {}
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

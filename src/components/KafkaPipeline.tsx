"use client";

import { motion } from "framer-motion";
import { Activity, ArrowRight, Database, Zap, Server, HardDrive } from "lucide-react";

const kafkaTopics = [
  { name: "system.metrics", messages: "12.4K/s", color: "#00d9ff" },
  { name: "audit.logs", messages: "3.2K/s", color: "#7c3aed" },
  { name: "agent.decisions", messages: "856/s", color: "#10b981" },
  { name: "model.outputs", messages: "2.1K/s", color: "#f59e0b" },
];

const consumers = [
  { name: "AGL Planner", topic: "system.metrics", lag: 12 },
  { name: "Monitor Agent", topic: "audit.logs", lag: 3 },
  { name: "Incident Service", topic: "agent.decisions", lag: 0 },
  { name: "Analytics Sink", topic: "model.outputs", lag: 45 },
];

export function KafkaPipeline() {
  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-[#ff6b35]/20">
          <Zap className="w-5 h-5 text-[#ff6b35]" />
        </div>
        <div>
          <h3 className="font-display text-lg font-semibold text-white">Kafka Event Pipeline</h3>
          <p className="text-sm text-[#6b6b80]">Real-time streaming backbone</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#1a1a24] rounded-lg p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <Server className="w-4 h-4 text-[#ff6b35]" />
            <span className="text-xs text-[#6b6b80]">Brokers</span>
          </div>
          <p className="text-2xl font-mono font-bold text-white">3</p>
          <p className="text-xs text-[#10b981]">All healthy</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-[#1a1a24] rounded-lg p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-[#00d9ff]" />
            <span className="text-xs text-[#6b6b80]">Throughput</span>
          </div>
          <p className="text-2xl font-mono font-bold text-white">18.5K</p>
          <p className="text-xs text-[#6b6b80]">events/sec</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-[#1a1a24] rounded-lg p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="w-4 h-4 text-[#7c3aed]" />
            <span className="text-xs text-[#6b6b80]">Partitions</span>
          </div>
          <p className="text-2xl font-mono font-bold text-white">24</p>
          <p className="text-xs text-[#6b6b80]">across topics</p>
        </motion.div>
      </div>

      <div className="space-y-3 mb-6">
        <h4 className="text-sm font-medium text-[#6b6b80] uppercase tracking-wider">Active Topics</h4>
        {kafkaTopics.map((topic, i) => (
          <motion.div
            key={topic.name}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className="flex items-center justify-between bg-[#1a1a24] rounded-lg p-3"
          >
            <div className="flex items-center gap-3">
              <div
                className="w-2 h-2 rounded-full animate-pulse"
                style={{ backgroundColor: topic.color }}
              />
              <span className="font-mono text-sm text-white">{topic.name}</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="relative h-1 w-24 bg-[#0a0a0f] rounded-full overflow-hidden">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ backgroundColor: topic.color }}
                  initial={{ width: 0 }}
                  animate={{ width: "100%" }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "linear",
                  }}
                />
              </div>
              <span className="font-mono text-xs text-[#6b6b80] w-16 text-right">{topic.messages}</span>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="space-y-3">
        <h4 className="text-sm font-medium text-[#6b6b80] uppercase tracking-wider">Consumer Groups</h4>
        {consumers.map((consumer, i) => (
          <motion.div
            key={consumer.name}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4 + i * 0.1 }}
            className="flex items-center justify-between bg-[#1a1a24] rounded-lg p-3"
          >
            <div className="flex items-center gap-3">
              <Database className="w-4 h-4 text-[#3b82f6]" />
              <div>
                <span className="text-sm text-white">{consumer.name}</span>
                <span className="text-xs text-[#6b6b80] ml-2">← {consumer.topic}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[#6b6b80]">Lag:</span>
              <span
                className={`font-mono text-xs px-2 py-0.5 rounded ${
                  consumer.lag === 0
                    ? "bg-[#10b981]/20 text-[#10b981]"
                    : consumer.lag < 20
                    ? "bg-[#f59e0b]/20 text-[#f59e0b]"
                    : "bg-[#ff4757]/20 text-[#ff4757]"
                }`}
              >
                {consumer.lag}
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-6 p-4 bg-gradient-to-r from-[#ff6b35]/10 to-transparent rounded-lg border border-[#ff6b35]/20">
        <div className="flex items-center gap-3">
          <ArrowRight className="w-5 h-5 text-[#ff6b35]" />
          <div>
            <p className="text-sm text-white">Schema Registry Active</p>
            <p className="text-xs text-[#6b6b80]">Avro schemas enforced • 12 schemas registered</p>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { Brain, Zap, Database, BarChart3, Server, Cloud, ArrowDown, Sparkles } from "lucide-react";

const layers = [
  {
    name: "Agentic AI Layer",
    icon: Brain,
    color: "#00d9ff",
    items: ["LangGraph", "Llama 3.x / GPT", "Pinecone Memory"],
  },
  {
    name: "Kafka Streaming",
    icon: Zap,
    color: "#ff6b35",
    items: ["Multi-Broker Cluster", "Kafka Streams", "Schema Registry"],
  },
  {
    name: "ORM Stack",
    icon: Database,
    color: "#3b82f6",
    items: ["FastAPI", "SQLAlchemy", "PostgreSQL"],
  },
  {
    name: "MLOps Layer",
    icon: BarChart3,
    color: "#7c3aed",
    items: ["MLflow", "Evidently AI", "Airflow"],
  },
  {
    name: "Observability",
    icon: Server,
    color: "#10b981",
    items: ["Prometheus", "Grafana", "OpenTelemetry"],
  },
  {
    name: "Infrastructure",
    icon: Cloud,
    color: "#f59e0b",
    items: ["Kubernetes", "Docker", "ArgoCD"],
  },
];

export function ArchitectureFlow() {
  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-gradient-to-br from-[#00d9ff]/20 to-[#7c3aed]/20">
          <Sparkles className="w-5 h-5 text-[#00d9ff]" />
        </div>
        <div>
          <h3 className="font-display text-lg font-semibold text-white">System Architecture</h3>
          <p className="text-sm text-[#6b6b80]">Full stack overview</p>
        </div>
      </div>

      <div className="relative">
        {layers.map((layer, i) => (
          <motion.div
            key={layer.name}
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className="relative"
          >
            <div
              className="flex items-center gap-4 p-4 rounded-lg mb-2 transition-all hover:scale-[1.02]"
              style={{
                background: `linear-gradient(90deg, ${layer.color}15 0%, transparent 100%)`,
                borderLeft: `3px solid ${layer.color}`,
              }}
            >
              <div
                className="p-2 rounded-lg shrink-0"
                style={{ backgroundColor: `${layer.color}20` }}
              >
                <layer.icon className="w-5 h-5" style={{ color: layer.color }} />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-medium text-white">{layer.name}</h4>
                <div className="flex flex-wrap gap-2 mt-1.5">
                  {layer.items.map((item) => (
                    <span
                      key={item}
                      className="text-xs px-2 py-0.5 rounded-full bg-[#0a0a0f] text-[#6b6b80]"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            
            {i < layers.length - 1 && (
              <div className="flex justify-center py-1">
                <motion.div
                  animate={{ y: [0, 4, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                >
                  <ArrowDown className="w-4 h-4 text-[#6b6b80]" />
                </motion.div>
              </div>
            )}
          </motion.div>
        ))}
      </div>

      <div className="mt-6 p-4 rounded-lg bg-gradient-to-r from-[#00d9ff]/10 via-[#7c3aed]/10 to-[#10b981]/10 border border-white/5">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse" />
          <span className="text-xs font-medium text-[#10b981]">Self-Healing Loop Active</span>
        </div>
        <p className="text-xs text-[#6b6b80]">
          Closed-loop control system driven by streaming events. All components decoupled via Kafka.
        </p>
      </div>
    </div>
  );
}

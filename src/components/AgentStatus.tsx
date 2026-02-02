"use client";

import { motion } from "framer-motion";
import {
  Bot,
  Brain,
  Shield,
  Search,
  Wrench,
  CheckCircle,
  AlertTriangle,
  Clock,
  Zap,
  Activity,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type AgentMetric = {
  agent: string;
  status: string;
  latency_ms: number;
  timestamp: string;
  cpu_percent: number;
  memory_mb: number;
  events_processed: number;
};

const INITIAL_AGENTS = [
  {
    name: "Ingestion Agent",
    icon: Brain,
    status: "active",
    task: "Injecting events into Kafka",
    decisions: 0,
    color: "#00d9ff",
    lastSeenMs: 0,
  },
  {
    name: "Feature Agent",
    icon: Search,
    status: "active",
    task: "Processing raw features",
    decisions: 0,
    color: "#7c3aed",
    lastSeenMs: 0,
  },
  {
    name: "Model Agent",
    icon: Zap,
    status: "active",
    task: "Executing model inference",
    decisions: 0,
    color: "#10b981",
    lastSeenMs: 0,
  },
  {
    name: "Decision Agent",
    icon: Shield,
    status: "active",
    task: "Applying policy logic",
    decisions: 0,
    color: "#f59e0b",
    lastSeenMs: 0,
  },
  {
    name: "Monitoring Agent",
    icon: Activity,
    status: "active",
    task: "Analyzing metrics stream",
    decisions: 0,
    color: "#3b82f6",
    lastSeenMs: 0,
  },
  {
    name: "Healing Agent",
    icon: Wrench,
    status: "idle",
    task: "Awaiting remediation tasks",
    decisions: 0,
    color: "#ff4757",
    lastSeenMs: 0,
  },
];

const statusConfig = {
  active: { color: "#10b981", label: "Active", Icon: CheckCircle },
  idle: { color: "#6b6b80", label: "Idle", Icon: Clock },
  pending: { color: "#f59e0b", label: "Pending", Icon: AlertTriangle },
};

// Normalize names so "HealingAgent" matches "Healing Agent"
function normalizeAgentName(s: string) {
  return s.toLowerCase().replace(/\s+/g, "").replace(/agent$/, "");
}

function parseTimestampMs(ts: string): number {
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : 0;
}

export function AgentStatus() {
  const [agents, setAgents] = useState(INITIAL_AGENTS);
  const [nowMs, setNowMs] = useState(Date.now());

  // Tick so status can flip to idle if heartbeats stop
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let logSource: EventSource | null = null;
    let metricsSource: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      logSource?.close();
      metricsSource?.close();

      logSource = new EventSource("/api/logs");
      metricsSource = new EventSource("/api/agent-metrics");

      // Logs: update task text + mark active
      logSource.onmessage = (event) => {
        try {
          if (!event.data) return;
          const rawData = JSON.parse(event.data);
          if (!rawData?.agent) return;

          const incoming = normalizeAgentName(rawData.agent);

          setAgents((prev) =>
            prev.map((agent) => {
              const a = normalizeAgentName(agent.name);
              if (a === incoming) {
                return {
                  ...agent,
                  status: "active",
                  task: rawData.message ?? agent.task,
                  lastSeenMs: Date.now(),
                };
              }
              return agent;
            })
          );
        } catch {}
      };

      // Metrics: THIS IS THE IMPORTANT FIX
      // Update decisions + lastSeen, and mark active if heartbeat is recent
      metricsSource.onmessage = (event) => {
        try {
          if (!event.data) return;
          const data = JSON.parse(event.data) as AgentMetric;
          if (!data?.agent) return;

          const incoming = normalizeAgentName(data.agent);
          const metricSeenMs = parseTimestampMs(data.timestamp) || Date.now();

          setAgents((prev) =>
            prev.map((agent) => {
              const a = normalizeAgentName(agent.name);
              if (a === incoming) {
                return {
                  ...agent,
                  // ✅ update decisions
                  decisions:
                    typeof data.events_processed === "number"
                      ? data.events_processed
                      : agent.decisions,
                  // ✅ mark last seen from heartbeat
                  lastSeenMs: metricSeenMs,
                  // ✅ mark active (heartbeat proves it's alive)
                  status: "active",
                  // optional: show status string from metric
                  task:
                    agent.name === "Healing Agent"
                      ? data.events_processed === 0
                        ? "Awaiting remediation tasks"
                        : "Executing remediation"
                      : agent.task,
                };
              }
              return agent;
            })
          );
        } catch {}
      };

      logSource.onerror = () => {
        logSource?.close();
        metricsSource?.close();
        reconnectTimeout = setTimeout(connect, 3000);
      };
      metricsSource.onerror = () => {
        logSource?.close();
        metricsSource?.close();
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      logSource?.close();
      metricsSource?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // ✅ Derive status from heartbeat freshness (so it doesn’t stay active forever)
  const agentsWithFreshStatus = useMemo(() => {
    return agents.map((a) => {
      const alive = a.lastSeenMs > 0 && nowMs - a.lastSeenMs < 20000; // 20s
      return {
        ...a,
        status: alive ? "active" : "idle",
      };
    });
  }, [agents, nowMs]);

  const activeCount = agentsWithFreshStatus.filter((a) => a.status === "active").length;

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-[#00d9ff]/20">
            <Bot className="w-5 h-5 text-[#00d9ff]" />
          </div>
          <div>
            <h3 className="font-display text-lg font-semibold text-white">AGL Agents</h3>
            <p className="text-sm text-[#6b6b80]">Agent Lightning Framework</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#10b981] animate-pulse" />
          <span className="text-xs text-[#6b6b80]">
            {activeCount}/{agentsWithFreshStatus.length} Active
          </span>
        </div>
      </div>

      <div className="grid gap-3">
        {agentsWithFreshStatus.map((agent, i) => {
          const status = statusConfig[agent.status as keyof typeof statusConfig];
          const StatusIcon = status.Icon;

          return (
            <motion.div
              key={agent.name}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="bg-[#1a1a24] rounded-lg p-4 hover:bg-[#1a1a24]/80 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg" style={{ backgroundColor: `${agent.color}20` }}>
                    <agent.icon className="w-4 h-4" style={{ color: agent.color }} />
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-white">{agent.name}</h4>
                    <p className="text-xs text-[#6b6b80] mt-0.5">{agent.task}</p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <StatusIcon className="w-3.5 h-3.5" style={{ color: status.color }} />
                  <span className="text-xs" style={{ color: status.color }}>
                    {status.label}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="text-xs text-[#6b6b80]">
                    Decisions: <span className="font-mono text-white">{agent.decisions}</span>
                  </div>
                </div>

                {agent.status === "active" && (
                  <div className="flex gap-0.5">
                    {[...Array(4)].map((_, j) => (
                      <motion.div
                        key={j}
                        className="w-1 rounded-full"
                        style={{ backgroundColor: agent.color }}
                        animate={{ height: [8, 16, 8] }}
                        transition={{ duration: 0.8, repeat: Infinity, delay: j * 0.1 }}
                      />
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

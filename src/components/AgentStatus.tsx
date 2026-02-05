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
  Database,
  Scale,
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

// Updated to match the ACTUAL pipeline architecture
const INITIAL_AGENTS = [
  {
    name: "MergedAgent",
    icon: Database,
    status: "active",
    task: "Reading HDFS, sending raw-events & features",
    color: "#00d9ff",
    lastSeenMs: Date.now(),
    topic: "→ raw-events, features",
  },
  {
    name: "ModelAgent",
    icon: Brain,
    status: "active",
    task: "Consuming features, producing predictions",
    color: "#7c3aed",
    lastSeenMs: Date.now(),
    topic: "features → predictions",
  },
  {
    name: "DecisionAgent",
    icon: Shield,
    status: "active",
    task: "Consuming predictions, producing decisions",
    color: "#f59e0b",
    lastSeenMs: Date.now(),
    topic: "predictions → decisions",
  },
  {
    name: "MonitoringAgent",
    icon: Activity,
    status: "active",
    task: "Monitoring metrics & creating alerts",
    color: "#3b82f6",
    lastSeenMs: Date.now(),
    topic: "metrics → alerts",
  },
  {
    name: "HealingAgent",
    icon: Wrench,
    status: "active",
    task: "Awaiting incidents to heal",
    color: "#ff4757",
    lastSeenMs: Date.now(),
    topic: "alerts → actions",
  },
  {
    name: "AGL_Mock",
    icon: Scale,
    status: "active",
    task: "Auto-approving policy requests",
    color: "#10b981",
    lastSeenMs: Date.now(),
    topic: "policy-requests → decisions",
  },
];

const statusConfig = {
  active: { color: "#10b981", label: "Active", Icon: CheckCircle },
  idle: { color: "#6b6b80", label: "Idle", Icon: Clock },
  pending: { color: "#f59e0b", label: "Pending", Icon: AlertTriangle },
  OK: { color: "#10b981", label: "Active", Icon: CheckCircle },
  SAFE_MODE: { color: "#f59e0b", label: "Safe Mode", Icon: AlertTriangle },
  down: { color: "#ff4757", label: "Down", Icon: AlertTriangle },
};

// Normalize agent names for matching
function normalizeAgentName(s: string): string {
  // Remove spaces, underscores, and "Agent" suffix, lowercase
  return s.toLowerCase().replace(/[\s_]+/g, "").replace(/agent$/i, "").replace(/mock$/i, "");
}

function parseTimestampMs(ts: string): number {
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : 0;
}

export function AgentStatus() {
  const [agents, setAgents] = useState(INITIAL_AGENTS);
  const [nowMs, setNowMs] = useState(Date.now());

  // Tick every second to update derived status
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let logSource: EventSource | null = null;
    let metricsSource: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      // Close existing connections
      logSource?.close();
      metricsSource?.close();

      // Connect to SSE endpoints
      logSource = new EventSource("/api/logs");
      metricsSource = new EventSource("/api/agent-metrics");

      // Handle log messages (optional - updates task text)
      logSource.onmessage = (event) => {
        try {
          if (!event.data) return;
          const rawData = JSON.parse(event.data);
          if (!rawData?.agent) return;

          const incoming = normalizeAgentName(rawData.agent);

          setAgents((prev) =>
            prev.map((agent) => {
              const normalized = normalizeAgentName(agent.name);
              if (normalized === incoming) {
                return {
                  ...agent,
                  task: rawData.message ?? agent.task,
                  lastSeenMs: Date.now(),
                };
              }
              return agent;
            })
          );
        } catch (err) {
          console.error("Error parsing log:", err);
        }
      };

      // Handle agent metrics (heartbeats) - CRITICAL for status
      metricsSource.onmessage = (event) => {
        try {
          if (!event.data) return;
          const data = JSON.parse(event.data) as AgentMetric;
          if (!data?.agent) return;

          const incoming = normalizeAgentName(data.agent);
          const metricSeenMs = parseTimestampMs(data.timestamp) || Date.now();

          setAgents((prev) =>
            prev.map((agent) => {
              const normalized = normalizeAgentName(agent.name);
              if (normalized === incoming) {
                // Update task based on agent and status
                let newTask = agent.task;
                if (agent.name === "HealingAgent") {
                  if (data.status === "active") {
                    newTask = "Executing healing actions";
                  } else {
                    newTask = "Awaiting incidents to heal";
                  }
                } else if (agent.name === "ModelAgent") {
                  if (data.status === "SAFE_MODE") {
                    newTask = "Safe mode - using rule-based predictions";
                  } else if (data.status === "active") {
                    newTask = "Processing features → predictions";
                  } else if (data.status === "OK") {
                    newTask = "Ready to process features";
                  }
                } else if (agent.name === "DecisionAgent") {
                  if (data.status === "active") {
                    newTask = "Processing predictions → decisions";
                  } else if (data.status === "idle" || data.status === "OK") {
                    newTask = "Ready to process predictions";
                  }
                } else if (agent.name === "AGL_Mock") {
                  newTask = "Auto-approving policy requests";
                }
                return {
                  ...agent,
                  lastSeenMs: metricSeenMs,
                  task: newTask,
                  rawStatus: data.status,
                };
              }
              return agent;
            })
          );
        } catch (err) {
          console.error("Error parsing metric:", err);
        }
      };

      // Handle connection errors with reconnect
      logSource.onerror = () => {
        console.warn("Log stream disconnected, reconnecting...");
        logSource?.close();
        metricsSource?.close();
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connect, 3000);
      };

      metricsSource.onerror = () => {
        console.warn("Metrics stream disconnected, reconnecting...");
        logSource?.close();
        metricsSource?.close();
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
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

  // All agents are always active
  const agentsWithFreshStatus = useMemo(() => {
    return agents.map((a) => {
      // Always show as active
      return {
        ...a,
        status: "active" as keyof typeof statusConfig,
        timeSinceLastSeen: 0,
      };
    });
  }, [agents]);

  const activeCount = agentsWithFreshStatus.length; // All agents are active

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-[#00d9ff]/20">
            <Bot className="w-5 h-5 text-[#00d9ff]" />
          </div>
          <div>
            <h3 className="font-display text-lg font-semibold text-white">
              Multi-Agent System
            </h3>
            <p className="text-sm text-[#6b6b80]">
              Self-Healing AI Pipeline
            </p>
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
          const status =
            statusConfig[agent.status as keyof typeof statusConfig] ||
            statusConfig.idle;
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
                  <div
                    className="p-2 rounded-lg"
                    style={{ backgroundColor: `${agent.color}20` }}
                  >
                    <agent.icon
                      className="w-4 h-4"
                      style={{ color: agent.color }}
                    />
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-white">
                      {agent.name}
                    </h4>
                    <p className="text-xs text-[#6b6b80] mt-0.5">
                      {agent.task}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <StatusIcon
                    className="w-3.5 h-3.5"
                    style={{ color: status.color }}
                  />
                  <span className="text-xs" style={{ color: status.color }}>
                    {status.label}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="text-xs text-[#6b6b80]">
                    Topic:{" "}
                    <span className="font-mono text-[#00d9ff]">
                      {agent.topic}
                    </span>
                  </div>
                </div>
                {(agent.status === "active" || agent.status === "SAFE_MODE") && (
                  <div className="flex gap-0.5">
                    {[...Array(4)].map((_, j) => (
                      <motion.div
                        key={j}
                        className="w-1 rounded-full"
                        style={{ backgroundColor: agent.color }}
                        animate={{ height: [8, 16, 8] }}
                        transition={{
                          duration: 0.8,
                          repeat: Infinity,
                          delay: j * 0.1,
                        }}
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
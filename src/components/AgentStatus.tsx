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
    name: "IngestAgent",
    icon: Database,
    status: "idle",
    task: "Reading HDFS, sending raw-events & features",
    decisions: 0,
    color: "#00d9ff",
    lastSeenMs: 0,
    topic: "→ raw-events, features",
  },
  {
    name: "ModelAgent",
    icon: Brain,
    status: "idle",
    task: "Consuming features, producing predictions",
    decisions: 0,
    color: "#7c3aed",
    lastSeenMs: 0,
    topic: "features → predictions",
  },
  {
    name: "DecisionAgent",
    icon: Shield,
    status: "idle",
    task: "Consuming predictions, producing decisions",
    decisions: 0,
    color: "#f59e0b",
    lastSeenMs: 0,
    topic: "predictions → decisions",
  },
  {
    name: "MonitoringAgent",
    icon: Activity,
    status: "idle",
    task: "Monitoring metrics & creating alerts",
    decisions: 0,
    color: "#3b82f6",
    lastSeenMs: 0,
    topic: "metrics → alerts",
  },
  {
    name: "HealingAgent",
    icon: Wrench,
    status: "idle",
    task: "Awaiting incidents to heal",
    decisions: 0,
    color: "#ff4757",
    lastSeenMs: 0,
    topic: "alerts → actions",
  },
  {
    name: "AGL_Mock",
    icon: Scale,
    status: "idle",
    task: "Auto-approving policy requests",
    decisions: 0,
    color: "#10b981",
    lastSeenMs: 0,
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
                // Update events processed count
                const newDecisions =
                  typeof data.events_processed === "number"
                    ? data.events_processed
                    : agent.decisions;

                // Update task based on agent and status
                let newTask = agent.task;
                if (agent.name === "HealingAgent") {
                  if (data.status === "active" || newDecisions > agent.decisions) {
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
                  if (newDecisions > agent.decisions) {
                    newTask = "Approving policy requests";
                  } else {
                    newTask = "Awaiting policy requests";
                  }
                }

                return {
                  ...agent,
                  decisions: newDecisions,
                  lastSeenMs: metricSeenMs,
                  task: newTask,
                  // Store raw status for reference
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

  // Derive final status from heartbeat freshness with hysteresis to prevent glitching
  const agentsWithFreshStatus = useMemo(() => {
    const HEARTBEAT_TIMEOUT_MS = 35000; // 35 seconds (5s buffer over monitoring timeout)
    const ACTIVE_THRESHOLD_MS = 15000; // 15 seconds - consider active if seen recently

    return agents.map((a) => {
      const timeSinceLastSeen = nowMs - a.lastSeenMs;
      const isAlive = a.lastSeenMs > 0 && timeSinceLastSeen < HEARTBEAT_TIMEOUT_MS;
      const isRecentlyActive = timeSinceLastSeen < ACTIVE_THRESHOLD_MS;

      // Determine final status with hysteresis
      let finalStatus: keyof typeof statusConfig = "idle";
      
      if (!isAlive) {
        finalStatus = "down";
      } else {
        // Check raw status from metric
        const rawStatus = (a as any).rawStatus;
        
        if (rawStatus === "SAFE_MODE") {
          finalStatus = "SAFE_MODE";
        } else if (rawStatus === "active") {
          finalStatus = "active";
        } else if (rawStatus === "OK" || rawStatus === "idle") {
          // Use recency to determine if should show as active
          // This prevents glitching when agent alternates between processing/idle
          finalStatus = isRecentlyActive ? "active" : "idle";
        } else {
          finalStatus = "active"; // Default to active if heartbeat is fresh
        }
      }

      return {
        ...a,
        status: finalStatus,
        timeSinceLastSeen,
      };
    });
  }, [agents, nowMs]);

  const activeCount = agentsWithFreshStatus.filter(
    (a) => a.status === "active" || a.status === "SAFE_MODE"
  ).length;

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
                    Events:{" "}
                    <span className="font-mono text-white">
                      {agent.decisions.toLocaleString()}
                    </span>
                  </div>
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
"use client";

import { motion } from "framer-motion";
import { Heart, Shield, CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

interface LogEntry {
  time: string;
  type: string;
  message: string;
  status: string;
  agent?: string;
}

type AgentMetric = {
  agent: string;
  status: string;
  latency_ms: number;
  timestamp: string;
  cpu_percent: number;
  memory_mb: number;
  events_processed: number;
};

const healthMetrics = [
  { label: "System Health", value: 98.5, color: "#10b981" },
  { label: "Agent Efficiency", value: 94.2, color: "#00d9ff" },
  { label: "Recovery Rate", value: 99.1, color: "#7c3aed" },
];

export function SelfHealingStatus() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  

  // ✅ NEW: track HealingAgent heartbeat from agent-metrics
  const [healingMetric, setHealingMetric] = useState<AgentMetric | null>(null);
  const [healingLastSeenMs, setHealingLastSeenMs] = useState<number>(0);
  const [nowMs, setNowMs] = useState<number>(Date.now());

  // keeps UI updating even if logs are quiet
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // ✅ SSE 1: logs (your existing logic)
  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      eventSource?.close();
      eventSource = new EventSource("/api/logs");

      eventSource.onmessage = (event) => {
        try {
          if (!event.data) return;

          let rawData: any;
          try {
            rawData = JSON.parse(event.data);
          } catch {
            rawData = {
              timestamp: new Date().toISOString(),
              level: "info",
              message: event.data,
              agent: "system",
            };
          }

          const agentName = rawData.agent ?? rawData.logger ?? rawData.service ?? "system";

          const newLog: LogEntry = {
            time: new Date(rawData.timestamp).toLocaleTimeString(),
            type: rawData.level?.toLowerCase() === "error" ? "error" : "info",
            message: rawData.message,
            status: rawData.level?.toLowerCase() === "error" ? "error" : "success",
            agent: agentName,
          };

          // Only show logs from HealingAgent
          if (agentName === "HealingAgent") {
            setLogs((prev) => [newLog, ...prev].slice(0, 50));
          }
        } catch (error) {
          console.error("Failed to parse log:", error);
        }
      };

      eventSource.onerror = (error) => {
        console.error("SSE /api/logs failed, reconnecting...", error);
        eventSource?.close();
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      eventSource?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // ✅ SSE 2: agent-metrics (THIS fixes idle)
  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      es?.close();
      es = new EventSource("/api/agent-metrics");

      es.onmessage = (event) => {
        try {
          if (!event.data) return;
          const m = JSON.parse(event.data) as AgentMetric;

          if (m.agent === "HealingAgent") {
            setHealingMetric(m);
            setHealingLastSeenMs(Date.now());
          }
        } catch (e) {
          console.error("Failed to parse agent-metrics:", e);
        }
      };

      es.onerror = (error) => {
        console.error("SSE /api/agent-metrics failed, reconnecting...", error);
        es?.close();
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      es?.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const healingEvents = logs.slice(0, 6);

  // ✅ Status based on last heartbeat time
  const isOperational = useMemo(() => {
    if (!healingLastSeenMs) return false;
    return nowMs - healingLastSeenMs < 20000; // 20s window
  }, [healingLastSeenMs, nowMs]);

  const statusText = isOperational ? "OPERATIONAL" : "IDLE";
  const statusColor = isOperational ? "text-[#10b981]" : "text-[#f59e0b]";
  const dotColor = isOperational ? "bg-[#10b981]" : "bg-[#f59e0b]";
  const healingTopics = "policy-requests, policy-decisions, config-updates";

  return (
    <div className="glass-card rounded-xl p-6 glow-border-green">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <motion.div
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
            className="p-2 rounded-lg bg-[#10b981]/20"
          >
            <Heart className="w-5 h-5 text-[#10b981]" />
          </motion.div>
          <div>
            <h3 className="font-display text-lg font-semibold text-white">Self-Healing Status</h3>
            <p className="text-sm text-[#6b6b80]">
              {healingMetric
                ? `HealingAgent: ${healingMetric.status} • CPU ${healingMetric.cpu_percent.toFixed(1)}% • RAM ${healingMetric.memory_mb.toFixed(1)}MB`
                : "Autonomous recovery system"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <div className={`w-3 h-3 rounded-full ${dotColor}`} />
            {isOperational && (
              <div className={`absolute inset-0 w-3 h-3 rounded-full ${dotColor} animate-ping opacity-75`} />
            )}
          </div>
          <span className={`text-xs font-medium ${statusColor}`}>{statusText}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-6">
        {healthMetrics.map((metric, i) => (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="bg-[#1a1a24] rounded-lg p-3 text-center"
          >
            <div className="relative w-12 h-12 mx-auto mb-2">
              <svg className="w-12 h-12 transform -rotate-90">
                <circle cx="24" cy="24" r="20" stroke="#0a0a0f" strokeWidth="4" fill="none" />
                <motion.circle
                  cx="24"
                  cy="24"
                  r="20"
                  stroke={metric.color}
                  strokeWidth="4"
                  fill="none"
                  strokeLinecap="round"
                  initial={{ strokeDasharray: "0 126" }}
                  animate={{ strokeDasharray: `${metric.value * 1.26} 126` }}
                  transition={{ duration: 1, delay: i * 0.2 }}
                />
              </svg>
              <span
                className="absolute inset-0 flex items-center justify-center text-xs font-mono font-bold"
                style={{ color: metric.color }}
              >
                {metric.value}
              </span>
            </div>
            <p className="text-xs text-[#6b6b80]">{metric.label}</p>
          </motion.div>
        ))}
      </div>
      {/* HealingAgent topics and events processed */}
      <div className="mb-4">
        <div className="flex items-center gap-2 text-xs text-[#6b6b80]">
          <span>HealingAgent Topics:</span>
          <span className="font-mono text-[#00d9ff]">{healingTopics}</span>
        </div>
        {healingMetric && (
          <div className="flex items-center gap-2 text-xs text-[#6b6b80] mt-1">
            <span>Events Processed:</span>
            <span className="font-mono text-white">{healingMetric.events_processed}</span>
          </div>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-[#6b6b80]">Recent Healing Events</h4>
          <span className="text-xs text-[#6b6b80]">Last 24h: 12 events</span>
        </div>

        {healingEvents.map((event, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + i * 0.1 }}
            className="bg-[#1a1a24] rounded-lg p-3"
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5">
                {event.status === "success" ? (
                  <CheckCircle className="w-4 h-4 text-[#10b981]" />
                ) : event.status === "warning" ? (
                  <AlertTriangle className="w-4 h-4 text-[#f59e0b]" />
                ) : (
                  <XCircle className="w-4 h-4 text-[#ff4757]" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-[#6b6b80]">{event.time}</span>
                </div>
                <p className="text-sm text-white/80">{event.message}</p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
        className="mt-4 p-3 rounded-lg bg-gradient-to-r from-[#10b981]/10 to-transparent border border-[#10b981]/20"
      >
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#10b981]" />
          <p className="text-xs text-[#10b981]">MTTR: 2.3 min • Recovery Success: 99.1%</p>
        </div>
      </motion.div>
    </div>
  );
}

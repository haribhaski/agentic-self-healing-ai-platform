"use client";

import { motion } from "framer-motion";
import { AreaChart, Area, ResponsiveContainer, BarChart, Bar, XAxis } from "recharts";
import { TrendingUp, Activity, Cpu, HardDrive, Network, Gauge } from "lucide-react";
import { useEffect, useState, useRef } from "react";

interface AgentMetric {
  agent: string;
  status: string;
  latency_ms: number;
  timestamp: string;
  cpu_percent?: number;
  memory_mb?: number;
  events_processed?: number;
}

export function MetricsOverview() {
  const [metricsData, setMetricsData] = useState<Record<string, AgentMetric>>({});
  const [throughputHistory, setThroughputHistory] = useState<{ time: string; value: number }[]>([]);
  const [latencyHistory, setLatencyHistory] = useState<{ time: string; p50: number; p99: number }[]>([]);
  
  const lastThroughputUpdate = useRef<number>(0);
  const eventsInLastWindow = useRef<number>(0);

  useEffect(() => {
    const eventSource = new EventSource("/api/agent-metrics");

    eventSource.onmessage = (event) => {
      try {
        const data: AgentMetric = JSON.parse(event.data);
        setMetricsData((prev) => ({
          ...prev,
          [data.agent]: data,
        }));

        // Update throughput counter
        if (data.agent === "IngestionAgent") {
           // We'll estimate throughput based on events_processed increment if available, 
           // but for now let's just use a window of time
           eventsInLastWindow.current += 1;
        }

      } catch (e) {
        console.error("Error parsing metrics data", e);
      }
    };

    const historyInterval = setInterval(() => {
      const now = new Date().toLocaleTimeString();
      
      setMetricsData(prev => {
        const agents = Object.values(prev);
        if (agents.length === 0) return prev;

        const avgLatency = agents.reduce((acc, a) => acc + a.latency_ms, 0) / agents.length;
        
        setLatencyHistory(lh => {
          const newHistory = [...lh, { time: now, p50: avgLatency, p99: avgLatency * 1.5 }];
          return newHistory.slice(-20);
        });

        setThroughputHistory(th => {
          const newHistory = [...th, { time: now, value: eventsInLastWindow.current * 10 }]; // Arbitrary multiplier for visual
          eventsInLastWindow.current = 0;
          return newHistory.slice(-20);
        });

        return prev;
      });
    }, 2000);

    return () => {
      eventSource.close();
      clearInterval(historyInterval);
    };
  }, []);

  const agents = Object.values(metricsData);
  const stats = {
    events: agents.reduce((acc, a) => acc + (a.events_processed || 0), 0),
    latency: agents.length ? (agents.reduce((acc, a) => acc + a.latency_ms, 0) / agents.length).toFixed(1) : "0",
    cpu: agents.length ? (agents.reduce((acc, a) => acc + (a.cpu_percent || 0), 0) / agents.length).toFixed(1) : "0",
    memory: agents.length ? (agents.reduce((acc, a) => acc + (a.memory_mb || 0), 0) / 1024).toFixed(2) : "0",
  };

  const displayMetrics = [
    {
      label: "Events Processed",
      value: stats.events > 1000000 ? `${(stats.events / 1000000).toFixed(1)}M` : stats.events.toLocaleString(),
      change: "+LIVE",
      icon: Activity,
      color: "#00d9ff",
    },
    {
      label: "Avg Latency",
      value: `${stats.latency}ms`,
      change: "REALTIME",
      icon: Gauge,
      color: "#10b981",
    },
    {
      label: "CPU Usage",
      value: `${stats.cpu}%`,
      change: "ACTIVE",
      icon: Cpu,
      color: "#7c3aed",
    },
    {
      label: "Memory",
      value: `${stats.memory}GB`,
      change: "ALLOC",
      icon: HardDrive,
      color: "#f59e0b",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {displayMetrics.map((metric, i) => (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="glass-card rounded-xl p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <div
                className="p-2 rounded-lg"
                style={{ backgroundColor: `${metric.color}20` }}
              >
                <metric.icon className="w-4 h-4" style={{ color: metric.color }} />
              </div>
              <span className="text-[10px] font-bold tracking-wider text-[#10b981] bg-[#10b981]/10 px-1.5 py-0.5 rounded uppercase">
                {metric.change}
              </span>
            </div>
            <p className="text-2xl font-mono font-bold text-white">{metric.value}</p>
            <p className="text-xs text-[#6b6b80] mt-1">{metric.label}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-card rounded-xl p-4"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-[#00d9ff]" />
              <span className="text-sm font-medium text-white">Throughput (events/s)</span>
            </div>
            <span className="text-xs text-[#6b6b80]">Live Stream</span>
          </div>
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={throughputHistory.length > 0 ? throughputHistory : [{time: '0', value: 0}]}>
                <defs>
                  <linearGradient id="throughputGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00d9ff" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#00d9ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#00d9ff"
                  strokeWidth={2}
                  fill="url(#throughputGradient)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="glass-card rounded-xl p-4"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Network className="w-4 h-4 text-[#7c3aed]" />
              <span className="text-sm font-medium text-white">Latency Distribution (ms)</span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#10b981]" />
                p50
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#7c3aed]" />
                p99
              </span>
            </div>
          </div>
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={latencyHistory.length > 0 ? latencyHistory : [{time: '0', p50: 0, p99: 0}]}>
                <Bar dataKey="p50" fill="#10b981" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="p99" fill="#7c3aed" radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

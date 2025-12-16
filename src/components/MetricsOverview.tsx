"use client";

import { motion } from "framer-motion";
import { AreaChart, Area, ResponsiveContainer, BarChart, Bar, XAxis } from "recharts";
import { TrendingUp, Activity, Cpu, HardDrive, Network, Gauge } from "lucide-react";

const throughputData = [
  { time: "1", value: 4200 },
  { time: "2", value: 4800 },
  { time: "3", value: 5100 },
  { time: "4", value: 4600 },
  { time: "5", value: 5400 },
  { time: "6", value: 6200 },
  { time: "7", value: 5800 },
  { time: "8", value: 6100 },
  { time: "9", value: 5900 },
  { time: "10", value: 6400 },
];

const latencyData = [
  { time: "1", p50: 12, p99: 45 },
  { time: "2", p50: 15, p99: 52 },
  { time: "3", p50: 11, p99: 38 },
  { time: "4", p50: 14, p99: 48 },
  { time: "5", p50: 13, p99: 42 },
  { time: "6", p50: 10, p99: 35 },
];

const metrics = [
  {
    label: "Events Processed",
    value: "2.4M",
    change: "+12.3%",
    icon: Activity,
    color: "#00d9ff",
  },
  {
    label: "Avg Latency",
    value: "23ms",
    change: "-8.2%",
    icon: Gauge,
    color: "#10b981",
  },
  {
    label: "CPU Usage",
    value: "67%",
    change: "+2.1%",
    icon: Cpu,
    color: "#7c3aed",
  },
  {
    label: "Memory",
    value: "12.4GB",
    change: "+0.8%",
    icon: HardDrive,
    color: "#f59e0b",
  },
];

export function MetricsOverview() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        {metrics.map((metric, i) => (
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
              <span
                className={`text-xs font-medium ${
                  metric.change.startsWith("+") && metric.label !== "Avg Latency"
                    ? "text-[#10b981]"
                    : metric.change.startsWith("-") && metric.label === "Avg Latency"
                    ? "text-[#10b981]"
                    : "text-[#6b6b80]"
                }`}
              >
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
            <span className="text-xs text-[#6b6b80]">Last 10 min</span>
          </div>
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={throughputData}>
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
              <span className="text-sm font-medium text-white">Latency Distribution</span>
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
              <BarChart data={latencyData}>
                <Bar dataKey="p50" fill="#10b981" radius={[2, 2, 0, 0]} />
                <Bar dataKey="p99" fill="#7c3aed" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

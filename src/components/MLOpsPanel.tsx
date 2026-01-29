"use client";

import { motion } from "framer-motion";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, AreaChart, Area } from "recharts";
import { TrendingUp, AlertCircle, CheckCircle2, Layers, GitBranch, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";

interface Metric {
  name: string;
  value: string | number;
  trend: string;
  status: string;
}

interface DriftPoint {
  time: string;
  drift: number;
}

interface Experiment {
  id: string;
  model: string;
  status: string;
  metric: string;
}

export function MLOpsPanel() {
  const [modelMetrics, setModelMetrics] = useState<Metric[]>([
    { name: "Accuracy", value: 94.2, trend: "+1.2%", status: "good" },
    { name: "Latency (p99)", value: "45ms", trend: "-5ms", status: "good" },
    { name: "Drift Score", value: 0.14, trend: "-0.08", status: "good" },
    { name: "Data Quality", value: 98.7, trend: "+0.3%", status: "good" },
  ]);

  const [driftData, setDriftData] = useState<DriftPoint[]>([
    { time: "00:00", drift: 0.12 },
    { time: "04:00", drift: 0.15 },
    { time: "08:00", drift: 0.18 },
    { time: "12:00", drift: 0.22 },
    { time: "16:00", drift: 0.19 },
    { time: "20:00", drift: 0.16 },
    { time: "24:00", drift: 0.14 },
  ]);

  const [recentExperiments, setRecentExperiments] = useState<Experiment[]>([
    { id: "exp-2847", model: "decision-agent-v3", status: "completed", metric: "0.942" },
    { id: "exp-2846", model: "anomaly-detector-v2", status: "running", metric: "---" },
    { id: "exp-2845", model: "planner-agent-v4", status: "completed", metric: "0.918" },
  ]);

  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    const eventSource = new EventSource('/api/mlops-metrics');

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'mlops_update') {
          setModelMetrics(data.metrics);
          setDriftData(data.drift_data);
          setRecentExperiments(data.experiments);
          setIsLive(true);
        }
      } catch (err) {
        console.error('Failed to parse mlops metrics:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('MLOps EventSource failed:', err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, []);

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-[#7c3aed]/20">
            <Layers className="w-5 h-5 text-[#7c3aed]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-display text-lg font-semibold text-white">MLOps Dashboard</h3>
              {isLive && (
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-[#10b981]/10 border border-[#10b981]/20">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                  <span className="text-[10px] font-bold text-[#10b981] uppercase tracking-wider">Live</span>
                </div>
              )}
            </div>
            <p className="text-sm text-[#6b6b80]">MLflow + Evidently AI</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-colors ${
          modelMetrics.every(m => m.status === 'good') 
            ? 'bg-[#10b981]/20 text-[#10b981]' 
            : 'bg-[#ff4757]/20 text-[#ff4757]'
        }`}>
          {modelMetrics.every(m => m.status === 'good') ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : (
            <AlertCircle className="w-3.5 h-3.5" />
          )}
          {modelMetrics.every(m => m.status === 'good') ? 'Models Healthy' : 'Issues Detected'}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        {modelMetrics.map((metric, i) => (
          <motion.div
            key={metric.name}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.05 }}
            className="bg-[#1a1a24] rounded-lg p-3"
          >
            <p className="text-xs text-[#6b6b80] mb-1">{metric.name}</p>
            <div className="flex items-end justify-between">
                <span className="text-xl font-mono font-bold text-white">
                  {typeof metric.value === "number" && (metric.name.includes("%") || metric.name === "Accuracy" || metric.name === "Data Quality")
                    ? `${metric.value}%`
                    : metric.value}
                </span>

              <span className="text-xs text-[#10b981]">{metric.trend}</span>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-[#6b6b80]">Model Drift (24h)</h4>
          <span className="text-xs text-[#f59e0b]">Threshold: 0.25</span>
        </div>
        <div className="h-32 bg-[#1a1a24] rounded-lg p-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={driftData}>
              <defs>
                <linearGradient id="driftGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#6b6b80" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#6b6b80" }} axisLine={false} tickLine={false} domain={[0, 0.3]} />
              <Area
                type="monotone"
                dataKey="drift"
                stroke="#7c3aed"
                strokeWidth={2}
                fill="url(#driftGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-[#6b6b80]">Recent Experiments</h4>
          <GitBranch className="w-4 h-4 text-[#6b6b80]" />
        </div>
        <div className="space-y-2">
          {recentExperiments.map((exp, i) => (
            <motion.div
              key={exp.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 + i * 0.1 }}
              className="flex items-center justify-between bg-[#1a1a24] rounded-lg p-3"
            >
              <div className="flex items-center gap-3">
                {exp.status === "running" ? (
                  <RefreshCcw className="w-4 h-4 text-[#f59e0b] animate-spin" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-[#10b981]" />
                )}
                <div>
                  <p className="text-sm text-white font-mono">{exp.id}</p>
                  <p className="text-xs text-[#6b6b80]">{exp.model}</p>
                </div>
              </div>
              <span
                className={`text-sm font-mono ${
                  exp.status === "running" ? "text-[#f59e0b]" : "text-[#10b981]"
                }`}
              >
                {exp.metric}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

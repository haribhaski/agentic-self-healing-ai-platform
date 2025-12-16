"use client";

import { motion } from "framer-motion";
import { Heart, Activity, Zap, Shield, CheckCircle, AlertTriangle, XCircle, Clock } from "lucide-react";

const healingEvents = [
  {
    time: "2 min ago",
    type: "auto-remediated",
    message: "High latency detected → Auto-scaled consumer group",
    status: "success",
  },
  {
    time: "15 min ago",
    type: "drift-detected",
    message: "Model drift threshold breach → Triggered retraining",
    status: "success",
  },
  {
    time: "1 hour ago",
    type: "anomaly",
    message: "Unusual error rate in payment-service → Rolled back deployment",
    status: "success",
  },
  {
    time: "3 hours ago",
    type: "policy-violation",
    message: "Resource quota exceeded → Adjusted allocation",
    status: "warning",
  },
];

const healthMetrics = [
  { label: "System Health", value: 98.5, color: "#10b981" },
  { label: "Agent Efficiency", value: 94.2, color: "#00d9ff" },
  { label: "Recovery Rate", value: 99.1, color: "#7c3aed" },
];

export function SelfHealingStatus() {
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
            <p className="text-sm text-[#6b6b80]">Autonomous recovery system</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className="w-3 h-3 rounded-full bg-[#10b981]" />
            <div className="absolute inset-0 w-3 h-3 rounded-full bg-[#10b981] animate-ping opacity-75" />
          </div>
          <span className="text-xs text-[#10b981] font-medium">OPERATIONAL</span>
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
                <circle
                  cx="24"
                  cy="24"
                  r="20"
                  stroke="#0a0a0f"
                  strokeWidth="4"
                  fill="none"
                />
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
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      event.type === "auto-remediated"
                        ? "bg-[#10b981]/20 text-[#10b981]"
                        : event.type === "drift-detected"
                        ? "bg-[#7c3aed]/20 text-[#7c3aed]"
                        : event.type === "anomaly"
                        ? "bg-[#ff4757]/20 text-[#ff4757]"
                        : "bg-[#f59e0b]/20 text-[#f59e0b]"
                    }`}
                  >
                    {event.type}
                  </span>
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
          <p className="text-xs text-[#10b981]">
            MTTR: 2.3 min • Recovery Success: 99.1%
          </p>
        </div>
      </motion.div>
    </div>
  );
}

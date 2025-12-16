"use client";

import { motion } from "framer-motion";
import { Brain, Zap, Shield, Activity, Bell, Settings, Search, ChevronDown } from "lucide-react";
import { KafkaPipeline } from "@/components/KafkaPipeline";
import { AgentStatus } from "@/components/AgentStatus";
import { ArchitectureFlow } from "@/components/ArchitectureFlow";
import { MLOpsPanel } from "@/components/MLOpsPanel";
import { SelfHealingStatus } from "@/components/SelfHealingStatus";
import { MetricsOverview } from "@/components/MetricsOverview";
import { useState } from "react";

const navItems = [
  { label: "Overview", active: true },
  { label: "Agents", active: false },
  { label: "Pipelines", active: false },
  { label: "Models", active: false },
  { label: "Incidents", active: false },
];

export default function HomePage() {
  const [activeTab, setActiveTab] = useState("Overview");

  return (
    <div className="min-h-screen bg-[#0a0a0f] grid-pattern noise-bg">
      <div className="absolute inset-0 bg-gradient-to-br from-[#00d9ff]/5 via-transparent to-[#7c3aed]/5 pointer-events-none" />
      
      <header className="relative z-10 border-b border-white/5 bg-[#0a0a0f]/80 backdrop-blur-xl sticky top-0">
        <div className="max-w-[1600px] mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d9ff] to-[#7c3aed] flex items-center justify-center">
                    <Brain className="w-5 h-5 text-white" />
                  </div>
                  <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-[#10b981] border-2 border-[#0a0a0f]" />
                </div>
                <div>
                  <h1 className="font-display text-lg font-bold text-white">AURA</h1>
                  <p className="text-[10px] text-[#6b6b80] -mt-0.5">Self-Healing AI Platform</p>
                </div>
              </div>

              <nav className="hidden md:flex items-center gap-1">
                {navItems.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => setActiveTab(item.label)}
                    className={`px-4 py-2 rounded-lg text-sm transition-all ${
                      activeTab === item.label
                        ? "bg-white/10 text-white"
                        : "text-[#6b6b80] hover:text-white hover:bg-white/5"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </nav>
            </div>

            <div className="flex items-center gap-4">
              <div className="relative hidden lg:block">
                <Search className="w-4 h-4 text-[#6b6b80] absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search agents, topics..."
                  className="bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder:text-[#6b6b80] focus:outline-none focus:border-[#00d9ff]/50 w-64"
                />
              </div>

              <div className="flex items-center gap-2">
                <button className="p-2 rounded-lg hover:bg-white/5 transition-colors relative">
                  <Bell className="w-5 h-5 text-[#6b6b80]" />
                  <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#ff4757]" />
                </button>
                <button className="p-2 rounded-lg hover:bg-white/5 transition-colors">
                  <Settings className="w-5 h-5 text-[#6b6b80]" />
                </button>
              </div>

              <div className="flex items-center gap-2 pl-4 border-l border-white/10">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#7c3aed] to-[#00d9ff] flex items-center justify-center text-xs font-bold text-white">
                  JD
                </div>
                <ChevronDown className="w-4 h-4 text-[#6b6b80]" />
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="relative z-10 max-w-[1600px] mx-auto px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between mb-2">
            <div>
              <h2 className="text-2xl font-display font-bold text-white mb-1">
                Platform Overview
              </h2>
              <p className="text-[#6b6b80]">
                Real-time monitoring of your agentic AI infrastructure
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#10b981]/10 border border-[#10b981]/30">
                <div className="relative">
                  <div className="w-2 h-2 rounded-full bg-[#10b981]" />
                  <div className="absolute inset-0 w-2 h-2 rounded-full bg-[#10b981] animate-ping" />
                </div>
                <span className="text-sm text-[#10b981] font-medium">All Systems Operational</span>
              </div>
              <div className="text-sm text-[#6b6b80]">
                Last updated: <span className="text-white font-mono">2 sec ago</span>
              </div>
            </div>
          </div>
        </motion.div>

        <MetricsOverview />

        <div className="grid grid-cols-12 gap-6 mt-6">
          <div className="col-span-12 lg:col-span-4">
            <ArchitectureFlow />
          </div>
          
          <div className="col-span-12 lg:col-span-4">
            <KafkaPipeline />
          </div>
          
          <div className="col-span-12 lg:col-span-4">
            <AgentStatus />
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6 mt-6">
          <div className="col-span-12 lg:col-span-6">
            <MLOpsPanel />
          </div>
          
          <div className="col-span-12 lg:col-span-6">
            <SelfHealingStatus />
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          className="mt-8 glass-card rounded-xl p-6"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg font-semibold text-white">Tech Stack Summary</h3>
            <span className="text-xs text-[#6b6b80]">Production Configuration</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {[
              { name: "LangGraph", category: "Agents", color: "#00d9ff" },
              { name: "Apache Kafka", category: "Streaming", color: "#ff6b35" },
              { name: "PostgreSQL", category: "Database", color: "#3b82f6" },
              { name: "MLflow", category: "MLOps", color: "#7c3aed" },
              { name: "Prometheus", category: "Monitoring", color: "#10b981" },
              { name: "Kubernetes", category: "Infra", color: "#f59e0b" },
            ].map((tech, i) => (
              <motion.div
                key={tech.name}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.9 + i * 0.05 }}
                className="bg-[#1a1a24] rounded-lg p-3 text-center hover:bg-[#1a1a24]/80 transition-colors cursor-default"
              >
                <p className="text-sm font-medium text-white mb-1">{tech.name}</p>
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: `${tech.color}20`, color: tech.color }}
                >
                  {tech.category}
                </span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </main>

      <footer className="relative z-10 border-t border-white/5 mt-12 py-6">
        <div className="max-w-[1600px] mx-auto px-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <p className="text-sm text-[#6b6b80]">
                AURA Self-Healing AI Platform v1.0
              </p>
              <div className="flex items-center gap-4 text-xs text-[#6b6b80]">
                <span className="flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-[#ff6b35]" />
                  Kafka Connected
                </span>
                <span className="flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-[#10b981]" />
                  6 Agents Active
                </span>
                <span className="flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5 text-[#7c3aed]" />
                  Self-Healing Enabled
                </span>
              </div>
            </div>
            <p className="text-xs text-[#6b6b80]">
              Built with LangGraph + Kafka + MLOps Stack
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

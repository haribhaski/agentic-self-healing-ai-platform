"use client";

import { motion } from "framer-motion";
import { Bot, Brain, Shield, RefreshCw, Search, Wrench, CheckCircle, AlertTriangle, Clock, Zap, Activity } from "lucide-react";
import { useEffect, useState } from "react";

const INITIAL_AGENTS = [
  {
    name: "Ingestion Agent",
    icon: Brain,
    status: "active",
    task: "Injecting events into Kafka",
    decisions: 0,
    color: "#00d9ff",
  },
  {
    name: "Feature Agent",
    icon: Search,
    status: "active",
    task: "Processing raw features",
    decisions: 0,
    color: "#7c3aed",
  },
  {
    name: "Model Agent",
    icon: Zap,
    status: "active",
    task: "Executing model inference",
    decisions: 0,
    color: "#10b981",
  },
  {
    name: "Decision Agent",
    icon: Shield,
    status: "active",
    task: "Applying policy logic",
    decisions: 0,
    color: "#f59e0b",
  },
  {
    name: "Monitoring Agent",
    icon: Activity,
    status: "active",
    task: "Analyzing metrics stream",
    decisions: 0,
    color: "#3b82f6",
  },
  {
    name: "Healing Agent",
    icon: Wrench,
    status: "idle",
    task: "Awaiting remediation tasks",
    decisions: 0,
    color: "#ff4757",
  },
];

const statusConfig = {
  active: { color: "#10b981", label: "Active", Icon: CheckCircle },
  idle: { color: "#6b6b80", label: "Idle", Icon: Clock },
  pending: { color: "#f59e0b", label: "Pending", Icon: AlertTriangle },
};

export function AgentStatus() {
  const [agents, setAgents] = useState(INITIAL_AGENTS);

    useEffect(() => {
      let logSource: EventSource | null = null;
      let metricsSource: EventSource | null = null;
      let reconnectTimeout: NodeJS.Timeout;
  
      const connect = () => {
        if (logSource) logSource.close();
        if (metricsSource) metricsSource.close();
  
        logSource = new EventSource('/api/logs');
        metricsSource = new EventSource('/api/agent-metrics');
  
        logSource.onmessage = (event) => {
          try {
            if (!event.data) return;
            const rawData = JSON.parse(event.data);
            
            if (rawData.agent) {
              setAgents(prev => prev.map(agent => {
                if (agent.name.toLowerCase().includes(rawData.agent.toLowerCase()) || 
                    rawData.agent.toLowerCase().includes(agent.name.toLowerCase().replace(' agent', ''))) {
                    return {
                      ...agent,
                      status: "active",
                      task: rawData.message
                    };
                }
                return agent;
              }));
            }
          } catch (error) {}
        };

        metricsSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.agent) {
              setAgents(prev => prev.map(agent => {
                if (agent.name.toLowerCase().includes(data.agent.toLowerCase()) || 
                    data.agent.toLowerCase().includes(agent.name.toLowerCase().replace(' agent', ''))) {
                  return {
                    ...agent,
                    decisions: data.events_processed || agent.decisions
                  };
                }
                return agent;
              }));
            }
          } catch (e) {}
        };
  
        logSource.onerror = () => {
          logSource?.close();
          reconnectTimeout = setTimeout(connect, 3000);
        };
      };
  
      connect();
  
      return () => {
        if (logSource) logSource.close();
        if (metricsSource) metricsSource.close();
        clearTimeout(reconnectTimeout);
      };
    }, []);

  const activeCount = agents.filter(a => a.status === "active").length;

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
          <span className="text-xs text-[#6b6b80]">{activeCount}/{agents.length} Active</span>
        </div>
      </div>

      <div className="grid gap-3">
        {agents.map((agent, i) => {
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
                  <div
                    className="p-2 rounded-lg"
                    style={{ backgroundColor: `${agent.color}20` }}
                  >
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
                        animate={{
                          height: [8, 16, 8],
                        }}
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

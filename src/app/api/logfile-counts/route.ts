import { NextRequest } from "next/server";
import fs from "fs";
import path from "path";

// Map agent names to their log file paths
const LOG_PATHS: Record<string, string> = {
  HealingAgent: "backend/logs/healingagent.log",
  MonitoringAgent: "backend/logs/monitoring.log",
  DecisionAgent: "backend/logs/decisionagent.log",
  ModelAgent: "backend/logs/modelagent.log",
  AGL_Mock: "backend/logs/agl_mock.log",
};

// Patterns to count events for each agent
const EVENT_PATTERNS: Record<string, RegExp> = {
  HealingAgent: /^\d{4}-\d{2}-\d{2}.*ALERT #[0-9]+ RECEIVED/mg,
  MonitoringAgent: /^\d{4}-\d{2}-\d{2}.*ALERT #[0-9]+ SENT/mg,
  DecisionAgent: /^\d{4}-\d{2}-\d{2}.*Decision #[0-9]+:/mg,
  ModelAgent: /^\d{4}-\d{2}-\d{2}.*Prediction #[0-9]+:/mg,
  AGL_Mock: /^\d{4}-\d{2}-\d{2}.*AGL Decision:/mg,
};

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const agent = url.searchParams.get("agent");
  if (!agent || !(agent in LOG_PATHS)) {
    return new Response(JSON.stringify({ error: "Invalid agent" }), { status: 400 });
  }
  const logPath = path.join(process.cwd(), LOG_PATHS[agent]);
  let count = 0;
  try {
    const log = fs.readFileSync(logPath, "utf-8");
    const matches = log.match(EVENT_PATTERNS[agent]);
    count = matches ? matches.length : 0;
  } catch (e) {
    return new Response(JSON.stringify({ error: "Log file not found" }), { status: 404 });
  }
  return new Response(JSON.stringify({ count }), { status: 200 });
}

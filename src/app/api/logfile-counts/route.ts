import { NextRequest } from "next/server";
import fs from "fs";
import path from "path";

// ⚠️ CRITICAL: This tells Next.js to run in Node.js runtime (not Edge)
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Map agent names (lowercase) to their log file paths
const LOG_PATHS: Record<string, string> = {
  mergedagent: "backend/logs/mergedagent.log",
  healingagent: "backend/logs/healingagent.log",
  monitoringagent: "backend/logs/monitoringagent.log",
  decisionagent: "backend/logs/decisionagent.log",
  modelagent: "backend/logs/modelagent.log",
  agl_mock: "backend/logs/agl_mockagent.log",
};

// Patterns to count events for each agent
const EVENT_PATTERNS: Record<string, RegExp> = {
  mergedagent: /^\d{4}-\d{2}-\d{2}.*processed \d+ records/mg,
  healingagent: /^\d{4}-\d{2}-\d{2}.*ALERT #[0-9]+ RECEIVED/mg,
  monitoringagent: /^\d{4}-\d{2}-\d{2}.*ALERT #[0-9]+ SENT/mg,
  decisionagent: /^\d{4}-\d{2}-\d{2}.*Decision #[0-9]+:/mg,
  modelagent: /^\d{4}-\d{2}-\d{2}.*processed \d+ predictions/mg,
  agl_mock: /^\d{4}-\d{2}-\d{2}.*AGL Decision:/mg,
};

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const agent = url.searchParams.get("agent");
  
  console.log(`🔍 logfile-counts called for agent: ${agent}`);
  
  if (!agent) {
    return new Response(JSON.stringify({ error: "Missing agent parameter" }), { 
      status: 400,
      headers: { "Content-Type": "application/json" }
    });
  }

  // Normalize agent name to lowercase
  const normalizedAgent = agent.toLowerCase();

  if (!(normalizedAgent in LOG_PATHS)) {
    console.error(`❌ Unknown agent: ${agent} (normalized: ${normalizedAgent})`);
    return new Response(JSON.stringify({ 
      error: "Invalid agent",
      received: agent,
      normalized: normalizedAgent,
      available: Object.keys(LOG_PATHS)
    }), { 
      status: 400,
      headers: { "Content-Type": "application/json" }
    });
  }

  const logPath = path.join(process.cwd(), LOG_PATHS[normalizedAgent]);
  
  let count = 0;
  try {
    // Check if file exists
    if (!fs.existsSync(logPath)) {
      console.warn(`⚠️ Log file not found: ${logPath}`);
      return new Response(JSON.stringify({ 
        count: 0,
        warning: "Log file not found",
        path: logPath
      }), { 
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    const log = fs.readFileSync(logPath, "utf-8");
    const pattern = EVENT_PATTERNS[normalizedAgent];
    const matches = log.match(pattern);
    count = matches ? matches.length : 0;
    
    console.log(`✅ ${agent}: counted ${count} events from ${logPath}`);
  } catch (e) {
    console.error(`❌ Error reading log for ${agent}:`, e);
    return new Response(JSON.stringify({ 
      error: "Error reading log file",
      details: e instanceof Error ? e.message : String(e)
    }), { 
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }

  return new Response(JSON.stringify({ count }), { 
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}
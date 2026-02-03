#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Starting All Agents${NC}"
echo -e "${GREEN}================================${NC}"

# Function to start an agent
start_agent() {
    local agent_name=$1
    local agent_file=$2
    local port=$3
    
    echo -e "${YELLOW}Starting $agent_name (Port: $port)...${NC}"
    python3 "$SCRIPT_DIR/agents/$agent_file/main.py" &
    local pid=$!
    echo -e "${GREEN}✓ $agent_name started (PID: $pid)${NC}"
    echo "$agent_name:$pid" >> "$SCRIPT_DIR/.agents_pids"
}

# Clear previous PID file
> "$SCRIPT_DIR/.agents_pids"

# Start all agents
start_agent "MergedAgent" "merged_agent" 8001
sleep 2

start_agent "ModelAgent" "model_agent" 8003
sleep 2

start_agent "DecisionAgent" "decision_agent" 8004
sleep 2

start_agent "MonitoringAgent" "monitoring_agent" 8005
sleep 2

start_agent "HealingAgent" "healing_agent" 8006
sleep 2

start_agent "AGL_Mock" "agl_mock" 8007
sleep 2

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}All agents started!${NC}"
echo -e "${GREEN}================================${NC}"
echo -e "${YELLOW}Running agents:${NC}"
cat "$SCRIPT_DIR/.agents_pids"
echo ""
echo -e "${YELLOW}To stop all agents, run:${NC}"
echo -e "${GREEN}bash stop_all_agents.sh${NC}"
echo ""
echo -e "${YELLOW}Agent Status:${NC}"
echo -e "${GREEN}http://localhost:3000${NC}"

# Keep the script running
wait

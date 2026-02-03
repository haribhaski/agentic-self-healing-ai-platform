#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${YELLOW}Stopping all agents...${NC}"

if [ -f "$SCRIPT_DIR/.agents_pids" ]; then
    while IFS=':' read -r agent_name pid; do
        if [ ! -z "$pid" ]; then
            echo -e "${RED}Killing $agent_name (PID: $pid)${NC}"
            kill $pid 2>/dev/null || true
            sleep 1
        fi
    done < "$SCRIPT_DIR/.agents_pids"
    rm "$SCRIPT_DIR/.agents_pids"
    echo -e "${GREEN}All agents stopped${NC}"
else
    echo -e "${RED}No agents PID file found${NC}"
    echo -e "${YELLOW}Killing all Python agent processes...${NC}"
    pkill -f "agents/.*main.py" || true
    echo -e "${GREEN}Done${NC}"
fi

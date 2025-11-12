#!/bin/bash

# Local Development Script for OpenTelemetry Demo
# This script helps you run all services locally for testing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  OpenTelemetry Demo - Local Setup  ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""

# Check if connection string is set
if [ -z "$APPLICATIONINSIGHTS_CONNECTION_STRING" ]; then
    echo -e "${YELLOW}Warning: APPLICATIONINSIGHTS_CONNECTION_STRING not set${NC}"
    echo "Telemetry will not be sent to Application Insights"
    echo "To set it, run:"
    echo "export APPLICATIONINSIGHTS_CONNECTION_STRING='your-connection-string'"
    echo ""
fi

# Function to setup Python environment
setup_venv() {
    local dir=$1
    local service=$2
    
    echo -e "${GREEN}Setting up $service...${NC}"
    cd "$dir"
    
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    echo "Activating virtual environment..."
    source venv/bin/activate
    
    echo "Installing dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    
    echo -e "${GREEN}✓ $service setup complete${NC}"
    echo ""
    
    cd - > /dev/null
}

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Working directory: $SCRIPT_DIR"
echo ""

# Setup each service
echo "Setting up services..."
echo ""

setup_venv "$SCRIPT_DIR/inventory-api" "Inventory API"
setup_venv "$SCRIPT_DIR/orders-api" "Orders API"
setup_venv "$SCRIPT_DIR/storefront-frontend" "Storefront Frontend"

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}  Setup Complete!                   ${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "To run the services, open three separate terminals and run:"
echo ""
echo -e "${YELLOW}Terminal 1 - Inventory API:${NC}"
echo "cd $SCRIPT_DIR/inventory-api"
echo "source venv/bin/activate"
echo "uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo -e "${YELLOW}Terminal 2 - Orders API:${NC}"
echo "cd $SCRIPT_DIR/orders-api"
echo "source venv/bin/activate"
echo "export INVENTORY_API_URL='http://localhost:8000'"
echo "uvicorn app:app --host 0.0.0.0 --port 8001 --reload"
echo ""
echo -e "${YELLOW}Terminal 3 - Storefront Frontend:${NC}"
echo "cd $SCRIPT_DIR/storefront-frontend"
echo "source venv/bin/activate"
echo "export ORDERS_API_URL='http://localhost:8001'"
echo "uvicorn app:app --host 0.0.0.0 --port 8080 --reload"
echo ""
echo -e "${GREEN}Then open your browser to: http://localhost:8080${NC}"
echo ""
echo "Alternatively, use the provided tmux script:"
echo "./run-local-tmux.sh"

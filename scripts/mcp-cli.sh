#!/bin/bash

# Helper script for MCP STDIO interface operations

# Configuration
PYTHON=${PYTHON:-"python"}
SERVER_MODULE="src.run_stdio_server"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${BLUE}Info: $1${NC}"
}

success() {
    echo -e "${GREEN}Success: $1${NC}"
}

# Function to send request to STDIO server
send_request() {
    local method=$1
    local path=$2
    local body=$3

    if [ -z "$body" ]; then
        echo "{\"method\": \"$method\", \"path\": \"$path\"}"
    else
        echo "{\"method\": \"$method\", \"path\": \"$path\", \"body\": $body}"
    fi | $PYTHON -m $SERVER_MODULE
}

# Show usage information
usage() {
    cat << EOF
Usage: $0 <command> [args]

Commands:
    health                  Check server health
    auth                   Get authentication token
    create-campaign       Create a new campaign
    get-campaign <id>     Get campaign details
    list-campaigns       List all campaigns
    create-order         Create a new order
    get-report <type>    Get a report (campaign-performance, inventory-usage)
    help                 Show this help message

Examples:
    $0 health
    $0 auth
    $0 create-campaign '{"name": "Test Campaign", "advertiserId": "12345"}'
    $0 get-campaign 67890
    $0 get-report campaign-performance '{"dateRange": "LAST_7_DAYS"}'
EOF
    exit 1
}

# Main command handler
case "$1" in
    health)
        info "Checking server health..."
        send_request "GET" "/health"
        ;;
        
    auth)
        if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
            error "CLIENT_ID and CLIENT_SECRET environment variables must be set"
        fi
        
        info "Authenticating..."
        send_request "POST" "/auth/token" "{\"client_id\": \"$CLIENT_ID\", \"client_secret\": \"$CLIENT_SECRET\"}"
        ;;
        
    create-campaign)
        if [ -z "$2" ]; then
            error "Campaign data required"
        fi
        
        info "Creating campaign..."
        send_request "POST" "/campaigns" "$2"
        ;;
        
    get-campaign)
        if [ -z "$2" ]; then
            error "Campaign ID required"
        fi
        
        info "Getting campaign $2..."
        send_request "GET" "/campaigns/$2"
        ;;
        
    list-campaigns)
        info "Listing campaigns..."
        send_request "GET" "/campaigns"
        ;;
        
    create-order)
        if [ -z "$2" ]; then
            error "Order data required"
        fi
        
        info "Creating order..."
        send_request "POST" "/orders" "$2"
        ;;
        
    get-report)
        if [ -z "$2" ]; then
            error "Report type required"
        fi
        
        local body=${3:-"{}"}
        info "Getting $2 report..."
        send_request "GET" "/reports/$2" "$body"
        ;;
        
    help|--help|-h)
        usage
        ;;
        
    *)
        error "Unknown command: $1"
        usage
        ;;
esac 
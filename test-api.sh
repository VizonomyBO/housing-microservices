#!/bin/bash

# API Testing Script for Microservices Platform
# This script tests all major endpoints of the Account Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base URLs
ACCOUNT_URL="http://localhost:5000"
SWAGGER_URL="http://localhost:3000"

# Test data
TEST_EMAIL="test_$(date +%s)@example.com"
TEST_USERNAME="testuser_$(date +%s)"
TEST_PASSWORD="TestPass123!"
TEST_FIRST_NAME="Test"
TEST_LAST_NAME="User"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Function to test endpoint
test_endpoint() {
    local description=$1
    local method=$2
    local url=$3
    local data=$4
    local expected_status=$5
    
    print_info "Testing: $description"
    
    if [ -z "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" -eq "$expected_status" ]; then
        print_success "$description - Status: $http_code"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        echo ""
        return 0
    else
        print_error "$description - Expected: $expected_status, Got: $http_code"
        echo "$body"
        echo ""
        return 1
    fi
}

echo "=========================================="
echo "  Microservices Platform API Tests"
echo "=========================================="
echo ""

# Test 1: Check Swagger Aggregator Health
print_info "Phase 1: Testing Swagger Aggregator Service"
test_endpoint "Swagger Health Check" "GET" "$SWAGGER_URL/health" "" 200

# Test 2: Check Account Service Health
print_info "Phase 2: Testing Account Service"
test_endpoint "Account Service Health Check" "GET" "$ACCOUNT_URL/health" "" 200

# Test 3: Get System Status
test_endpoint "System Status" "GET" "$SWAGGER_URL/api/status" "" 200

# Test 4: Get Service List
test_endpoint "Service List" "GET" "$SWAGGER_URL/api/services" "" 200

# Test 5: Get OpenAPI Spec
test_endpoint "OpenAPI Specification" "GET" "$ACCOUNT_URL/openapi.json" "" 200

print_info "Phase 3: Testing User Registration"

# Test 6: Register User
REGISTER_DATA=$(cat <<EOF
{
  "email": "$TEST_EMAIL",
  "username": "$TEST_USERNAME",
  "password": "$TEST_PASSWORD",
  "first_name": "$TEST_FIRST_NAME",
  "last_name": "$TEST_LAST_NAME"
}
EOF
)

if test_endpoint "User Registration" "POST" "$ACCOUNT_URL/auth/register" "$REGISTER_DATA" 201; then
    print_info "Phase 4: Testing User Login"
    
    # Test 7: Login
    LOGIN_DATA=$(cat <<EOF
{
  "login": "$TEST_EMAIL",
  "password": "$TEST_PASSWORD"
}
EOF
)
    
    login_response=$(curl -s -X POST "$ACCOUNT_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d "$LOGIN_DATA")
    
    ACCESS_TOKEN=$(echo "$login_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
    REFRESH_TOKEN=$(echo "$login_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])" 2>/dev/null || echo "")
    
    if [ -n "$ACCESS_TOKEN" ] && [ -n "$REFRESH_TOKEN" ]; then
        print_success "User Login - Got tokens"
        echo "$login_response" | python3 -m json.tool
        echo ""
        
        print_info "Phase 5: Testing Token Operations"
        
        # Test 8: Verify Token
        VERIFY_DATA=$(cat <<EOF
{
  "token": "$ACCESS_TOKEN"
}
EOF
)
        test_endpoint "Token Verification" "POST" "$ACCOUNT_URL/auth/verify-token" "$VERIFY_DATA" 200
        
        # Test 9: Refresh Token
        REFRESH_DATA=$(cat <<EOF
{
  "refresh_token": "$REFRESH_TOKEN"
}
EOF
)
        if test_endpoint "Token Refresh" "POST" "$ACCOUNT_URL/auth/refresh" "$REFRESH_DATA" 200; then
            # Get new refresh token for logout test
            refresh_response=$(curl -s -X POST "$ACCOUNT_URL/auth/refresh" \
                -H "Content-Type: application/json" \
                -d "$REFRESH_DATA")
            
            NEW_REFRESH_TOKEN=$(echo "$refresh_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])" 2>/dev/null || echo "")
            
            # Test 10: Logout
            if [ -n "$NEW_REFRESH_TOKEN" ]; then
                LOGOUT_DATA=$(cat <<EOF
{
  "refresh_token": "$NEW_REFRESH_TOKEN"
}
EOF
)
                test_endpoint "User Logout" "POST" "$ACCOUNT_URL/auth/logout" "$LOGOUT_DATA" 200
            fi
        fi
    else
        print_error "Failed to get tokens from login response"
    fi
fi

print_info "Phase 6: Testing Password Reset Flow"

# Test 11: Forgot Password
FORGOT_DATA=$(cat <<EOF
{
  "email": "$TEST_EMAIL"
}
EOF
)
test_endpoint "Forgot Password" "POST" "$ACCOUNT_URL/auth/forgot-password" "$FORGOT_DATA" 200

print_info "Phase 7: Testing Invalid Inputs"

# Test 12: Invalid Registration (duplicate email)
test_endpoint "Duplicate Registration" "POST" "$ACCOUNT_URL/auth/register" "$REGISTER_DATA" 409

# Test 13: Invalid Login
INVALID_LOGIN_DATA=$(cat <<EOF
{
  "login": "$TEST_EMAIL",
  "password": "WrongPassword123!"
}
EOF
)
test_endpoint "Invalid Login" "POST" "$ACCOUNT_URL/auth/login" "$INVALID_LOGIN_DATA" 401

# Test 14: Invalid Token
INVALID_TOKEN_DATA=$(cat <<EOF
{
  "token": "invalid.token.here"
}
EOF
)
test_endpoint "Invalid Token Verification" "POST" "$ACCOUNT_URL/auth/verify-token" "$INVALID_TOKEN_DATA" 401

print_info "Phase 8: Testing Swagger Aggregator Features"

# Test 15: Get Aggregated Specs
test_endpoint "Aggregated OpenAPI Specs" "GET" "$SWAGGER_URL/api/specs" "" 200

# Test 16: Get Specific Service Spec
test_endpoint "Account Service Spec" "GET" "$SWAGGER_URL/api/specs/Account Service" "" 200

# Test 17: Health Metrics
test_endpoint "Health Metrics" "GET" "$SWAGGER_URL/health/metrics" "" 200

# Test 18: Force Refresh
test_endpoint "Force Refresh Services" "POST" "$SWAGGER_URL/api/refresh" "" 200

echo "=========================================="
echo "  Test Summary"
echo "=========================================="
echo ""
print_success "All tests completed!"
echo ""
print_info "Test User Created:"
echo "  Email: $TEST_EMAIL"
echo "  Username: $TEST_USERNAME"
echo "  Password: $TEST_PASSWORD"
echo ""
print_info "Access the API documentation at:"
echo "  http://localhost:3000/docs"
echo ""
print_info "View system status at:"
echo "  http://localhost:3000/api/status"
echo ""


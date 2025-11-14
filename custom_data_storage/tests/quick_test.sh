#!/bin/bash

# Quick Test Script for Custom Data Storage Add-on
# Tests basic functionality with curl commands

set -e

# Configuration
BASE_URL="${1:-http://localhost:8100}"
API_KEY="${2:-}"

echo "🧪 Quick Test for Custom Data Storage Add-on"
echo "🌐 Base URL: $BASE_URL"
echo "🔑 API Key: $([ -n "$API_KEY" ] && echo "Set" || echo "Not set")"
echo "=" * 50

# Setup headers
HEADERS="-H 'Content-Type: application/json'"
if [ -n "$API_KEY" ]; then
    HEADERS="$HEADERS -H 'X-API-Key: $API_KEY'"
fi

# Test 1: Health Check
echo "🏥 Testing health check..."
if curl -s -f "$BASE_URL/health" > /dev/null; then
    echo "✅ Health check passed"
    curl -s "$BASE_URL/health" | python3 -m json.tool
else
    echo "❌ Health check failed"
    exit 1
fi

echo ""

# Test 2: Store test data
echo "💾 Storing test data..."
TEST_DATA='{"key": "test_key", "value": "test_value", "category": "test"}'
if eval "curl -s -f -X POST $HEADERS -d '$TEST_DATA' '$BASE_URL/api/data'" > /dev/null; then
    echo "✅ Data stored successfully"
else
    echo "❌ Failed to store data"
    exit 1
fi

# Test 3: Retrieve test data
echo "📖 Retrieving test data..."
if eval "curl -s -f $HEADERS '$BASE_URL/api/data/test/test_key'" > /dev/null; then
    echo "✅ Data retrieved successfully"
    eval "curl -s $HEADERS '$BASE_URL/api/data/test/test_key'" | python3 -m json.tool
else
    echo "❌ Failed to retrieve data"
    exit 1
fi

echo ""

# Test 4: Store complex data
echo "🔧 Storing complex data..."
COMPLEX_DATA='{"key": "user_prefs", "value": {"theme": "dark", "lang": "en", "notifications": true}, "category": "settings"}'
if eval "curl -s -f -X POST $HEADERS -d '$COMPLEX_DATA' '$BASE_URL/api/data'" > /dev/null; then
    echo "✅ Complex data stored successfully"
else
    echo "❌ Failed to store complex data"
    exit 1
fi

# Test 5: Get category data
echo "📂 Getting category data..."
if eval "curl -s -f $HEADERS '$BASE_URL/api/data/settings'" > /dev/null; then
    echo "✅ Category data retrieved successfully"
    eval "curl -s $HEADERS '$BASE_URL/api/data/settings'" | python3 -m json.tool
else
    echo "❌ Failed to retrieve category data"
    exit 1
fi

echo ""

# Test 6: Get metadata
echo "📊 Getting metadata..."
if eval "curl -s -f $HEADERS '$BASE_URL/api/metadata'" > /dev/null; then
    echo "✅ Metadata retrieved successfully"
    eval "curl -s $HEADERS '$BASE_URL/api/metadata'" | python3 -m json.tool
else
    echo "❌ Failed to retrieve metadata"
    exit 1
fi

echo ""

# Test 7: Delete test data
echo "🗑️ Deleting test data..."
if eval "curl -s -f -X DELETE $HEADERS '$BASE_URL/api/data/test/test_key'" > /dev/null; then
    echo "✅ Data deleted successfully"
else
    echo "❌ Failed to delete data"
    exit 1
fi

echo ""
echo "🎉 All tests passed! Custom Data Storage Add-on is working correctly."
echo ""
echo "📋 Example usage:"
echo "# Store data:"
echo "curl -X POST $BASE_URL/api/data \\"
echo "  -H 'Content-Type: application/json' \\"
if [ -n "$API_KEY" ]; then
    echo "  -H 'X-API-Key: $API_KEY' \\"
fi
echo "  -d '{\"key\": \"my_key\", \"value\": \"my_value\", \"category\": \"my_category\"}'"
echo ""
echo "# Get data:"
echo "curl $BASE_URL/api/data/my_category/my_key"
if [ -n "$API_KEY" ]; then
    echo "  -H 'X-API-Key: $API_KEY'"
fi
echo ""
echo "🌐 WebSocket URL: $BASE_URL (for real-time updates)"
echo "📚 Full API documentation: See README.md"

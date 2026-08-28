#!/usr/bin/env python3
"""
Regression Test Suite for Order Discrepancy Feature
Tests dispatch-before-order detection and resolution actions.
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
ROOT_DIR = Path(__file__).parent / "backend"
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

# Base URL from frontend/.env
frontend_env = Path(__file__).parent / "frontend" / ".env"
BACKEND_URL = None
if frontend_env.exists():
    with open(frontend_env) as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BACKEND_URL = line.split('=', 1)[1].strip()
                break

if not BACKEND_URL:
    print("ERROR: Could not find REACT_APP_BACKEND_URL in frontend/.env")
    sys.exit(1)

BASE_URL = f"{BACKEND_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@factory.com"
ADMIN_PASSWORD = "admin123"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed += 1
        self.tests.append({"name": test_name, "status": "PASS", "details": details})
        print(f"{GREEN}✓ PASS{RESET}: {test_name}")
        if details:
            print(f"  {details}")
    
    def add_fail(self, test_name: str, details: str = ""):
        self.failed += 1
        self.tests.append({"name": test_name, "status": "FAIL", "details": details})
        print(f"{RED}✗ FAIL{RESET}: {test_name}")
        if details:
            print(f"  {details}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Test Summary: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"{RED}Failed tests:{RESET}")
            for test in self.tests:
                if test["status"] == "FAIL":
                    print(f"  - {test['name']}")
        print(f"{'='*60}\n")
        return self.failed == 0


def get_admin_token() -> str:
    """Login as admin and get token (OTP disabled)."""
    print(f"\n{BLUE}Logging in as admin...{RESET}")
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if resp.status_code != 200:
        print(f"{RED}Login failed: {resp.status_code} - {resp.text}{RESET}")
        sys.exit(1)
    
    data = resp.json()
    if "token" not in data:
        print(f"{RED}No token in response (OTP might be enabled): {data}{RESET}")
        sys.exit(1)
    
    print(f"{GREEN}✓ Admin login successful{RESET}")
    return data["token"]


def iso_now() -> str:
    """Return current time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def iso_days_ago(days: int) -> str:
    """Return ISO timestamp for N days ago."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class DiscrepancyTestFixtures:
    """Manages test fixtures for discrepancy testing."""
    
    def __init__(self, mongo_client: MongoClient, db_name: str):
        self.client = mongo_client
        self.db = self.client[db_name]
        self.created_orders = []
        self.created_dispatches = []
        self.customer = None
        self.item = None
    
    def setup(self):
        """Get existing customer and item for test fixtures."""
        print(f"\n{BLUE}Setting up test fixtures...{RESET}")
        
        # Get any existing customer
        self.customer = self.db.customers.find_one({}, {"_id": 0})
        if not self.customer:
            print(f"{RED}No customers found in database{RESET}")
            sys.exit(1)
        
        # Get any existing item
        self.item = self.db.items.find_one({}, {"_id": 0})
        if not self.item:
            print(f"{RED}No items found in database{RESET}")
            sys.exit(1)
        
        print(f"  Using customer: {self.customer['name']} (ID: {self.customer['id']})")
        print(f"  Using item: {self.item['name']} (ID: {self.item['id']})")
    
    def create_fixture_pair(self, slip_no: int, order_days_ago: int = 5, dispatch_days_ago: int = 4) -> Dict[str, str]:
        """
        Create a test order and dispatch pair where dispatch pre-dates order.
        Returns dict with order_id and dispatch_id.
        """
        import uuid
        
        # Create dispatch first (older date)
        dispatch_id = str(uuid.uuid4())
        dispatch = {
            "id": dispatch_id,
            "customer_id": self.customer["id"],
            "customer_name": self.customer["name"],
            "items": [{
                "item_id": self.item["id"],
                "item_name": self.item["name"],
                "product_name": self.item.get("product_name", "Test Product"),
                "variant": "",
                "quantity": 50
            }],
            "order_id": None,
            "order_ids": [],
            "dispatched_at": iso_days_ago(dispatch_days_ago),
            "dispatched_by": "qa_test",
            "slip_no": slip_no,
            "created_at": iso_days_ago(dispatch_days_ago),
            "updated_at": iso_days_ago(dispatch_days_ago)
        }
        self.db.dispatches.insert_one(dispatch)
        self.created_dispatches.append(dispatch_id)
        
        # Create order (newer date, but order_date is older)
        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "customer_id": self.customer["id"],
            "customer_name": self.customer["name"],
            "items": [{
                "item_id": self.item["id"],
                "item_name": self.item["name"],
                "product_name": self.item.get("product_name", "Test Product"),
                "variant": "",
                "quantity": 50
            }],
            "order_date": iso_days_ago(order_days_ago),
            "status": "Pending",
            "created_at": iso_now(),  # Created NOW (after dispatch)
            "created_by": "qa_test",
            "updated_at": iso_now(),
            "discrepancy_dismissed": False
        }
        self.db.orders.insert_one(order)
        self.created_orders.append(order_id)
        
        print(f"  Created fixture pair: order={order_id[:8]}..., dispatch={dispatch_id[:8]}... (slip {slip_no})")
        return {"order_id": order_id, "dispatch_id": dispatch_id}
    
    def cleanup(self):
        """Remove all test fixtures."""
        print(f"\n{BLUE}Cleaning up test fixtures...{RESET}")
        
        # Delete test orders
        if self.created_orders:
            result = self.db.orders.delete_many({"created_by": "qa_test"})
            print(f"  Deleted {result.deleted_count} test orders")
        
        # Delete test dispatches
        if self.created_dispatches:
            result = self.db.dispatches.delete_many({"dispatched_by": "qa_test"})
            print(f"  Deleted {result.deleted_count} test dispatches")
        
        print(f"{GREEN}✓ Cleanup complete{RESET}")


def test_discrepancy_detection(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 1: Verify GET /api/orders attaches discrepancy objects."""
    print(f"\n{BLUE}Test 1: Discrepancy Detection{RESET}")
    
    # Create a test fixture
    pair = fixtures.create_fixture_pair(slip_no=990010)
    
    # Get orders and check for discrepancy
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/orders", headers=headers)
    
    if resp.status_code != 200:
        result.add_fail("Discrepancy Detection", f"GET /orders failed: {resp.status_code}")
        return
    
    orders = resp.json()
    
    # Find our test order
    test_order = None
    for order in orders:
        if order.get("id") == pair["order_id"]:
            test_order = order
            break
    
    if not test_order:
        result.add_fail("Discrepancy Detection", f"Test order {pair['order_id']} not found in response")
        return
    
    # Check for discrepancy object
    if "discrepancy" not in test_order:
        result.add_fail("Discrepancy Detection", "No 'discrepancy' field in order")
        return
    
    discrepancy = test_order["discrepancy"]
    if discrepancy is None:
        result.add_fail("Discrepancy Detection", "Discrepancy is None (should be an object)")
        return
    
    # Validate discrepancy structure
    required_fields = ["dispatch_id", "slip_no", "dispatched_at", "order_date", "entered_at", "items"]
    missing = [f for f in required_fields if f not in discrepancy]
    if missing:
        result.add_fail("Discrepancy Detection", f"Missing fields in discrepancy: {missing}")
        return
    
    # Validate dispatch_id matches
    if discrepancy["dispatch_id"] != pair["dispatch_id"]:
        result.add_fail("Discrepancy Detection", 
                       f"Wrong dispatch_id: expected {pair['dispatch_id']}, got {discrepancy['dispatch_id']}")
        return
    
    # Validate slip_no
    if discrepancy["slip_no"] != 990010:
        result.add_fail("Discrepancy Detection", f"Wrong slip_no: expected 990010, got {discrepancy['slip_no']}")
        return
    
    # Validate items
    if not discrepancy["items"]:
        result.add_fail("Discrepancy Detection", "No items in discrepancy")
        return
    
    item = discrepancy["items"][0]
    if item.get("quantity") != 50:
        result.add_fail("Discrepancy Detection", f"Wrong quantity: expected 50, got {item.get('quantity')}")
        return
    
    result.add_pass("Discrepancy Detection", 
                   f"Discrepancy correctly detected: dispatch {pair['dispatch_id'][:8]}..., slip {discrepancy['slip_no']}, qty 50")


def test_resolve_update_date(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 2: Resolve with update_date action."""
    print(f"\n{BLUE}Test 2: Resolve - Update Date{RESET}")
    
    # Create a test fixture
    pair = fixtures.create_fixture_pair(slip_no=990011)
    
    # Get the dispatch date
    dispatch = fixtures.db.dispatches.find_one({"id": pair["dispatch_id"]}, {"_id": 0})
    dispatch_date = dispatch["dispatched_at"]
    
    # Resolve with update_date
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "update_date", "dispatch_id": pair["dispatch_id"]}
    )
    
    if resp.status_code != 200:
        result.add_fail("Resolve - Update Date", f"API call failed: {resp.status_code} - {resp.text}")
        return
    
    data = resp.json()
    if not data.get("ok"):
        result.add_fail("Resolve - Update Date", f"Response ok=false: {data}")
        return
    
    # Verify order was updated
    order = data.get("order")
    if not order:
        result.add_fail("Resolve - Update Date", "No order in response")
        return
    
    # Check order_date was updated
    if order.get("order_date") != dispatch_date:
        result.add_fail("Resolve - Update Date", 
                       f"order_date not updated: expected {dispatch_date}, got {order.get('order_date')}")
        return
    
    # Check status is still Pending
    if order.get("status") != "Pending":
        result.add_fail("Resolve - Update Date", f"Status changed: expected Pending, got {order.get('status')}")
        return
    
    # Check discrepancy_dismissed
    if not order.get("discrepancy_dismissed"):
        result.add_fail("Resolve - Update Date", "discrepancy_dismissed not set to true")
        return
    
    # Verify discrepancy no longer appears on subsequent GET
    resp = requests.get(f"{BASE_URL}/orders", headers=headers)
    if resp.status_code == 200:
        orders = resp.json()
        test_order = next((o for o in orders if o.get("id") == pair["order_id"]), None)
        if test_order and test_order.get("discrepancy") is not None:
            result.add_fail("Resolve - Update Date", "Discrepancy still appears after dismissal")
            return
    
    result.add_pass("Resolve - Update Date", 
                   f"Order date updated to {dispatch_date}, status=Pending, discrepancy dismissed")


def test_resolve_clear(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 3: Resolve with clear action."""
    print(f"\n{BLUE}Test 3: Resolve - Clear{RESET}")
    
    # Create a test fixture
    pair = fixtures.create_fixture_pair(slip_no=990012)
    
    # Resolve with clear
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "clear", "dispatch_id": pair["dispatch_id"]}
    )
    
    if resp.status_code != 200:
        result.add_fail("Resolve - Clear", f"API call failed: {resp.status_code} - {resp.text}")
        return
    
    data = resp.json()
    if not data.get("ok"):
        result.add_fail("Resolve - Clear", f"Response ok=false: {data}")
        return
    
    # Verify order was updated
    order = data.get("order")
    if not order:
        result.add_fail("Resolve - Clear", "No order in response")
        return
    
    # Check status is Dispatched
    if order.get("status") != "Dispatched":
        result.add_fail("Resolve - Clear", f"Status not updated: expected Dispatched, got {order.get('status')}")
        return
    
    # Check items is empty
    if order.get("items"):
        result.add_fail("Resolve - Clear", f"Items not emptied: {order.get('items')}")
        return
    
    # Check discrepancy_dismissed
    if not order.get("discrepancy_dismissed"):
        result.add_fail("Resolve - Clear", "discrepancy_dismissed not set to true")
        return
    
    # Verify dispatch was updated with order_id
    dispatch = fixtures.db.dispatches.find_one({"id": pair["dispatch_id"]}, {"_id": 0})
    if pair["order_id"] not in dispatch.get("order_ids", []):
        result.add_fail("Resolve - Clear", f"Order ID not added to dispatch.order_ids: {dispatch.get('order_ids')}")
        return
    
    # Verify discrepancy no longer appears
    resp = requests.get(f"{BASE_URL}/orders", headers=headers)
    if resp.status_code == 200:
        orders = resp.json()
        test_order = next((o for o in orders if o.get("id") == pair["order_id"]), None)
        if test_order and test_order.get("discrepancy") is not None:
            result.add_fail("Resolve - Clear", "Discrepancy still appears after dismissal")
            return
    
    result.add_pass("Resolve - Clear", 
                   f"Order status=Dispatched, items=[], dispatch linked, discrepancy dismissed")


def test_resolve_keep(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 4: Resolve with keep action."""
    print(f"\n{BLUE}Test 4: Resolve - Keep{RESET}")
    
    # Create a test fixture
    pair = fixtures.create_fixture_pair(slip_no=990013)
    
    # Resolve with keep
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "keep"}
    )
    
    if resp.status_code != 200:
        result.add_fail("Resolve - Keep", f"API call failed: {resp.status_code} - {resp.text}")
        return
    
    data = resp.json()
    if not data.get("ok"):
        result.add_fail("Resolve - Keep", f"Response ok=false: {data}")
        return
    
    # Verify order was updated
    order = data.get("order")
    if not order:
        result.add_fail("Resolve - Keep", "No order in response")
        return
    
    # Check status is still Pending
    if order.get("status") != "Pending":
        result.add_fail("Resolve - Keep", f"Status changed: expected Pending, got {order.get('status')}")
        return
    
    # Check discrepancy_dismissed
    if not order.get("discrepancy_dismissed"):
        result.add_fail("Resolve - Keep", "discrepancy_dismissed not set to true")
        return
    
    # Verify discrepancy no longer appears
    resp = requests.get(f"{BASE_URL}/orders", headers=headers)
    if resp.status_code == 200:
        orders = resp.json()
        test_order = next((o for o in orders if o.get("id") == pair["order_id"]), None)
        if test_order and test_order.get("discrepancy") is not None:
            result.add_fail("Resolve - Keep", "Discrepancy still appears after dismissal")
            return
    
    result.add_pass("Resolve - Keep", "Status=Pending, discrepancy dismissed")


def test_resolve_delete(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 5: Resolve with delete action."""
    print(f"\n{BLUE}Test 5: Resolve - Delete{RESET}")
    
    # Create a test fixture
    pair = fixtures.create_fixture_pair(slip_no=990014)
    
    # Resolve with delete
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "delete"}
    )
    
    if resp.status_code != 200:
        result.add_fail("Resolve - Delete", f"API call failed: {resp.status_code} - {resp.text}")
        return
    
    data = resp.json()
    if not data.get("ok") or not data.get("deleted"):
        result.add_fail("Resolve - Delete", f"Response not ok/deleted: {data}")
        return
    
    # Verify order no longer exists
    resp = requests.get(f"{BASE_URL}/orders", headers=headers)
    if resp.status_code == 200:
        orders = resp.json()
        test_order = next((o for o in orders if o.get("id") == pair["order_id"]), None)
        if test_order:
            result.add_fail("Resolve - Delete", "Order still exists after delete")
            return
    
    # Remove from cleanup list since it's already deleted
    if pair["order_id"] in fixtures.created_orders:
        fixtures.created_orders.remove(pair["order_id"])
    
    result.add_pass("Resolve - Delete", "Order successfully deleted")


def test_error_cases(token: str, fixtures: DiscrepancyTestFixtures, result: TestResult):
    """Test 6: Error cases (invalid action, unknown order, unknown dispatch)."""
    print(f"\n{BLUE}Test 6: Error Cases{RESET}")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test 6a: Invalid action
    pair = fixtures.create_fixture_pair(slip_no=990015)
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "invalid_action"}
    )
    if resp.status_code != 400:
        result.add_fail("Error - Invalid Action", f"Expected 400, got {resp.status_code}")
    else:
        result.add_pass("Error - Invalid Action", "Returns 400 for invalid action")
    
    # Test 6b: Unknown order ID
    resp = requests.post(
        f"{BASE_URL}/orders/fake-order-id-12345/resolve-discrepancy",
        headers=headers,
        json={"action": "keep"}
    )
    if resp.status_code != 404:
        result.add_fail("Error - Unknown Order", f"Expected 404, got {resp.status_code}")
    else:
        result.add_pass("Error - Unknown Order", "Returns 404 for unknown order")
    
    # Test 6c: Unknown dispatch ID for update_date
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "update_date", "dispatch_id": "fake-dispatch-id-12345"}
    )
    if resp.status_code != 404:
        result.add_fail("Error - Unknown Dispatch", f"Expected 404, got {resp.status_code}")
    else:
        result.add_pass("Error - Unknown Dispatch", "Returns 404 for unknown dispatch")
    
    # Test 6d: Missing dispatch_id for clear action
    resp = requests.post(
        f"{BASE_URL}/orders/{pair['order_id']}/resolve-discrepancy",
        headers=headers,
        json={"action": "clear"}
    )
    if resp.status_code != 404:
        result.add_fail("Error - Missing Dispatch ID", f"Expected 404, got {resp.status_code}")
    else:
        result.add_pass("Error - Missing Dispatch ID", "Returns 404 when dispatch_id missing for clear")


def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Order Discrepancy Feature - Regression Test Suite{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"Base URL: {BASE_URL}")
    print(f"MongoDB: {MONGO_URL}/{DB_NAME}")
    
    # Initialize
    result = TestResult()
    mongo_client = MongoClient(MONGO_URL)
    fixtures = DiscrepancyTestFixtures(mongo_client, DB_NAME)
    
    try:
        # Setup
        token = get_admin_token()
        fixtures.setup()
        
        # Run tests
        test_discrepancy_detection(token, fixtures, result)
        test_resolve_update_date(token, fixtures, result)
        test_resolve_clear(token, fixtures, result)
        test_resolve_keep(token, fixtures, result)
        test_resolve_delete(token, fixtures, result)
        test_error_cases(token, fixtures, result)
        
    finally:
        # Cleanup
        fixtures.cleanup()
        mongo_client.close()
    
    # Summary
    success = result.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

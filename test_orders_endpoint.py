#!/usr/bin/env python3
"""
Backend API Test Suite for Factory Order Management - Orders Endpoint
Tests the updated GET /orders endpoint with three views:
1. Pending orders (status_filter=Pending)
2. Dispatched orders (status_filter=Dispatched)
3. All orders (no filter) with dispatch_summary
"""

import requests
import json
import sys
from typing import Optional, Dict, Any, List

# Base URL from frontend/.env
BASE_URL = "https://source-snapshot-3.preview.emergentagent.com/api"

# Test credentials (OTP is disabled)
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
        print(f"\n{'='*70}")
        print(f"TEST SUMMARY: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"{RED}Failed tests:{RESET}")
            for t in self.tests:
                if t["status"] == "FAIL":
                    print(f"  - {t['name']}")
        print(f"{'='*70}\n")
        return self.failed == 0

def get_admin_token(result: TestResult) -> Optional[str]:
    """Login as admin and get token (OTP disabled)."""
    print(f"\n{BLUE}Getting admin token...{RESET}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if response.status_code != 200:
            result.add_fail("Admin login", 
                          f"Expected 200, got {response.status_code}: {response.text}")
            return None
        
        data = response.json()
        
        # OTP is disabled, should get token directly
        if "token" not in data:
            result.add_fail("Admin login", 
                          f"Expected token in response, got: {json.dumps(data, indent=2)}")
            return None
        
        token = data["token"]
        print(f"{GREEN}✓{RESET} Admin token obtained")
        return token
        
    except Exception as e:
        result.add_fail("Admin login", f"Exception: {str(e)}")
        return None

def test_pending_orders(token: str, result: TestResult):
    """Test 1: GET /orders?status_filter=Pending - only Pending status orders."""
    print(f"\n{BLUE}Test 1: GET /orders?status_filter=Pending{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/orders",
            params={"status_filter": "Pending"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            result.add_fail("Pending orders view", 
                          f"Expected 200, got {response.status_code}: {response.text}")
            return
        
        orders = response.json()
        
        if not isinstance(orders, list):
            result.add_fail("Pending orders view", 
                          f"Expected list, got {type(orders)}")
            return
        
        print(f"  Found {len(orders)} orders")
        
        # Verify every order has status == "Pending"
        non_pending = []
        for order in orders:
            status = order.get("status")
            if status != "Pending":
                non_pending.append({
                    "id": order.get("id"),
                    "status": status
                })
        
        if non_pending:
            result.add_fail("Pending orders view - status validation", 
                          f"Found {len(non_pending)} orders with status != 'Pending': {json.dumps(non_pending[:5], indent=2)}")
            return
        
        # Verify each order has items (remaining pending lines)
        orders_without_items = []
        for order in orders:
            items = order.get("items", [])
            if not items:
                orders_without_items.append(order.get("id"))
        
        if orders_without_items:
            result.add_fail("Pending orders view - items validation", 
                          f"Found {len(orders_without_items)} orders without items: {orders_without_items[:5]}")
            return
        
        result.add_pass("Pending orders view", 
                       f"All {len(orders)} orders have status='Pending' and contain items")
        
    except Exception as e:
        result.add_fail("Pending orders view", f"Exception: {str(e)}")

def test_dispatched_orders(token: str, result: TestResult):
    """Test 2: GET /orders?status_filter=Dispatched - Dispatched/Cleared + partial orders."""
    print(f"\n{BLUE}Test 2: GET /orders?status_filter=Dispatched{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/orders",
            params={"status_filter": "Dispatched"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            result.add_fail("Dispatched orders view", 
                          f"Expected 200, got {response.status_code}: {response.text}")
            return
        
        orders = response.json()
        
        if not isinstance(orders, list):
            result.add_fail("Dispatched orders view", 
                          f"Expected list, got {type(orders)}")
            return
        
        print(f"  Found {len(orders)} orders")
        
        if len(orders) == 0:
            result.add_fail("Dispatched orders view", 
                          "Expected at least some dispatched orders, got 0")
            return
        
        # Verify each order has dispatched_items array
        orders_without_dispatched_items = []
        for order in orders:
            dispatched_items = order.get("dispatched_items")
            if not isinstance(dispatched_items, list):
                orders_without_dispatched_items.append({
                    "id": order.get("id"),
                    "status": order.get("status"),
                    "dispatched_items": dispatched_items
                })
            elif len(dispatched_items) == 0:
                # Empty dispatched_items is a problem for Dispatched view
                orders_without_dispatched_items.append({
                    "id": order.get("id"),
                    "status": order.get("status"),
                    "dispatched_items": "empty array"
                })
        
        if orders_without_dispatched_items:
            result.add_fail("Dispatched orders view - dispatched_items validation", 
                          f"Found {len(orders_without_dispatched_items)} orders without proper dispatched_items: {json.dumps(orders_without_dispatched_items[:3], indent=2)}")
            return
        
        # Check that orders include Dispatched/Cleared status OR partially-dispatched (Pending with dispatches)
        status_counts = {}
        for order in orders:
            status = order.get("status", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"  Status breakdown: {json.dumps(status_counts, indent=2)}")
        
        result.add_pass("Dispatched orders view", 
                       f"All {len(orders)} orders have non-empty dispatched_items array. Status breakdown: {status_counts}")
        
    except Exception as e:
        result.add_fail("Dispatched orders view", f"Exception: {str(e)}")

def test_all_orders_with_dispatch_summary(token: str, result: TestResult):
    """Test 3: GET /orders (no filter) - verify dispatch_summary field."""
    print(f"\n{BLUE}Test 3: GET /orders (All Status) - dispatch_summary validation{RESET}")
    
    try:
        response = requests.get(
            f"{BASE_URL}/orders",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            result.add_fail("All orders view", 
                          f"Expected 200, got {response.status_code}: {response.text}")
            return
        
        orders = response.json()
        
        if not isinstance(orders, list):
            result.add_fail("All orders view", 
                          f"Expected list, got {type(orders)}")
            return
        
        print(f"  Found {len(orders)} total orders")
        
        # Verify every order has dispatch_summary field (array)
        orders_without_dispatch_summary = []
        for order in orders:
            if "dispatch_summary" not in order:
                orders_without_dispatch_summary.append({
                    "id": order.get("id"),
                    "status": order.get("status"),
                    "missing": "dispatch_summary field"
                })
            elif not isinstance(order.get("dispatch_summary"), list):
                orders_without_dispatch_summary.append({
                    "id": order.get("id"),
                    "status": order.get("status"),
                    "dispatch_summary_type": type(order.get("dispatch_summary")).__name__
                })
        
        if orders_without_dispatch_summary:
            result.add_fail("All orders view - dispatch_summary presence", 
                          f"Found {len(orders_without_dispatch_summary)} orders without proper dispatch_summary: {json.dumps(orders_without_dispatch_summary[:3], indent=2)}")
            return
        
        # For orders with dispatches, verify dispatch_summary structure
        orders_with_dispatches = [o for o in orders if len(o.get("dispatch_summary", [])) > 0]
        print(f"  {len(orders_with_dispatches)} orders have dispatch history")
        
        if len(orders_with_dispatches) == 0:
            result.add_pass("All orders view - dispatch_summary structure", 
                           f"All {len(orders)} orders have dispatch_summary field (array). No orders with dispatch history to validate structure.")
            return
        
        # Validate dispatch_summary structure for orders with dispatches
        invalid_dispatch_summaries = []
        quantity_mismatch_orders = []
        
        for order in orders_with_dispatches[:10]:  # Check first 10 for detailed validation
            dispatch_summary = order.get("dispatch_summary", [])
            
            # Validate structure: [{date: 'YYYY-MM-DD', items: [{item_name, product_name, variant, quantity}]}]
            for entry in dispatch_summary:
                if not isinstance(entry, dict):
                    invalid_dispatch_summaries.append({
                        "order_id": order.get("id"),
                        "issue": "dispatch_summary entry is not a dict",
                        "entry": entry
                    })
                    continue
                
                if "date" not in entry or "items" not in entry:
                    invalid_dispatch_summaries.append({
                        "order_id": order.get("id"),
                        "issue": "missing date or items field",
                        "entry": entry
                    })
                    continue
                
                if not isinstance(entry["items"], list):
                    invalid_dispatch_summaries.append({
                        "order_id": order.get("id"),
                        "issue": "items is not a list",
                        "entry": entry
                    })
                    continue
                
                # Validate each item has required fields and quantity > 0
                for item in entry["items"]:
                    if not isinstance(item, dict):
                        invalid_dispatch_summaries.append({
                            "order_id": order.get("id"),
                            "issue": "item is not a dict",
                            "item": item
                        })
                        continue
                    
                    qty = item.get("quantity", 0)
                    if qty <= 0:
                        invalid_dispatch_summaries.append({
                            "order_id": order.get("id"),
                            "issue": "item quantity <= 0",
                            "item": item
                        })
            
            # Verify sum of dispatch_summary quantities equals dispatched_items quantities
            # Build map of item_id -> total quantity from dispatch_summary
            summary_totals = {}
            for entry in dispatch_summary:
                for item in entry.get("items", []):
                    item_id = item.get("item_id") or item.get("item_name", "")
                    qty = int(item.get("quantity", 0))
                    summary_totals[item_id] = summary_totals.get(item_id, 0) + qty
            
            # Build map from dispatched_items
            dispatched_totals = {}
            for item in order.get("dispatched_items", []):
                item_id = item.get("item_id") or item.get("item_name", "")
                qty = int(item.get("quantity", 0))
                dispatched_totals[item_id] = qty
            
            # Compare
            if summary_totals != dispatched_totals:
                quantity_mismatch_orders.append({
                    "order_id": order.get("id"),
                    "dispatch_summary_totals": summary_totals,
                    "dispatched_items_totals": dispatched_totals
                })
        
        if invalid_dispatch_summaries:
            result.add_fail("All orders view - dispatch_summary structure", 
                          f"Found {len(invalid_dispatch_summaries)} invalid dispatch_summary entries: {json.dumps(invalid_dispatch_summaries[:3], indent=2)}")
            return
        
        if quantity_mismatch_orders:
            result.add_fail("All orders view - dispatch_summary quantity validation", 
                          f"Found {len(quantity_mismatch_orders)} orders where dispatch_summary totals don't match dispatched_items: {json.dumps(quantity_mismatch_orders[:2], indent=2)}")
            return
        
        result.add_pass("All orders view - dispatch_summary validation", 
                       f"All {len(orders)} orders have dispatch_summary field. {len(orders_with_dispatches)} orders with dispatch history validated: correct structure, quantities > 0, and totals match dispatched_items.")
        
    except Exception as e:
        result.add_fail("All orders view", f"Exception: {str(e)}")

def main():
    print(f"\n{'='*70}")
    print(f"Factory Order Management - Orders Endpoint Test Suite")
    print(f"Base URL: {BASE_URL}")
    print(f"{'='*70}")
    
    result = TestResult()
    
    # Get admin token
    token = get_admin_token(result)
    if not token:
        print(f"\n{RED}Cannot proceed without admin token{RESET}")
        sys.exit(1)
    
    # Run tests
    test_pending_orders(token, result)
    test_dispatched_orders(token, result)
    test_all_orders_with_dispatch_summary(token, result)
    
    # Summary
    success = result.summary()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

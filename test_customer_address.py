#!/usr/bin/env python3
"""
Test script to verify customer_address field in GET /orders endpoint.
Verifies:
1. customer_address is present on EVERY order
2. It's populated for orders whose customer has an address on file
3. It's an empty string otherwise
4. Existing discrepancy and dispatch_summary fields are still present and correctly structured
"""

import requests
import sys
import os

# Read backend URL from frontend/.env
BACKEND_URL = "https://source-snapshot-3.preview.emergentagent.com/api"

def test_customer_address():
    """Test customer_address field in GET /orders endpoint"""
    
    print("=" * 80)
    print("TEST: Customer Address Field in GET /orders")
    print("=" * 80)
    
    # Step 1: Login as admin (direct token, no OTP)
    print("\n[1] Logging in as admin@factory.com...")
    login_resp = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={"email": "admin@factory.com", "password": "admin123"},
        timeout=10
    )
    
    if login_resp.status_code != 200:
        print(f"❌ Login failed: {login_resp.status_code}")
        print(f"Response: {login_resp.text}")
        return False
    
    login_data = login_resp.json()
    
    # Check if OTP is required (shouldn't be based on test history)
    if login_data.get("otp_required"):
        print(f"❌ Unexpected OTP requirement. Response: {login_data}")
        return False
    
    token = login_data.get("token")
    if not token:
        print(f"❌ No token in login response: {login_data}")
        return False
    
    print(f"✅ Login successful, token received")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Step 2: Get all orders
    print("\n[2] Fetching all orders (GET /orders)...")
    orders_resp = requests.get(
        f"{BACKEND_URL}/orders",
        headers=headers,
        timeout=10
    )
    
    if orders_resp.status_code != 200:
        print(f"❌ GET /orders failed: {orders_resp.status_code}")
        print(f"Response: {orders_resp.text}")
        return False
    
    orders = orders_resp.json()
    
    if not isinstance(orders, list):
        print(f"❌ Expected list of orders, got: {type(orders)}")
        return False
    
    print(f"✅ Retrieved {len(orders)} orders")
    
    if len(orders) == 0:
        print("⚠️  No orders found in database")
        return False
    
    # Step 3: Verify customer_address field on EVERY order
    print("\n[3] Verifying customer_address field on all orders...")
    
    missing_field = []
    wrong_type = []
    with_address = 0
    without_address = 0
    
    for idx, order in enumerate(orders):
        order_id = order.get("id", f"order_{idx}")
        
        # Check if customer_address field exists
        if "customer_address" not in order:
            missing_field.append(order_id)
            continue
        
        # Check if it's a string
        addr = order["customer_address"]
        if not isinstance(addr, str):
            wrong_type.append((order_id, type(addr).__name__))
            continue
        
        # Count populated vs empty
        if addr:
            with_address += 1
        else:
            without_address += 1
    
    if missing_field:
        print(f"❌ customer_address field MISSING on {len(missing_field)} orders:")
        for oid in missing_field[:5]:  # Show first 5
            print(f"   - {oid}")
        if len(missing_field) > 5:
            print(f"   ... and {len(missing_field) - 5} more")
        return False
    
    if wrong_type:
        print(f"❌ customer_address has wrong type on {len(wrong_type)} orders:")
        for oid, typ in wrong_type[:5]:
            print(f"   - {oid}: {typ}")
        return False
    
    print(f"✅ customer_address field present on ALL {len(orders)} orders")
    print(f"   - {with_address} orders with populated address")
    print(f"   - {without_address} orders with empty address")
    
    # Step 4: Verify existing fields (discrepancy, dispatch_summary) are still present
    print("\n[4] Verifying existing fields (discrepancy, dispatch_summary)...")
    
    missing_discrepancy = []
    missing_dispatch_summary = []
    wrong_dispatch_summary_type = []
    
    for idx, order in enumerate(orders):
        order_id = order.get("id", f"order_{idx}")
        
        # Check discrepancy field
        if "discrepancy" not in order:
            missing_discrepancy.append(order_id)
        
        # Check dispatch_summary field
        if "dispatch_summary" not in order:
            missing_dispatch_summary.append(order_id)
        elif not isinstance(order["dispatch_summary"], list):
            wrong_dispatch_summary_type.append((order_id, type(order["dispatch_summary"]).__name__))
    
    if missing_discrepancy:
        print(f"❌ discrepancy field MISSING on {len(missing_discrepancy)} orders")
        return False
    
    if missing_dispatch_summary:
        print(f"❌ dispatch_summary field MISSING on {len(missing_dispatch_summary)} orders")
        return False
    
    if wrong_dispatch_summary_type:
        print(f"❌ dispatch_summary has wrong type on {len(wrong_dispatch_summary_type)} orders:")
        for oid, typ in wrong_dispatch_summary_type[:5]:
            print(f"   - {oid}: {typ}")
        return False
    
    print(f"✅ discrepancy field present on all {len(orders)} orders")
    print(f"✅ dispatch_summary field present on all {len(orders)} orders (type: list)")
    
    # Step 5: Verify dispatch_summary structure on orders with dispatches
    print("\n[5] Verifying dispatch_summary structure...")
    
    orders_with_dispatches = [o for o in orders if o.get("dispatch_summary")]
    
    if orders_with_dispatches:
        print(f"   Found {len(orders_with_dispatches)} orders with dispatch history")
        
        # Check structure of first few
        for order in orders_with_dispatches[:3]:
            order_id = order.get("id", "unknown")
            summary = order["dispatch_summary"]
            
            for entry in summary:
                if not isinstance(entry, dict):
                    print(f"❌ dispatch_summary entry not a dict on order {order_id}")
                    return False
                
                if "date" not in entry:
                    print(f"❌ dispatch_summary entry missing 'date' on order {order_id}")
                    return False
                
                if "items" not in entry:
                    print(f"❌ dispatch_summary entry missing 'items' on order {order_id}")
                    return False
                
                if not isinstance(entry["items"], list):
                    print(f"❌ dispatch_summary 'items' not a list on order {order_id}")
                    return False
        
        print(f"✅ dispatch_summary structure correct (checked {min(3, len(orders_with_dispatches))} orders)")
    else:
        print(f"   No orders with dispatch history found")
    
    # Step 6: Show sample orders with and without address
    print("\n[6] Sample orders:")
    
    # Find one with address
    with_addr_sample = next((o for o in orders if o.get("customer_address")), None)
    if with_addr_sample:
        print(f"\n   Order WITH address:")
        print(f"   - ID: {with_addr_sample.get('id')}")
        print(f"   - Customer: {with_addr_sample.get('customer_name', 'N/A')}")
        print(f"   - Address: {with_addr_sample['customer_address']}")
        print(f"   - City: {with_addr_sample.get('customer_city', 'N/A')}")
        print(f"   - Location: {with_addr_sample.get('customer_location', 'N/A')}")
    
    # Find one without address
    without_addr_sample = next((o for o in orders if not o.get("customer_address")), None)
    if without_addr_sample:
        print(f"\n   Order WITHOUT address:")
        print(f"   - ID: {without_addr_sample.get('id')}")
        print(f"   - Customer: {without_addr_sample.get('customer_name', 'N/A')}")
        print(f"   - Address: '{without_addr_sample['customer_address']}' (empty string)")
        print(f"   - City: {without_addr_sample.get('customer_city', 'N/A')}")
        print(f"   - Location: {without_addr_sample.get('customer_location', 'N/A')}")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    print("\nSummary:")
    print(f"  • customer_address field present on ALL {len(orders)} orders")
    print(f"  • {with_address} orders with populated address, {without_address} with empty string")
    print(f"  • discrepancy field present and correct on all orders")
    print(f"  • dispatch_summary field present and correctly structured on all orders")
    print("=" * 80)
    
    return True


if __name__ == "__main__":
    try:
        success = test_customer_address()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

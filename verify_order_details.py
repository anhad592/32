#!/usr/bin/env python3
"""Quick verification script to inspect order details."""

import requests
import json

BASE_URL = "https://source-snapshot-3.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@factory.com"
ADMIN_PASSWORD = "admin123"

# Get token
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    timeout=10
)
token = response.json()["token"]

# Get all orders
response = requests.get(
    f"{BASE_URL}/orders",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10
)
orders = response.json()

# Find an order with dispatch_summary
order_with_dispatch = None
for order in orders:
    if len(order.get("dispatch_summary", [])) > 0:
        order_with_dispatch = order
        break

if order_with_dispatch:
    print("Sample order with dispatch_summary:")
    print(json.dumps({
        "id": order_with_dispatch.get("id"),
        "status": order_with_dispatch.get("status"),
        "customer_name": order_with_dispatch.get("customer_name"),
        "items": order_with_dispatch.get("items", [])[:2],  # First 2 items
        "dispatched_items": order_with_dispatch.get("dispatched_items", [])[:2],
        "dispatch_summary": order_with_dispatch.get("dispatch_summary", [])[:2]
    }, indent=2))
else:
    print("No orders with dispatch_summary found")

# Get pending orders
response = requests.get(
    f"{BASE_URL}/orders",
    params={"status_filter": "Pending"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=10
)
pending_orders = response.json()

print(f"\n\nPending orders count: {len(pending_orders)}")
if pending_orders:
    print("Sample pending order:")
    print(json.dumps({
        "id": pending_orders[0].get("id"),
        "status": pending_orders[0].get("status"),
        "customer_name": pending_orders[0].get("customer_name"),
        "items_count": len(pending_orders[0].get("items", [])),
        "dispatched_items_count": len(pending_orders[0].get("dispatched_items", [])),
        "dispatch_summary_count": len(pending_orders[0].get("dispatch_summary", []))
    }, indent=2))

# Get dispatched orders
response = requests.get(
    f"{BASE_URL}/orders",
    params={"status_filter": "Dispatched"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=10
)
dispatched_orders = response.json()

print(f"\n\nDispatched orders count: {len(dispatched_orders)}")
if dispatched_orders:
    print("Sample dispatched order:")
    sample = dispatched_orders[0]
    print(json.dumps({
        "id": sample.get("id"),
        "status": sample.get("status"),
        "customer_name": sample.get("customer_name"),
        "items_count": len(sample.get("items", [])),
        "dispatched_items_count": len(sample.get("dispatched_items", [])),
        "dispatch_summary_count": len(sample.get("dispatch_summary", []))
    }, indent=2))

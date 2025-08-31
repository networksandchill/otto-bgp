#!/usr/bin/env python3
"""Test script to debug device API endpoints"""
import requests
import json

# Configuration - update these for your environment
BASE_URL = "https://localhost:8443"  # or http://localhost:8000 for dev
USERNAME = "admin"
PASSWORD = "your_password_here"

# Disable SSL warnings for self-signed cert
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_device_endpoints():
    session = requests.Session()
    session.verify = False  # For self-signed certs
    
    # Login first
    print("1. Logging in...")
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD}
    )
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.status_code} - {login_resp.text}")
        return
    
    token = login_resp.json().get("access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("✓ Login successful")
    
    # Test GET /api/devices
    print("\n2. Testing GET /api/devices...")
    get_resp = session.get(f"{BASE_URL}/api/devices")
    print(f"   Status: {get_resp.status_code}")
    if get_resp.status_code == 200:
        print(f"   Response: {get_resp.json()}")
    else:
        print(f"   Error: {get_resp.text}")
    
    # Test POST /api/devices
    print("\n3. Testing POST /api/devices...")
    test_device = {
        "address": "10.10.10.10",
        "hostname": "test-router-01",
        "username": "admin",
        "role": "edge",
        "region": "us-test"
    }
    
    post_resp = session.post(
        f"{BASE_URL}/api/devices",
        json=test_device
    )
    print(f"   Status: {post_resp.status_code}")
    print(f"   Response: {post_resp.text}")
    
    # Check headers
    print("\n4. Checking route with OPTIONS...")
    options_resp = session.options(f"{BASE_URL}/api/devices")
    print(f"   Status: {options_resp.status_code}")
    print(f"   Allow header: {options_resp.headers.get('Allow', 'Not present')}")

if __name__ == "__main__":
    print("Device API Endpoint Test")
    print("=" * 50)
    print(f"Testing against: {BASE_URL}")
    print("=" * 50)
    test_device_endpoints()
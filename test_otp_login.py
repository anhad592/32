#!/usr/bin/env python3
"""
Test script for OTP login feature restoration
Tests the full optional-OTP flow on seeded users
"""

import requests
import json
import re
import subprocess
from typing import Optional, Dict, Any

# Base URL from frontend/.env
BASE_URL = "https://source-snapshot-3.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@factory.com"
ADMIN_PASSWORD = "admin123"
USER_EMAIL = "user@factory.com"
USER_PASSWORD = "user123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log_step(step_num: int, description: str):
    print(f"\n{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}STEP {step_num}: {description}{Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}")

def log_success(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def log_error(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def log_info(message: str):
    print(f"{Colors.YELLOW}ℹ️  {message}{Colors.END}")

def read_otp_from_logs(challenge_id: str, email: str) -> Optional[str]:
    """Read OTP code from backend logs"""
    log_info(f"Reading OTP from backend logs for challenge_id={challenge_id}")
    
    # Pattern: "Admin OTP for user@factory.com (challenge <challenge_id>): <6-digit-code>"
    pattern = rf"Admin OTP for {re.escape(email)} \(challenge {re.escape(challenge_id)}\): (\d{{6}})"
    
    # Try both log files
    log_files = [
        "/var/log/supervisor/backend.out.log",
        "/var/log/supervisor/backend.err.log"
    ]
    
    for log_file in log_files:
        try:
            result = subprocess.run(
                ["tail", "-n", "200", log_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                matches = re.findall(pattern, result.stdout)
                if matches:
                    otp_code = matches[-1]  # Get the most recent match
                    log_info(f"Found OTP code in {log_file}: {otp_code}")
                    return otp_code
        except Exception as e:
            log_error(f"Error reading {log_file}: {e}")
    
    return None

def test_admin_login() -> Optional[str]:
    """Step 0: Login as admin to get admin token"""
    log_step(0, "Admin Login (otp_login=false, expect direct token)")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Admin should have otp_login=false, so expect direct token
            if "token" in data and "otp_required" not in data:
                log_success("Admin login successful - received direct token (otp_login=false)")
                return data["token"]
            elif data.get("otp_required"):
                log_error("Admin has otp_login=true, expected false for this test")
                return None
            else:
                log_error("Unexpected response format")
                return None
        else:
            log_error(f"Admin login failed with status {response.status_code}")
            return None
            
    except Exception as e:
        log_error(f"Exception during admin login: {e}")
        return None

def test_get_users(admin_token: str) -> Optional[str]:
    """Step 1: GET /api/users to find user@factory.com"""
    log_step(1, "GET /api/users - Find user@factory.com")
    
    try:
        response = requests.get(
            f"{BASE_URL}/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            users = response.json()
            log_info(f"Found {len(users)} users")
            
            # Find user@factory.com
            target_user = None
            for user in users:
                if user.get("email") == USER_EMAIL:
                    target_user = user
                    break
            
            if target_user:
                user_id = target_user.get("id")
                log_success(f"Found user@factory.com with id={user_id}")
                log_info(f"User details: {json.dumps(target_user, indent=2)}")
                return user_id
            else:
                log_error(f"User {USER_EMAIL} not found in users list")
                return None
        else:
            log_error(f"GET /users failed with status {response.status_code}")
            log_info(f"Response: {response.text}")
            return None
            
    except Exception as e:
        log_error(f"Exception during GET /users: {e}")
        return None

def test_enable_otp(admin_token: str, user_id: str) -> bool:
    """Step 2: PATCH /api/users/{id}/otp to enable OTP"""
    log_step(2, f"PATCH /api/users/{user_id}/otp - Enable OTP for user@factory.com")
    
    try:
        response = requests.patch(
            f"{BASE_URL}/users/{user_id}/otp",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"otp_login": True},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("otp_login") == True:
                log_success("OTP enabled successfully for user@factory.com")
                return True
            else:
                log_error("OTP not enabled in response")
                return False
        else:
            log_error(f"PATCH /users/{user_id}/otp failed with status {response.status_code}")
            return False
            
    except Exception as e:
        log_error(f"Exception during PATCH /users/{user_id}/otp: {e}")
        return False

def test_user_login_with_otp() -> Optional[Dict[str, Any]]:
    """Step 3: POST /api/auth/login for user@factory.com - expect OTP challenge"""
    log_step(3, "POST /api/auth/login for user@factory.com - Expect OTP challenge")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for OTP challenge response
            required_fields = ["otp_required", "challenge_id", "sent_to", "email_sent"]
            missing_fields = [f for f in required_fields if f not in data]
            
            if missing_fields:
                log_error(f"Missing required fields: {missing_fields}")
                return None
            
            if data.get("otp_required") != True:
                log_error("otp_required is not True")
                return None
            
            if "token" in data:
                log_error("Token should NOT be present in OTP challenge response")
                return None
            
            log_success("OTP challenge response correct:")
            log_info(f"  - otp_required: {data['otp_required']}")
            log_info(f"  - challenge_id: {data['challenge_id']}")
            log_info(f"  - sent_to: {data['sent_to']}")
            log_info(f"  - email_sent: {data['email_sent']}")
            log_info(f"  - token field absent: ✓")
            
            return data
        else:
            log_error(f"Login failed with status {response.status_code}")
            log_info(f"Response: {response.text}")
            return None
            
    except Exception as e:
        log_error(f"Exception during user login: {e}")
        return None

def test_verify_otp(challenge_id: str, otp_code: str) -> Optional[str]:
    """Step 5: POST /api/auth/verify-otp with correct code"""
    log_step(5, "POST /api/auth/verify-otp - Verify OTP code")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/verify-otp",
            json={"challenge_id": challenge_id, "code": otp_code},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            
            if "token" not in data:
                log_error("Token not present in response")
                return None
            
            if "user" not in data:
                log_error("User object not present in response")
                return None
            
            user = data["user"]
            if user.get("role") != "user":
                log_error(f"Expected role='user', got role='{user.get('role')}'")
                return None
            
            log_success("OTP verification successful:")
            log_info(f"  - Token received: {data['token'][:20]}...")
            log_info(f"  - User role: {user.get('role')}")
            log_info(f"  - User email: {user.get('email')}")
            
            return data["token"]
        else:
            log_error(f"OTP verification failed with status {response.status_code}")
            log_info(f"Response: {response.text}")
            return None
            
    except Exception as e:
        log_error(f"Exception during OTP verification: {e}")
        return None

def test_wrong_otp(challenge_id: str) -> bool:
    """Step 6: POST /api/auth/verify-otp with wrong code"""
    log_step(6, "POST /api/auth/verify-otp - Test wrong OTP code (negative test)")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/verify-otp",
            json={"challenge_id": challenge_id, "code": "000000"},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {response.text}")
        
        if response.status_code == 401:
            data = response.json()
            
            if "token" in data:
                log_error("Token should NOT be present when OTP is wrong")
                return False
            
            log_success("Wrong OTP correctly rejected with 401 status")
            return True
        else:
            log_error(f"Expected 401 status, got {response.status_code}")
            return False
            
    except Exception as e:
        log_error(f"Exception during wrong OTP test: {e}")
        return False

def test_disable_otp(admin_token: str, user_id: str) -> bool:
    """Step 7a: PATCH /api/users/{id}/otp to disable OTP"""
    log_step(7, "PATCH /api/users/{user_id}/otp - Disable OTP (cleanup)")
    
    try:
        response = requests.patch(
            f"{BASE_URL}/users/{user_id}/otp",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"otp_login": False},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("otp_login") == False:
                log_success("OTP disabled successfully for user@factory.com")
                return True
            else:
                log_error("OTP not disabled in response")
                return False
        else:
            log_error(f"PATCH /users/{user_id}/otp failed with status {response.status_code}")
            return False
            
    except Exception as e:
        log_error(f"Exception during PATCH /users/{user_id}/otp: {e}")
        return False

def test_user_direct_login() -> bool:
    """Step 7b: POST /api/auth/login for user@factory.com - expect direct token"""
    log_step("7b", "POST /api/auth/login for user@factory.com - Verify direct token login")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD},
            timeout=10
        )
        
        log_info(f"Status: {response.status_code}")
        log_info(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            data = response.json()
            
            if "token" not in data:
                log_error("Token not present in response")
                return False
            
            if "otp_required" in data:
                log_error("otp_required should NOT be present when OTP is disabled")
                return False
            
            log_success("Direct token login successful (OTP disabled):")
            log_info(f"  - Token received: {data['token'][:20]}...")
            log_info(f"  - No otp_required field: ✓")
            
            return True
        else:
            log_error(f"Login failed with status {response.status_code}")
            log_info(f"Response: {response.text}")
            return False
            
    except Exception as e:
        log_error(f"Exception during direct login: {e}")
        return False

def main():
    print(f"\n{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}OTP LOGIN FEATURE RESTORATION TEST{Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print(f"Test User: {USER_EMAIL}")
    
    results = {
        "admin_login": False,
        "get_users": False,
        "enable_otp": False,
        "user_login_otp": False,
        "read_otp_logs": False,
        "verify_otp": False,
        "wrong_otp": False,
        "disable_otp": False,
        "direct_login": False
    }
    
    # Step 0: Admin login
    admin_token = test_admin_login()
    if not admin_token:
        log_error("Cannot proceed without admin token")
        print_summary(results)
        return
    results["admin_login"] = True
    
    # Step 1: Get users
    user_id = test_get_users(admin_token)
    if not user_id:
        log_error("Cannot proceed without user ID")
        print_summary(results)
        return
    results["get_users"] = True
    
    # Step 2: Enable OTP
    if not test_enable_otp(admin_token, user_id):
        log_error("Cannot proceed - OTP enable failed")
        print_summary(results)
        return
    results["enable_otp"] = True
    
    # Step 3: User login with OTP
    otp_challenge = test_user_login_with_otp()
    if not otp_challenge:
        log_error("Cannot proceed - OTP challenge failed")
        print_summary(results)
        return
    results["user_login_otp"] = True
    
    challenge_id = otp_challenge["challenge_id"]
    
    # Step 4: Read OTP from logs
    log_step(4, "Read OTP code from backend logs")
    otp_code = read_otp_from_logs(challenge_id, USER_EMAIL)
    if not otp_code:
        log_error("Cannot proceed - OTP code not found in logs")
        print_summary(results)
        return
    log_success(f"OTP code found: {otp_code}")
    results["read_otp_logs"] = True
    
    # Step 5: Verify OTP
    user_token = test_verify_otp(challenge_id, otp_code)
    if not user_token:
        log_error("OTP verification failed")
        print_summary(results)
        return
    results["verify_otp"] = True
    
    # Step 6: Test wrong OTP (need new challenge)
    log_info("Creating new login challenge for wrong OTP test...")
    otp_challenge2 = test_user_login_with_otp()
    if otp_challenge2:
        challenge_id2 = otp_challenge2["challenge_id"]
        if test_wrong_otp(challenge_id2):
            results["wrong_otp"] = True
    
    # Step 7: Cleanup - disable OTP
    if not test_disable_otp(admin_token, user_id):
        log_error("OTP disable failed")
        print_summary(results)
        return
    results["disable_otp"] = True
    
    # Step 7b: Verify direct login works
    if test_user_direct_login():
        results["direct_login"] = True
    
    print_summary(results)

def print_summary(results: Dict[str, bool]):
    print(f"\n{Colors.BLUE}{'='*80}{Colors.END}")
    print(f"{Colors.BLUE}TEST SUMMARY{Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, passed_flag in results.items():
        status = f"{Colors.GREEN}✅ PASS{Colors.END}" if passed_flag else f"{Colors.RED}❌ FAIL{Colors.END}"
        print(f"{status} - {test_name}")
    
    print(f"\n{Colors.BLUE}{'='*80}{Colors.END}")
    if passed == total:
        print(f"{Colors.GREEN}ALL TESTS PASSED ({passed}/{total}){Colors.END}")
    else:
        print(f"{Colors.RED}SOME TESTS FAILED ({passed}/{total} passed){Colors.END}")
    print(f"{Colors.BLUE}{'='*80}{Colors.END}\n")

if __name__ == "__main__":
    main()

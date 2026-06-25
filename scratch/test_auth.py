import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.dashboard import app, security, CONFIG
from werkzeug.security import generate_password_hash

def run_tests():
    print("Starting Auth System Tests...")
    
    # 1. Setup test client
    client = app.test_client()
    
    # Get the configured password hash
    pw_hash = CONFIG.get("DASHBOARD_PASSWORD_HASH")
    print(f"Configured password hash: {pw_hash}")
    
    # 2. Test root access without credentials -> Should redirect to /login
    print("Test 1: Requesting '/' without token cookie...")
    resp = client.get('/')
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
    assert resp.headers['Location'] == '/login', f"Expected redirect to /login, got {resp.headers.get('Location')}"
    print("  -> Passed (Redirected to /login)")
    
    # 3. Test GET /login -> Should return 200
    print("Test 2: Requesting GET '/login'...")
    resp = client.get('/login')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b"TrendCrusher" in resp.data, "Expected 'TrendCrusher' in body"
    assert b"Authorize Connection" in resp.data, "Expected login form button in body"
    print("  -> Passed (Login page loaded successfully)")
    
    # 4. Test POST /login with incorrect password -> Should return 200 and error msg
    print("Test 3: POST '/login' with invalid password...")
    resp = client.post('/login', data={'password': 'wrong_password'})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b"Invalid password" in resp.data, "Expected error message in body"
    print("  -> Passed (Error message returned)")
    
    # 5. Test POST /login with correct password -> Should redirect to '/' and set cookie
    print("Test 4: POST '/login' with correct password...")
    original_hash = security.password_hash
    test_password = "my_secure_password"
    security.password_hash = generate_password_hash(test_password, method="scrypt")
    CONFIG["DASHBOARD_PASSWORD_HASH"] = security.password_hash
    
    try:
        resp = client.post('/login', data={'password': test_password})
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        assert resp.headers['Location'] == '/', f"Expected redirect to /, got {resp.headers.get('Location')}"
        
        # Check set-cookie header
        cookies = resp.headers.getlist('Set-Cookie')
        token_cookie = None
        for c in cookies:
            if 'access_token=' in c:
                token_cookie = c
                break
        assert token_cookie is not None, "Expected access_token cookie in headers"
        assert 'HttpOnly' in token_cookie, "Expected HttpOnly flag"
        assert 'Secure' in token_cookie, "Expected Secure flag"
        assert 'SameSite=Lax' in token_cookie, "Expected SameSite=Lax flag"
        print("  -> Passed (Redirected and cookie set with HttpOnly/Secure flags)")
        
        # Extract token value
        token = token_cookie.split('access_token=')[1].split(';')[0]
        
        # 6. Test GET '/' with valid cookie -> Should return 200
        print("Test 5: Requesting '/' with valid token cookie...")
        client.set_cookie('access_token', token)
        # Mock exchange.fetch_ticker to return a dummy ticker to avoid API calls
        import scripts.dashboard as dashboard
        original_fetch = dashboard.exchange.fetch_ticker
        dashboard.exchange.fetch_ticker = lambda symbol: {"last": 1.0, "percentage": 0.0}
        
        try:
            resp = client.get('/')
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            assert b"Live Strategy Monitoring" in resp.data, "Expected dashboard content"
            print("  -> Passed (Access granted)")
        finally:
            dashboard.exchange.fetch_ticker = original_fetch

        # 7. Test session renewal -> Age <= 1 day should generate a new cookie
        print("Test 6: Testing session renewal for token with age <= 1 day...")
        # Since we just generated the token, its age is 0.
        # It should trigger renewal and return a new Set-Cookie header.
        resp = client.get('/')
        cookies = resp.headers.getlist('Set-Cookie')
        renewal_cookie = None
        for c in cookies:
            if 'access_token=' in c:
                renewal_cookie = c
                break
        assert renewal_cookie is not None, "Expected renewed access_token cookie in headers"
        print("  -> Passed (Session renewed successfully)")

        # 8. Test direct check_token age verification
        print("Test 7: Testing direct check_token age verification...")
        t_fresh = security.generate_token()
        is_valid, should_renew = security.check_token(t_fresh)
        assert is_valid is True
        assert should_renew is True, "Fresh token should want renewal"
        print("  -> Passed (Direct check_token verification for fresh token)")
        
    finally:
        security.password_hash = original_hash
        CONFIG["DASHBOARD_PASSWORD_HASH"] = original_hash

    # 9. Test GET /logout -> Should clear cookie
    print("Test 8: Requesting GET '/logout'...")
    resp = client.get('/logout')
    assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
    cookies = resp.headers.getlist('Set-Cookie')
    logout_cookie = None
    for c in cookies:
        if 'access_token=' in c:
            logout_cookie = c
            break
    assert logout_cookie is not None, "Expected access_token cookie in headers on logout"
    assert 'max-age=0' in logout_cookie.lower() or 'expires=' in logout_cookie.lower(), "Expected cookie to be expired"
    print("  -> Passed (Cookie cleared on logout)")
    
    print("\nAll auth system tests passed successfully!")

if __name__ == '__main__':
    run_tests()

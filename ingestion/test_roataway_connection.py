#!/usr/bin/env python3
"""
Test connection to Roataway/RTEC WebSocket API

Based on roataway-web source code:
- URL: https://rtec.dekart.com/webstomp
- Protocol: STOMP over SockJS
- Login: public_rtec
- Password: iWillHackItInVisualBasic
- Topic base: /exchange/e_public_rtec_Sho0ohCiephoh2waeM9t
"""
import json
import time
import socket

# Test 1: Basic TCP connectivity
print("=== Test 1: TCP Connectivity ===")
host = "rtec.dekart.com"
port = 443

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    result = sock.connect_ex((host, port))
    if result == 0:
        print(f"[OK] TCP port {port} is open")
    else:
        print(f"[ERROR] TCP port {port} is closed (error: {result})")
    sock.close()
except Exception as e:
    print(f"[ERROR] TCP test failed: {e}")

# Test 2: Try HTTP/HTTPS
print("\n=== Test 2: HTTP Connectivity ===")
import urllib.request
import ssl

urls = [
    "https://rtec.dekart.com/",
    "https://rtec.dekart.com/webstomp/info",
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            print(f"[OK] {url}")
            print(f"     Status: {response.status}")
            content = response.read()[:200]
            print(f"     Content: {content}")
    except Exception as e:
        print(f"[--] {url}")
        print(f"     Error: {str(e)[:80]}")

# Test 3: Try WebSocket connection
print("\n=== Test 3: WebSocket Connection ===")
try:
    import websocket
    
    ws_url = "wss://rtec.dekart.com/webstomp/websocket"
    print(f"Connecting to {ws_url}...")
    
    def on_message(ws, message):
        print(f"Message: {message[:200]}")
    
    def on_error(ws, error):
        print(f"Error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"Closed: {close_status_code} - {close_msg}")
    
    def on_open(ws):
        print("[OK] WebSocket connected!")
        # Send STOMP CONNECT frame
        connect_frame = "CONNECT\naccept-version:1.1,1.0\nhost:rtec.dekart.com\nlogin:public_rtec\npasscode:iWillHackItInVisualBasic\n\n\x00"
        ws.send(connect_frame)
    
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run for 10 seconds
    import threading
    wst = threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}))
    wst.daemon = True
    wst.start()
    time.sleep(10)
    ws.close()
    
except ImportError:
    print("websocket-client not installed")
except Exception as e:
    print(f"[ERROR] WebSocket test failed: {e}")

print("\n=== Tests Complete ===")

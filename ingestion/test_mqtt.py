#!/usr/bin/env python3
"""
Test MQTT connection to Roataway/Dekart real-time transport data
"""
import paho.mqtt.client as mqtt
import json
import time

messages_received = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print('[OK] Connected to MQTT broker!')
        client.subscribe('telemetry/route/+')
        print('Subscribed to telemetry/route/+')
        print('Waiting for vehicle telemetry...')
        print()
    else:
        print(f'[ERROR] Connection failed with code {rc}')

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        messages_received.append(data)
        board = data.get('board', '?')
        route = data.get('route', '?')
        speed = data.get('speed', 0)
        lat = data.get('latitude', 0)
        lon = data.get('longitude', 0)
        print(f'  Vehicle: {board} | Route: {route} | Speed: {speed} km/h | Pos: {lat:.5f}, {lon:.5f}')
    except Exception as e:
        print(f'Error parsing: {e}')

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print('=== Testing MQTT Connection to Dekart/Roataway ===')
print()
print('Connecting to opendata.dekart.com:1945...')

try:
    client.connect('opendata.dekart.com', 1945, 60)
    
    # Run for 10 seconds to collect messages
    client.loop_start()
    time.sleep(10)
    client.loop_stop()
    client.disconnect()
    
    print()
    print(f'Total messages received: {len(messages_received)}')
    if messages_received:
        print()
        print('[SUCCESS] MQTT API is working! Real-time trolleybus data available!')
    else:
        print()
        print('[WARNING] No messages received in 10 seconds')
        print('The MQTT broker might be down or no vehicles are active.')
except Exception as e:
    print(f'[ERROR] Connection failed: {e}')

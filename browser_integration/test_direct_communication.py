#!/usr/bin/env python3
"""
Test direct de la communication Native Messaging
"""
import sys
import json
import struct
import subprocess

def send_native_message(message):
    """Envoie un message au native host et lit la réponse"""
    
    # Encoder le message
    encoded_message = json.dumps(message).encode('utf-8')
    message_length = struct.pack('I', len(encoded_message))
    
    # Lancer le native host
    proc = subprocess.Popen(
        ['./native_host_wrapper.sh'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Envoyer le message
    proc.stdin.write(message_length)
    proc.stdin.write(encoded_message)
    proc.stdin.flush()
    
    # Lire la réponse
    response_length_bytes = proc.stdout.read(4)
    if len(response_length_bytes) == 4:
        response_length = struct.unpack('I', response_length_bytes)[0]
        response_bytes = proc.stdout.read(response_length)
        response = json.loads(response_bytes.decode('utf-8'))
        return response
    else:
        stderr = proc.stderr.read().decode('utf-8')
        return {'error': 'No response', 'stderr': stderr}

def main():
    print("🧪 Test de communication Native Messaging")
    print("=" * 50)
    print()
    
    # Test 1: Ping
    print("📍 Test 1: Ping")
    response = send_native_message({"action": "ping"})
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print()
    
    # Test 2: Search credentials
    print("📍 Test 2: Search credentials")
    response = send_native_message({
        "action": "search_credentials",
        "url": "https://github.com"
    })
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print(f"   Credentials: {len(response.get('credentials', []))} trouvé(s)")
    print()
    
    # Test 3: Generate password
    print("📍 Test 3: Generate password")
    response = send_native_message({
        "action": "generate_password",
        "length": 16
    })
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    if 'password' in response:
        print(f"   Password généré: {response['password']}")
    print()
    
    print("=" * 50)
    print("✅ Tests terminés!")

if __name__ == '__main__':
    main()

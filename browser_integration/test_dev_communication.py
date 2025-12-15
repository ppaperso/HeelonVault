#!/usr/bin/env python3
"""
Test direct du native host en mode DEV
"""
import json
import struct
import subprocess
import os

# Forcer le mode DEV
os.environ['DEV_MODE'] = '1'

def send_native_message(message, dev_mode=True):
    """Envoie un message au native host et lit la réponse"""
    
    # Encoder le message
    encoded_message = json.dumps(message).encode('utf-8')
    message_length = struct.pack('I', len(encoded_message))
    
    # Choisir le wrapper approprié
    wrapper = './native_host_wrapper_dev.sh' if dev_mode else './native_host_wrapper.sh'
    
    # Lancer le native host
    proc = subprocess.Popen(
        [wrapper],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy()
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
    print("🧪 Test de communication Native Messaging (DEV)")
    print("=" * 50)
    print()
    
    # Test 1: Ping
    print("📍 Test 1: Ping (DEV)")
    response = send_native_message({"action": "ping"}, dev_mode=True)
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print()
    
    # Test 2: Search ALL credentials dans la base DEV
    print("📍 Test 2: Récupération de TOUS les credentials (showAll=True)")
    response = send_native_message({
        "action": "search_credentials",
        "url": "",
        "showAll": True
    }, dev_mode=True)
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print(f"   Credentials trouvés: {len(response.get('credentials', []))}")
    if response.get('credentials'):
        for cred in response['credentials']:
            print(f"      - {cred.get('title')} ({cred.get('username')})")
    print()
    
    # Test 3: Search credentials pour une URL spécifique
    print("📍 Test 3: Search credentials (URL spécifique)")
    response = send_native_message({
        "action": "search_credentials",
        "url": "https://test.fr"
    }, dev_mode=True)
    print(f"   Réponse: {json.dumps(response, indent=2)}")
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print(f"   Credentials trouvés: {len(response.get('credentials', []))}")
    if response.get('credentials'):
        for cred in response['credentials']:
            print(f"      - {cred.get('title')} ({cred.get('username')})")
    print()
    
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    print(f"   Credentials trouvés: {len(response.get('credentials', []))}")
    if response.get('credentials'):
        for cred in response['credentials']:
            print(f"      - {cred.get('title')} ({cred.get('username')})")
    print()
    
    # Test 4: Generate password
    print("📍 Test 4: Generate password")
    response = send_native_message({
        "action": "generate_password",
        "length": 16
    }, dev_mode=True)
    print(f"   Status: {'✅ OK' if response.get('status') == 'success' else '❌ ERREUR'}")
    if 'password' in response:
        print(f"   Password généré: {response['password']}")
    print()
    
    print("=" * 50)
    print("✅ Tests DEV terminés!")
    print()
    print("📊 Vérification des logs:")
    print("   tail -f ~/Vscode/Gestionnaire_mot_passe/logs/native_host_dev.log")

if __name__ == '__main__':
    main()

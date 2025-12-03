#!/bin/bash
# Test de connexion simple pour déboguer Firefox

echo "🧪 Test de connexion Native Messaging"
echo "======================================="
echo ""

# Créer un message de test
echo "📤 Envoi d'un message search_credentials..."
echo '{"action":"search_credentials","url":"https://example.com"}' | python3 -c '
import sys
import json
import struct

message = sys.stdin.read()
msg_dict = json.loads(message)

# Format native messaging
encoded = json.dumps(msg_dict).encode("utf-8")
length = struct.pack("I", len(encoded))

sys.stdout.buffer.write(length)
sys.stdout.buffer.write(encoded)
sys.stdout.buffer.flush()

# Lire la réponse
response_length_bytes = sys.stdin.buffer.read(4)
if len(response_length_bytes) == 4:
    response_length = struct.unpack("I", response_length_bytes)[0]
    response = sys.stdin.buffer.read(response_length).decode("utf-8")
    print("📥 Réponse reçue:", file=sys.stderr)
    print(json.dumps(json.loads(response), indent=2), file=sys.stderr)
else:
    print("❌ Pas de réponse", file=sys.stderr)
' < <(./native_host_wrapper.sh)

echo ""
echo "✅ Test terminé"

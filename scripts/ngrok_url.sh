#!/bin/bash
# Fetch current ngrok public URL from local ngrok API
# Usage: bash scripts/ngrok_url.sh
NGROK_API="http://localhost:4040/api/tunnels"
url=$(curl -s "$NGROK_API" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('tunnels', []):
    if t.get('proto') == 'https':
        print(t['public_url'])
        break
")
if [ -z "$url" ]; then
    echo "ERROR: No tunnel found. Check: docker compose logs ngrok"
else
    echo "Public URL: $url"
fi

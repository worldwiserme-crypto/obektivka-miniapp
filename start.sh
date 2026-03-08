#!/bin/bash
# Node.js yo'lini topish
export PATH="/nix/var/nix/profiles/default/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
echo "Node: $(which node)"
echo "Node version: $(node --version)"
echo "Files: $(ls /app/)"
python bot.py

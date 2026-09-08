#!/bin/zsh
cd "${0:A:h}"
/usr/bin/python3 scripts/serve.py --port 4317

#!/usr/bin/env python3
"""Robust filename sanitizer – safe for every command in the workflow."""
import sys, re

def sanitize(name: str) -> str:
    # split extension
    dot = name.rfind('.')
    if dot == -1:
        base, ext = name, ''
    else:
        base = name[:dot]
        ext = name[dot:]          # includes the dot

    # replace anything that is NOT a-zA-Z0-9._- with '_'
    # (explicit class plus '-' inside brackets, so '-' is a literal char)
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', base)

    # collapse consecutive underscores
    safe = re.sub(r'_{2,}', '_', safe)

    # strip leading hyphens and underscores (order: hyphens, then underscores)
    safe = safe.lstrip('-').lstrip('_')

    # if nothing left, use fallback
    if not safe or safe == '_':
        safe = 'output'

    return safe + ext

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} '<filename>'", file=sys.stderr)
        sys.exit(2)
    print(sanitize(sys.argv[1]))

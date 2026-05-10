#!/usr/bin/env python3
"""
Robust filename sanitizer – safe for every command in the workflow.
Handles:
- Leading hyphens (option confusion)
- Non-ASCII / special characters
- Leading dots (hidden files)
- Trailing dots/spaces (Windows issues)
- Reserved Windows names (CON, PRN, etc.)
- Empty results
- Length limits
"""
import sys
import re

# Windows reserved filenames (case-insensitive)
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

def sanitize(name: str, max_length: int = 200) -> str:
    # Remember whether the original name started with a dot (hidden file)
    starts_with_dot = name.startswith('.')

    # ---- split into base and extension ----
    dot = name.rfind('.')
    if dot <= 0:                     # no extension or leading dot (hidden file)
        base = name
        ext = ''
    else:
        base = name[:dot]
        ext = name[dot:]             # includes the dot

    # ---- sanitize both parts ----
    safe_base = re.sub(r'[^a-zA-Z0-9._-]', '_', base)
    safe_ext  = re.sub(r'[^a-zA-Z0-9._-]', '_', ext)

    # collapse consecutive underscores
    safe_base = re.sub(r'_{2,}', '_', safe_base)
    safe_ext  = re.sub(r'_{2,}', '_', safe_ext)

    # strip leading/trailing hyphens, underscores  (do NOT strip dots)
    safe_base = safe_base.strip('-_')
    safe_ext = safe_ext.strip('-_')

    # ---- ensure extension keeps its leading dot ----
    if safe_ext and not safe_ext.startswith('.'):
        safe_ext = '.' + safe_ext
    elif safe_ext == '.':
        safe_ext = ''                 # extension was only a dot → remove

    # ---- handle emptiness ----
    if not safe_base:
        safe_base = 'output'

    # re-add leading dot for hidden files if lost (but avoid double dot)
    if starts_with_dot and not safe_base.startswith('.'):
        safe_base = '.' + safe_base

    result = safe_base + safe_ext

    # ---- length limit ----
    if len(result) > max_length:
        ext_len = len(safe_ext)
        safe_base = safe_base[:max_length - ext_len]
        # trim trailing punctuation after truncation
        safe_base = safe_base.rstrip('-_.')
        result = safe_base + safe_ext

    # ---- final safeguards ----
    #  Never empty
    if not result.strip('-_.'):
        result = 'output'

    #  Reserved Windows name (case-insensitive)
    base_upper = result.split('.')[0].upper()
    if base_upper in RESERVED_NAMES:
        result = '_' + result

    #  Trailing dot or space (Windows can't handle)
    result = result.rstrip('. ')

    #  Leading hyphen (prevent option confusion)
    if result.startswith('-'):
        result = '_' + result

    #  If we removed everything, fall back
    if not result:
        result = 'output'

    return result


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} '<filename>'", file=sys.stderr)
        sys.exit(2)
    print(sanitize(sys.argv[1]))

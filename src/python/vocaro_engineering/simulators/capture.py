#!/usr/bin/env python3
"""Synchronize simctl pixels with a paused iOS UI-test captureReader phase."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)

def displays(enumeration):
    """Read connected screen IDs, never framebuffer port order or a constant ID."""
    result = []
    for block in re.split(r'(?m)^    \(\d+\) ', enumeration)[1:]:
        def field(name):
            match = re.search(r'(?m)^        ' + re.escape(name) + r': (.+)$', block)
            if not match:
                raise ValueError('Missing display field: ' + name)
            return match.group(1).strip()
        size = re.fullmatch(r'\{(\d+), (\d+)\}', field('Pixel Size'))
        if not size:
            raise ValueError('Invalid display pixel size')
        result.append(dict(id=int(field('Screen ID')), name=field('Name'),
                           type=field('Screen Type'), width=int(size[1]), height=int(size[2]),
                           scale=float(field('Preferred UI Scale')), orientation=field('UI Orientation')))
    if not result or len({item['id'] for item in result}) != len(result):
        raise ValueError('Missing or duplicate connected displays')
    return result

def expected_size(display, viewport):
    width, height = display['width'], display['height']
    if display['orientation'].startswith('Landscape'):
        width, height = height, width
    requested = (viewport['width'] * display['scale'], viewport['height'] * display['scale'])
    if not all(math.isfinite(v) and v > 0 for v in requested):
        raise ValueError('Invalid viewport')
    return (width, height) if all(abs(a - b) <= 2 for a, b in zip((width, height), requested)) else None

def validate_pixels(pixels, size):
    if (pixels['width'], pixels['height']) != size:
        raise ValueError('wrong-display or wrong-orientation pixels')
    if pixels['nonBlackFraction'] < 0.001:
        raise ValueError('all-black or nearly-black pixels')

def capture(device, request, output, inspector, receipt_hash):
    response = dict(request, status='unavailable', buildReceiptSHA256=receipt_hash,
                    capturedAtUTC=datetime.now(timezone.utc).isoformat())
    try:
        enumeration = subprocess.check_output(['xcrun', 'simctl', 'io', device, 'enumerate'],
                                               text=True, timeout=60)
        observed = displays(enumeration)
        response['displays'] = observed
        candidates = [(d, expected_size(d, request['viewport'])) for d in observed if d['type'] == 'Integrated']
        candidates = [(d, size) for d, size in candidates if size]
        if len(candidates) != 1:
            raise ValueError('Viewport does not identify exactly one integrated display')
        display, size = candidates[0]
        requested_orientation = request.get('requestedOrientation')
        if requested_orientation is not None:
            landscape = display['orientation'].startswith('Landscape')
            portrait = display['orientation'].startswith('Portrait')
            if not (requested_orientation in (3, 4) and landscape or requested_orientation in (1, 2) and portrait):
                raise ValueError('Observed display orientation differs from the requested orientation')
        integrated = [d for d in observed if d['type'] == 'Integrated']
        areas = [d['width'] * d['height'] for d in integrated]
        area = display['width'] * display['height']
        if request.get('pose') == 'Open' and area != max(areas) or request.get('pose') == 'Closed' and area != min(areas):
            raise ValueError('Viewport does not match the confirmed inner/outer pose')
        response['display'] = display
        subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot',
                        '--display=' + str(display['id']), str(output)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
        pixels = json.loads(subprocess.check_output([str(inspector), str(output)], timeout=60))
        response['pixels'] = pixels
        validate_pixels(pixels, size)
        # Reject an orientation/pose change during capture, even if its dimensions coincide.
        after = displays(subprocess.check_output(['xcrun', 'simctl', 'io', device, 'enumerate'], text=True, timeout=60))
        if after != observed:
            raise ValueError('Display changed during capture')
        response['status'] = 'available'
    except subprocess.TimeoutExpired:
        response['reason'] = 'Simulator collection command exceeded 60 seconds; visual evidence unavailable'
    except subprocess.CalledProcessError as error:
        response['reason'] = 'Simulator collection command failed with exit ' + str(error.returncode)
    except (ValueError, KeyError) as error:
        response['reason'] = str(error)
    return response

def relocate(value, original_root):
    if isinstance(value, str):
        return value.replace('__TESTROOT__', str(original_root))
    if isinstance(value, list):
        return [relocate(v, original_root) for v in value]
    if isinstance(value, dict):
        return {k: relocate(v, original_root) for k, v in value.items()}
    return value

def test_targets(manifest):
    if 'TestConfigurations' in manifest:
        return [t for c in manifest['TestConfigurations'] for t in c['TestTargets']]
    return [t for k, t in manifest.items() if k != '__xctestrun_metadata__' and isinstance(t, dict)]

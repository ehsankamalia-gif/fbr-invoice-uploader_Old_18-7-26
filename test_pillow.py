#!/usr/bin/env python3
"""Test script to check Pillow installation"""

try:
    from PIL import Image
    print("✓ Pillow imported successfully")
    print(f"Pillow version: {Image.__version__}")
except ImportError as e:
    print(f"✗ Failed to import Pillow: {e}")
    
try:
    import qrcode
    print("✓ QRCode imported successfully")
except ImportError as e:
    print(f"✗ Failed to import QRCode: {e}")
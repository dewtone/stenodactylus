#!/usr/bin/env python3
"""Stenodactylus — steno chord trainer."""

import sys
import os

# Ensure package is importable
sys.path.insert(0, os.path.dirname(__file__))

from stenodactylus.app import StenodactylusApp

if __name__ == "__main__":
    app = StenodactylusApp()
    app.run(sys.argv)

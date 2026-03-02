#!/usr/bin/env python3
"""Entrypoint: run or validate a bundle."""
from __future__ import annotations

import sys

from cli.app import main

if __name__ == "__main__":
    sys.exit(main())

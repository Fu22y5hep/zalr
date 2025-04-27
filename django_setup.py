#!/usr/bin/env python
"""
Django Setup Helper

This script sets up Django before running the stages that need Django models.
It should be run as a separate step before running the stage scripts.

Usage:
  python django_setup.py
"""

import os
import sys
import django

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zalr_backend.settings.github_actions")

# Initialize Django
django.setup()

print("Django successfully initialized with settings:", os.environ.get("DJANGO_SETTINGS_MODULE"))
print("Django apps are now ready for importing") 
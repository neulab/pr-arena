#!/usr/bin/env python3
"""
Entry point for the resolver module that resolves GitHub issues.
This file serves as a compatibility layer for the GitHub workflow.
"""

import sys
import os

# Ensure the current directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the main function from resolver_issue
from resolver.resolver_issue import main as resolver_main

def main():
    """
    Main entry point for the resolver module.
    """
    return resolver_main()

if __name__ == "__main__":
    main()
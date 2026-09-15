"""Empirical test runner for M3 challenge."""
import sys
import os

server_dir = os.path.abspath(os.path.dirname(__file__))
site_packages = os.path.join(server_dir, ".venv", "Lib", "site-packages")

sys.path.insert(0, site_packages)
sys.path.insert(0, server_dir)

import pytest

if __name__ == "__main__":
    test_files = [
        os.path.join(server_dir, "tests", "test_m3_empirical_stress.py"),
        os.path.join(server_dir, "tests", "test_ai_tax_graph.py"),
        os.path.join(server_dir, "tests", "test_ai_guardrails_eval.py"),
    ]
    sys.exit(pytest.main(test_files + ["-v", "-s"]))

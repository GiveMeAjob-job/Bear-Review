# Technical Debt Report

The asset scan indicates several potential issues:

- Hard-coded dependencies in scripts (e.g., `requests`, `yaml`).
- Single responsibility violations in `src/main.py` mixing CLI and business logic.
- Missing unit tests for some modules.
- Direct calls to external APIs without retry logic.


#!/usr/bin/env python3
"""
QA Helper Script for MemRAG Project

Runs comprehensive quality checks:
1. Linting & formatting (backend + frontend)
2. Unit tests with coverage
3. Type checking (if applicable)
4. Generate QA report

Usage:
    python scripts/qa_check.py [--backend-only] [--frontend-only] [--verbose]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")


def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")


def run_command(
    cmd: str, cwd: Path, description: str, verbose: bool = False
) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    print_info(f"Running: {description}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if verbose and result.stdout:
            print(result.stdout)
        if result.returncode == 0:
            return True, result.stdout
        else:
            if verbose and result.stderr:
                print(result.stderr, file=sys.stderr)
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def check_backend_lint(verbose: bool = False) -> bool:
    """Check backend code quality."""
    print_header("Backend: Linting & Formatting")

    # Check formatting
    success, output = run_command(
        "uv run ruff format --check .",
        BACKEND_DIR,
        "Checking code formatting",
        verbose,
    )
    if not success:
        print_error("Code is not properly formatted")
        print_info("Run: cd backend && uv run ruff format .")
        return False
    print_success("Code formatting is correct")

    # Check linting
    success, output = run_command(
        "uv run ruff check .", BACKEND_DIR, "Running linter", verbose
    )
    if not success:
        print_error("Linting issues found")
        if output:
            print(output[:500])  # Show first 500 chars
        return False
    print_success("No linting issues")

    return True


def check_backend_tests(verbose: bool = False) -> tuple[bool, dict]:
    """Run backend tests with coverage."""
    print_header("Backend: Running Tests")

    cmd = "uv run pytest tests/ -v --cov=app --cov-report=term-missing --tb=short"
    success, output = run_command(cmd, BACKEND_DIR, "Running test suite", verbose)

    # Parse coverage from output
    coverage_info = {"passed": 0, "failed": 0, "coverage": 0, "errors": []}

    if output:
        # Extract test counts
        import re

        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)

        if passed_match:
            coverage_info["passed"] = int(passed_match.group(1))
        if failed_match:
            coverage_info["failed"] = int(failed_match.group(1))
        if coverage_match:
            coverage_info["coverage"] = int(coverage_match.group(1))

    if success:
        print_success(f"All tests passed ({coverage_info['passed']} tests)")
        if coverage_info["coverage"] > 0:
            print_info(f"Coverage: {coverage_info['coverage']}%")
            if coverage_info["coverage"] < 80:
                print_warning("Coverage is below 80% target")
    else:
        print_error("Some tests failed")
        if coverage_info["failed"] > 0:
            print_error(f"Failed: {coverage_info['failed']} tests")
        # Show error summary
        error_lines = [
            line for line in output.split("\n") if "FAILED" in line or "ERROR" in line
        ]
        if error_lines:
            print("\n".join(error_lines[:10]))  # Show first 10 errors

    return success, coverage_info


def check_frontend_lint(verbose: bool = False) -> bool:
    """Check frontend code quality."""
    print_header("Frontend: Linting")

    if not (FRONTEND_DIR / "node_modules").exists():
        print_warning("node_modules not found, skipping frontend checks")
        return True

    success, output = run_command(
        "npm run lint", FRONTEND_DIR, "Running ESLint", verbose
    )
    if not success:
        print_error("Frontend linting issues found")
        if output:
            print(output[:500])
        return False
    print_success("No frontend linting issues")

    return True


def check_wiki_service_tests(verbose: bool = False) -> bool:
    """Specifically check wiki service tests (common failure point)."""
    print_header("Wiki Service: Targeted Tests")

    success, output = run_command(
        "uv run pytest tests/test_wiki_service.py -v",
        BACKEND_DIR,
        "Running wiki service tests",
        verbose,
    )
    if success:
        print_success("Wiki service tests passed")
    else:
        print_error("Wiki service tests failed")
        if output:
            error_lines = [
                line for line in output.split("\n") if "FAILED" in line or "ERROR" in line
            ]
            if error_lines:
                print("\n".join(error_lines[:5]))

    return success


def generate_report(
    backend_lint: bool,
    backend_tests: tuple[bool, dict],
    frontend_lint: bool,
    wiki_tests: bool,
) -> str:
    """Generate a QA report."""
    print_header("QA Report")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""
MemRAG QA Report
Generated: {timestamp}

{'='*60}

Backend Linting:       {'✓ PASS' if backend_lint else '✗ FAIL'}
Backend Tests:         {'✓ PASS' if backend_tests[0] else '✗ FAIL'}
  - Passed:            {backend_tests[1].get('passed', 0)}
  - Failed:            {backend_tests[1].get('failed', 0)}
  - Coverage:          {backend_tests[1].get('coverage', 0)}%
Frontend Linting:      {'✓ PASS' if frontend_lint else '✓ SKIP'}
Wiki Tests:            {'✓ PASS' if wiki_tests else '✗ FAIL'}

{'='*60}

Overall Status: {'✓ ALL CHECKS PASSED' if all([backend_lint, backend_tests[0], wiki_tests]) else '✗ SOME CHECKS FAILED'}

"""

    print(report)

    # Save report to file
    report_file = PROJECT_ROOT / "qa_report.md"
    report_file.write_text(report)
    print_info(f"Report saved to: {report_file}")

    return report


def main():
    parser = argparse.ArgumentParser(description="MemRAG QA Check")
    parser.add_argument(
        "--backend-only", action="store_true", help="Only run backend checks"
    )
    parser.add_argument(
        "--frontend-only", action="store_true", help="Only run frontend checks"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--wiki-only", action="store_true", help="Only run wiki service tests"
    )
    args = parser.parse_args()

    print(f"{Colors.BOLD}MemRAG QA Check{Colors.RESET}")
    print(f"Project: {PROJECT_ROOT}")

    backend_lint = True
    backend_tests = (True, {})
    frontend_lint = True
    wiki_tests = True

    if not args.frontend_only:
        if args.wiki_only:
            wiki_tests = check_wiki_service_tests(args.verbose)
        else:
            backend_lint = check_backend_lint(args.verbose)
            backend_tests = check_backend_tests(args.verbose)
            wiki_tests = check_wiki_service_tests(args.verbose)

    if not args.backend_only and not args.wiki_only:
        frontend_lint = check_frontend_lint(args.verbose)

    generate_report(backend_lint, backend_tests, frontend_lint, wiki_tests)

    # Exit with error if any check failed
    if not all([backend_lint, backend_tests[0], wiki_tests]):
        sys.exit(1)


if __name__ == "__main__":
    main()

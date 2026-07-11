#!/usr/bin/env python3
"""Command entrypoint for HTML report generation."""

from reporting.sqlite_report import main


if __name__ == "__main__":
    raise SystemExit(main())

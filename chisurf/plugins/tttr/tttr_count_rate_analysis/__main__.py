"""
Entry point for running the Count Rate Analysis CLI directly.

This allows the CLI to be run with:
python -m chisurf.plugins.tttr.tttr_count_rate_analysis
"""

from chisurf.plugins.tttr.tttr_count_rate_analysis.cli import cli

if __name__ == "__main__":
    cli()

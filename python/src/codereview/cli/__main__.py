"""Entry point for ``python -m codereview.cli``."""

import sys

from codereview.cli import cli

if __name__ == "__main__":
    sys.exit(cli())

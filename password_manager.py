#!/usr/bin/env python3
"""Point d'entrée de l'application GTK."""

from __future__ import annotations

import sys

from src.app.application import PasswordManagerApplication


def main() -> int:
    app = PasswordManagerApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())

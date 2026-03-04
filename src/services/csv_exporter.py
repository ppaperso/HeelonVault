"""Service d'exportation des entrées vers un fichier CSV."""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import TypedDict

from src.i18n import _
from src.models.password_entry import PasswordEntry

logger = logging.getLogger(__name__)

class ExportResult(TypedDict):
    success: bool
    exported_count: int
    file_path: str
    error: str | None

class CSVExporter:
    """Exporte des entrées de mots de passe vers un fichier CSV."""

    HEADER = [
        "title",
        "username",
        "password",
        "url",
        "notes",
        "category",
        "tags",
        "password_validity_days",
    ]

    def export_to_csv(
        self,
        file_path: Path,
        entries: list[PasswordEntry],
        *,
        delimiter: str = ",",
        include_header: bool = True,
    ) -> ExportResult:
        """Exporte une liste d'entrées vers un fichier CSV.

        Returns:
            Dict avec les clés: success, exported_count, file_path, error
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8", newline="") as csv_file:
                writer = csv.writer(csv_file, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

                if include_header:
                    writer.writerow(self.HEADER)

                for entry in entries:
                    validity_days = (
                        ""
                        if entry.password_validity_days is None
                        else entry.password_validity_days
                    )
                    writer.writerow(
                        [
                            entry.title,
                            entry.username,
                            entry.password,
                            entry.url,
                            entry.notes,
                            entry.category,
                            ",".join(entry.tags),
                            validity_days,
                        ]
                    )

            logger.info("CSV export completed: %d entries to %s", len(entries), file_path)
            return {
                "success": True,
                "exported_count": len(entries),
                "file_path": str(file_path),
                "error": None,
            }
        except (OSError, csv.Error, ValueError, TypeError) as exc:
            logger.exception("CSV export failed to %s", file_path)
            return {
                "success": False,
                "exported_count": 0,
                "file_path": str(file_path),
                "error": str(exc),
            }

    def export_to_encrypted_zip(
        self,
        file_path: Path,
        entries: list[PasswordEntry],
        *,
        password: str,
        delimiter: str = ",",
        include_header: bool = True,
    ) -> ExportResult:
        """Exporte les entrées dans un ZIP chiffré par mot de passe (AES).

        Le ZIP contient un unique fichier CSV.
        """
        if not password:
            return {
                "success": False,
                "exported_count": 0,
                "file_path": str(file_path),
                "error": _("Export password is required"),
            }

        try:
            import pyzipper
        except ImportError:
            return {
                "success": False,
                "exported_count": 0,
                "file_path": str(file_path),
                "error": _("Missing pyzipper module (install dependencies)"),
            }

        try:
            zip_path = (
                file_path
                if file_path.suffix.lower() == ".zip"
                else file_path.with_suffix(".zip")
            )
            zip_path.parent.mkdir(parents=True, exist_ok=True)

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

            if include_header:
                writer.writerow(self.HEADER)

            for entry in entries:
                validity_days = (
                    ""
                    if entry.password_validity_days is None
                    else entry.password_validity_days
                )
                writer.writerow(
                    [
                        entry.title,
                        entry.username,
                        entry.password,
                        entry.url,
                        entry.notes,
                        entry.category,
                        ",".join(entry.tags),
                        validity_days,
                    ]
                )

            inner_csv_name = f"{zip_path.stem}.csv"
            csv_payload = csv_buffer.getvalue().encode("utf-8")

            with pyzipper.AESZipFile(
                zip_path,
                "w",
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES,
            ) as zip_file:
                zip_file.setpassword(password.encode("utf-8"))
                zip_file.writestr(inner_csv_name, csv_payload)

            logger.info("Encrypted ZIP export completed: %d entries to %s", len(entries), zip_path)
            return {
                "success": True,
                "exported_count": len(entries),
                "file_path": str(zip_path),
                "error": None,
            }
        except (OSError, csv.Error, ValueError, TypeError) as exc:
            logger.exception("Encrypted ZIP export failed to %s", file_path)
            return {
                "success": False,
                "exported_count": 0,
                "file_path": str(file_path),
                "error": str(exc),
            }

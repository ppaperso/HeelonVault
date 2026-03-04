"""
Service d'importation de CSV depuis d'autres gestionnaires de mots de passe
Supporte: LastPass, et format générique
"""

import csv
import logging
from pathlib import Path

from src.i18n import _

logger = logging.getLogger(__name__)


class CSVImporter:
    """Importe des mots de passe depuis un fichier CSV"""

    # Formats supportés avec leurs délimiteurs et colonnes
    FORMATS = {
        'lastpass': {
            'delimiter': ';',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'CSV (;)'
        },
        'generic_comma': {
            'delimiter': ',',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'CSV (,)'
        },
        'generic_semicolon': {
            'delimiter': ';',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'CSV (;)'
        }
    }

    def __init__(self):
        self.entries = []
        self.errors = []
        self.warnings = []

    def detect_format(self, file_path: Path) -> str | None:
        """Détecte automatiquement le format du CSV

        Args:
            file_path: Chemin vers le fichier CSV

        Returns:
            str: Nom du format détecté ou None
        """
        try:
            with open(file_path, encoding='utf-8') as f:
                first_line = f.readline().strip()

                # Compter les délimiteurs
                semicolon_count = first_line.count(';')
                comma_count = first_line.count(',')

                if semicolon_count >= 3:
                    return 'lastpass'  # Par défaut pour point-virgule
                elif comma_count >= 3:
                    return 'generic_comma'

        except (OSError, UnicodeDecodeError, csv.Error) as e:
            logger.error("Error while detecting CSV format: %s", e)

        return None

    def import_from_csv(self, file_path: Path, format_name: str = None,
                       has_header: bool = False) -> dict:
        """Importe les entrées depuis un fichier CSV

        Args:
            file_path: Chemin vers le fichier CSV
            format_name: Nom du format (auto-détection si None)
            has_header: True si la première ligne est un en-tête

        Returns:
            Dict avec 'success', 'entries', 'errors', 'warnings'
        """
        self.entries = []
        self.errors = []
        self.warnings = []

        # Détection automatique du format si non spécifié
        if format_name is None:
            format_name = self.detect_format(file_path)
            if format_name is None:
                return {
                    'success': False,
                    'entries': [],
                    'errors': [_('Unknown CSV format')],
                    'warnings': []
                }

        if format_name not in self.FORMATS:
            return {
                'success': False,
                'entries': [],
                'errors': [_('Unsupported format "%(format)s"') % {'format': format_name}],
                'warnings': []
            }

        format_config = self.FORMATS[format_name]
        delimiter = format_config['delimiter']
        expected_columns = format_config['columns']

        try:
            with open(file_path, encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter)

                # Sauter la ligne d'en-tête si présente
                if has_header:
                    next(reader, None)

                for line_num, row in enumerate(reader, start=1 + (1 if has_header else 0)):
                    try:
                        entry = self._parse_row(row, expected_columns, line_num)
                        if entry:
                            self.entries.append(entry)
                    except (ValueError, TypeError, IndexError, AttributeError) as e:
                        self.errors.append(
                            _("Line %(line)d: %(error)s")
                            % {'line': line_num, 'error': str(e)}
                        )

            logger.info(
                "CSV import: %d entries imported, %d errors, %d warnings",
                len(self.entries),
                len(self.errors),
                len(self.warnings),
            )

            return {
                'success': len(self.entries) > 0,
                'entries': self.entries,
                'errors': self.errors,
                'warnings': self.warnings
            }

        except (OSError, UnicodeDecodeError, csv.Error) as e:
            logger.error("Error while importing CSV: %s", e)
            return {
                'success': False,
                'entries': [],
                'errors': [
                    _("Error while reading file: %(error)s") % {'error': str(e)}
                ],
                'warnings': []
            }

    def _parse_row(self, row: list[str], expected_columns: list[str],
                   line_num: int) -> dict | None:
        """Parse une ligne du CSV

        Args:
            row: Liste des valeurs de la ligne
            expected_columns: Liste des noms de colonnes attendues
            line_num: Numéro de ligne (pour les messages d'erreur)

        Returns:
            Dict avec les données de l'entrée ou None si ligne invalide
        """
        # Vérifier le nombre de colonnes
        if len(row) < len(expected_columns):
            self.warnings.append(
                _(
                    "Line %(line)d: insufficient column count "
                    "(%(actual)d instead of %(expected)d)"
                )
                % {
                    'line': line_num,
                    'actual': len(row),
                    'expected': len(expected_columns),
                }
            )
            # Compléter avec des valeurs vides
            row.extend([''] * (len(expected_columns) - len(row)))
        elif len(row) > len(expected_columns):
            self.warnings.append(
                _(
                    "Line %(line)d: too many columns, extra columns will be ignored"
                )
                % {'line': line_num}
            )

        # Créer le dictionnaire d'entrée
        entry = {}
        for i, col_name in enumerate(expected_columns):
            value = row[i].strip() if i < len(row) else ''

            # Mapper les colonnes vers le format attendu
            if col_name == 'url':
                entry['url'] = value
            elif col_name == 'username':
                entry['username'] = value
            elif col_name == 'password':
                entry['password'] = value
            elif col_name == 'name':
                entry['name'] = value

        # Log pour debug
        pwd_preview = entry.get('password')[:3] if entry.get('password') else 'EMPTY'
        logger.debug(
            "Line %d: name='%s', password='%s...'",
            line_num,
            entry.get("name"),
            pwd_preview,
        )

        # Validation minimale
        if not entry.get('name') or not entry.get('name').strip():
            self.warnings.append(
                _("Line %(line)d: empty entry name, using a default name")
                % {'line': line_num}
            )
            entry['name'] = _("Imported entry %(line)d") % {'line': line_num}

        if not entry.get('password') or not entry.get('password').strip():
            self.warnings.append(_("Line %(line)d: empty password") % {'line': line_num})

        # Valeurs par défaut (sans forcer de catégorie/tags)
        entry.setdefault('url', '')
        entry.setdefault('username', '')
        entry.setdefault('notes', _("Imported from CSV (line %(line)d)") % {'line': line_num})
        entry.setdefault('category', '')  # Pas de catégorie par défaut
        entry.setdefault('tags', [])  # Pas de tags par défaut

        return entry

    @staticmethod
    def get_supported_formats() -> dict[str, str]:
        """Retourne la liste des formats supportés

        Returns:
            Dict: {format_name: description}
        """
        return {name: config['description']
                for name, config in CSVImporter.FORMATS.items()}

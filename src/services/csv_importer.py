"""
Service d'importation de CSV depuis d'autres gestionnaires de mots de passe
Supporte: LastPass, et format générique
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class CSVImporter:
    """Importe des mots de passe depuis un fichier CSV"""
    
    # Formats supportés avec leurs délimiteurs et colonnes
    FORMATS = {
        'lastpass': {
            'delimiter': ';',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'LastPass (url;username;password;name)'
        },
        'generic_comma': {
            'delimiter': ',',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'Format générique CSV (url,username,password,name)'
        },
        'generic_semicolon': {
            'delimiter': ';',
            'columns': ['url', 'username', 'password', 'name'],
            'description': 'Format générique CSV (url;username;password;name)'
        }
    }
    
    def __init__(self):
        self.entries = []
        self.errors = []
        self.warnings = []
    
    def detect_format(self, file_path: Path) -> Optional[str]:
        """Détecte automatiquement le format du CSV
        
        Args:
            file_path: Chemin vers le fichier CSV
            
        Returns:
            str: Nom du format détecté ou None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                
                # Compter les délimiteurs
                semicolon_count = first_line.count(';')
                comma_count = first_line.count(',')
                
                if semicolon_count >= 3:
                    return 'lastpass'  # Par défaut pour point-virgule
                elif comma_count >= 3:
                    return 'generic_comma'
                    
        except Exception as e:
            logger.error(f"Erreur lors de la détection du format: {e}")
        
        return None
    
    def import_from_csv(self, file_path: Path, format_name: str = None, 
                       has_header: bool = False) -> Dict:
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
                    'errors': ['Format CSV non reconnu'],
                    'warnings': []
                }
        
        if format_name not in self.FORMATS:
            return {
                'success': False,
                'entries': [],
                'errors': [f'Format "{format_name}" non supporté'],
                'warnings': []
            }
        
        format_config = self.FORMATS[format_name]
        delimiter = format_config['delimiter']
        expected_columns = format_config['columns']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter)
                
                # Sauter la ligne d'en-tête si présente
                if has_header:
                    next(reader, None)
                
                for line_num, row in enumerate(reader, start=1 + (1 if has_header else 0)):
                    try:
                        entry = self._parse_row(row, expected_columns, line_num)
                        if entry:
                            self.entries.append(entry)
                    except Exception as e:
                        self.errors.append(f"Ligne {line_num}: {str(e)}")
            
            logger.info(f"Import CSV: {len(self.entries)} entrées importées, "
                       f"{len(self.errors)} erreurs, {len(self.warnings)} avertissements")
            
            return {
                'success': len(self.entries) > 0,
                'entries': self.entries,
                'errors': self.errors,
                'warnings': self.warnings
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de l'import CSV: {e}")
            return {
                'success': False,
                'entries': [],
                'errors': [f"Erreur lors de la lecture du fichier: {str(e)}"],
                'warnings': []
            }
    
    def _parse_row(self, row: List[str], expected_columns: List[str], 
                   line_num: int) -> Optional[Dict]:
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
                f"Ligne {line_num}: nombre de colonnes insuffisant "
                f"({len(row)} au lieu de {len(expected_columns)})"
            )
            # Compléter avec des valeurs vides
            row.extend([''] * (len(expected_columns) - len(row)))
        elif len(row) > len(expected_columns):
            self.warnings.append(
                f"Ligne {line_num}: trop de colonnes, les colonnes supplémentaires seront ignorées"
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
        
        # Validation minimale
        if not entry.get('name'):
            self.warnings.append(f"Ligne {line_num}: nom d'entrée vide, utilisation d'un nom par défaut")
            entry['name'] = f"Entrée importée {line_num}"
        
        if not entry.get('password'):
            self.warnings.append(f"Ligne {line_num}: mot de passe vide")
        
        # Valeurs par défaut
        entry.setdefault('url', '')
        entry.setdefault('username', '')
        entry.setdefault('notes', f'Importé depuis CSV (ligne {line_num})')
        entry.setdefault('category', 'Importé')
        entry.setdefault('tags', ['import'])
        
        return entry
    
    @staticmethod
    def get_supported_formats() -> Dict[str, str]:
        """Retourne la liste des formats supportés
        
        Returns:
            Dict: {format_name: description}
        """
        return {name: config['description'] 
                for name, config in CSVImporter.FORMATS.items()}

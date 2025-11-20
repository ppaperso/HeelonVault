#!/usr/bin/env python3
"""
Test du parsing CSV pour valider l'import
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.csv_importer import CSVImporter

def test_csv_import():
    """Test d'import du fichier CSV LastPass"""
    
    csv_file = Path(__file__).parent.parent / "export-csv" / "lastpass_vault_export.csv"
    
    if not csv_file.exists():
        print(f"❌ Fichier non trouvé: {csv_file}")
        return
    
    print(f"📂 Fichier à tester: {csv_file}")
    print(f"📊 Contenu du fichier:")
    print("-" * 80)
    with open(csv_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            print(f"Ligne {i}: {line.rstrip()}")
    print("-" * 80)
    print()
    
    # Test de détection du format
    importer = CSVImporter()
    detected_format = importer.detect_format(csv_file)
    print(f"🔍 Format détecté: {detected_format}")
    print()
    
    # Test d'import avec header
    print("📥 Import avec header=True:")
    result = importer.import_from_csv(csv_file, format_name=detected_format, has_header=True)
    
    print(f"✅ Succès: {result['success']}")
    print(f"📊 Entrées importées: {len(result['entries'])}")
    print(f"❌ Erreurs: {len(result['errors'])}")
    print(f"⚠️  Avertissements: {len(result['warnings'])}")
    print()
    
    if result['errors']:
        print("Erreurs:")
        for error in result['errors']:
            print(f"  - {error}")
        print()
    
    if result['warnings']:
        print("Avertissements:")
        for warning in result['warnings']:
            print(f"  - {warning}")
        print()
    
    print("=" * 80)
    print("ENTRÉES PARSÉES:")
    print("=" * 80)
    for i, entry in enumerate(result['entries'], 1):
        print(f"\nEntrée #{i}:")
        print(f"  name:     '{entry.get('name')}'")
        print(f"  username: '{entry.get('username')}'")
        print(f"  password: '{entry.get('password')}'")
        print(f"  url:      '{entry.get('url')}'")
        print(f"  category: '{entry.get('category')}'")
        print(f"  tags:     {entry.get('tags')}")
        print(f"  notes:    '{entry.get('notes')}'")

if __name__ == "__main__":
    test_csv_import()

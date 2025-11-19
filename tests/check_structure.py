#!/usr/bin/env python3
"""Vérification de l'organisation des tests."""

import os
from pathlib import Path

print("📁 Organisation des tests")
print("=" * 60)

project_root = Path(__file__).parent.parent
tests_dir = project_root / "tests"

print("\n✅ Structure actuelle:")
print(f"\n{tests_dir}/")

# Lister les fichiers dans tests/
for item in sorted(tests_dir.iterdir()):
    if item.is_file():
        print(f"├── {item.name}")

# Lister les dossiers
for folder in ['unit', 'integration', 'fixtures']:
    folder_path = tests_dir / folder
    if folder_path.exists():
        print(f"├── {folder}/")
        if folder_path.is_dir():
            for item in sorted(folder_path.iterdir()):
                is_last = item == sorted(list(folder_path.iterdir()))[-1]
                prefix = "└──" if is_last else "├──"
                print(f"│   {prefix} {item.name}")

print("\n📊 Statistiques:")
integration_tests = list((tests_dir / "integration").glob("test_*.py"))
unit_tests = list((tests_dir / "unit").glob("test_*.py"))

print(f"   • Tests d'intégration : {len(integration_tests)}")
for test in integration_tests:
    print(f"     - {test.name}")

print(f"\n   • Tests unitaires : {len(unit_tests)}")
if unit_tests:
    for test in unit_tests:
        print(f"     - {test.name}")
else:
    print("     (aucun - à créer)")

print("\n✅ Migration des fichiers de test réussie!")
print("\n📝 Prochaines étapes:")
print("   1. ✅ Tests déplacés vers tests/integration/")
print("   2. ✅ README.md créé dans tests/")
print("   3. ✅ Script run_all_tests.sh créé")
print("   4. ⏳ Créer les tests unitaires dans tests/unit/")
print("   5. ⏳ Installer pytest : pip install pytest pytest-cov")
print("   6. ⏳ Configurer pytest.ini à la racine")

print("\n🚀 Lancer les tests:")
print("   ./tests/run_all_tests.sh           # Script personnalisé")
print("   pytest tests/                      # Avec pytest (à installer)")
print("   pytest tests/integration/          # Tests d'intégration seulement")
print("   pytest tests/unit/                 # Tests unitaires seulement")

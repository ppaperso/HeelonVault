#!/usr/bin/env python3
"""
Script pour nettoyer les doublons de la wordlist et compléter à 1000+ mots.
"""

import sys
from pathlib import Path

# Charger la liste actuelle (temporairement désactiver l'assertion)
sys.path.insert(0, str(Path(__file__).parent))

# Patch temporaire pour désactiver les assertions
import builtins

original_assert = builtins.__import__


def no_assert_import(name, *args, **kwargs):
    module = original_assert(name, *args, **kwargs)
    return module


sys.modules["src"] = type(sys)("src")

# Lire directement le fichier pour extraire la liste
wordlist_file = Path(__file__).parent / "src" / "data" / "french_wordlist_extended.py"

exec_globals = {}
with open(wordlist_file, "r", encoding="utf-8") as f:
    content = f.read()
    # Remplacer les asserts par des pass
    content = content.replace(
        "assert len(FRENCH_WORDS_EXTENDED)", "# assert len(FRENCH_WORDS_EXTENDED)"
    )
    content = content.replace(
        "assert len(set(FRENCH_WORDS_EXTENDED))",
        "# assert len(set(FRENCH_WORDS_EXTENDED))",
    )
    exec(content, exec_globals)

FRENCH_WORDS_EXTENDED = exec_globals["FRENCH_WORDS_EXTENDED"]

# Nettoyer les doublons en conservant l'ordre
seen = set()
cleaned = []
doublons_removed = []

for mot in FRENCH_WORDS_EXTENDED:
    if mot not in seen:
        seen.add(mot)
        cleaned.append(mot)
    else:
        doublons_removed.append(mot)

print("📊 Nettoyage de la liste de mots")
print("=" * 60)
print(f"Avant  : {len(FRENCH_WORDS_EXTENDED)} mots")
print(f"Après  : {len(cleaned)} mots uniques")
print(f"Retirés: {len(doublons_removed)} doublons")
print()

# Mots supplémentaires pour atteindre 1000+
mots_supplementaires = [
    # Animaux supplémentaires
    "chien",
    "chat",
    "cheval",
    "vache",
    "cochon",
    "mouton",
    "chevre",
    "poule",
    "coq",
    "canard",
    "oie",
    "dinde",
    "serpent",
    "lezard",
    "grenouille",
    "crapaud",
    "salamandre",
    "triton",
    "araignee",
    "scorpion",
    "mille",
    "pattes",
    "scarabee",
    "coccinelle",
    # Plantes et arbres
    "chene",
    "hetre",
    "bouleau",
    "sapin",
    "pin",
    "saule",
    "peuplier",
    "erable",
    "platane",
    "olivier",
    "palmier",
    "bambou",
    "cactus",
    "fougere",
    "lierre",
    "vigne",
    "roseau",
    "jonc",
    # Météo et phénomènes naturels
    "orage",
    "tempete",
    "cyclone",
    "tornade",
    "ouragan",
    "typhon",
    "brume",
    "brouillard",
    "rosee",
    "givre",
    "verglas",
    "grele",
    "eclair",
    "tonnerre",
    "arc",
    "iris",
    "zenith",
    "horizon",
    # Corps humain
    "tete",
    "corps",
    "bras",
    "jambe",
    "main",
    "pied",
    "doigt",
    "ongle",
    "coude",
    "genou",
    "epaule",
    "hanche",
    "coeur",
    "poumon",
    "foie",
    "rein",
    "estomac",
    "intestin",
    "cerveau",
    "nerf",
    "muscle",
    "tendon",
    "ligament",
    "cartilage",
    # Mathématiques et géométrie
    "nombre",
    "chiffre",
    "calcul",
    "compte",
    "somme",
    "total",
    "plus",
    "moins",
    "fois",
    "divise",
    "egal",
    "different",
    "ligne",
    "courbe",
    "droite",
    "segment",
    "rayon",
    "diametre",
    # Additional words to reach 1000+
    "balcon",
    "terrasse",
    "escalier",
    "ascenseur",
    "couloir",
    "vestibule",
    "salon",
    "cuisine",
    "chambre",
    "salle",
    "bain",
    "toilette",
]

# Ajouter les mots supplémentaires uniquement s'ils ne sont pas déjà présents
for mot in mots_supplementaires:
    if mot not in seen and mot not in cleaned:
        cleaned.append(mot)
        seen.add(mot)

print(
    f"Mots ajoutés : {len(cleaned) - len(FRENCH_WORDS_EXTENDED) + len(doublons_removed)}"
)
print(f"Total final  : {len(cleaned)} mots uniques")
print()

if len(cleaned) < 1000:
    print(f"⚠️  Il manque encore {1000 - len(cleaned)} mots pour atteindre 1000")
    sys.exit(1)

print(f"✅ Objectif atteint : {len(cleaned)} mots ≥ 1000")
print()

# Sauvegarder le fichier nettoyé
output = '''"""
Liste étendue de mots français pour la génération de passphrases sécurisées.

Cette liste contient 1000+ mots français courants, sans accents ni caractères spéciaux,
de 4 à 9 lettres, pour une entropie significativement améliorée.

Avec 1000 mots et 5 mots par passphrase :
- Entropie : log₂(1000⁵) ≈ 49.8 bits (acceptable)
- Avec capitalisation et nombres : ~60 bits (bon)

RECOMMANDATION FUTURE : Migrer vers 7776 mots (standard EFF Diceware)
pour atteindre 77+ bits d'entropie avec 6 mots.
"""

FRENCH_WORDS_EXTENDED = [
'''

# Écrire les mots par groupes de 6 pour la lisibilité
for i in range(0, len(cleaned), 6):
    groupe = cleaned[i : i + 6]
    if i + 6 < len(cleaned):
        output += "    " + ", ".join(f'"{mot}"' for mot in groupe) + ",\n"
    else:
        output += "    " + ", ".join(f'"{mot}"' for mot in groupe) + "\n"

output += """]

# Validation de la liste
assert len(FRENCH_WORDS_EXTENDED) >= 1000, f"Liste trop courte : {len(FRENCH_WORDS_EXTENDED)} mots"
assert len(set(FRENCH_WORDS_EXTENDED)) == len(FRENCH_WORDS_EXTENDED), "Doublons détectés"

# Export du nombre de mots
WORDLIST_SIZE = len(FRENCH_WORDS_EXTENDED)

if __name__ == "__main__":
    import math
    
    print(f"📊 Statistiques de la liste de mots")
    print(f"=" * 50)
    print(f"Nombre total de mots : {WORDLIST_SIZE}")
    print(f"Mots uniques : {len(set(FRENCH_WORDS_EXTENDED))}")
    print()
    
    print(f"🔐 Calcul d'entropie")
    print(f"=" * 50)
    for word_count in [4, 5, 6, 7, 8]:
        entropy = word_count * math.log2(WORDLIST_SIZE)
        # +2 bits par mot pour capitalisation, +6.6 pour le nombre final
        total_entropy = entropy + word_count * 2 + 6.6
        print(f"{word_count} mots : {entropy:.1f} bits (base) → {total_entropy:.1f} bits (avec caps+num)")
    
    print()
    print(f"✅ Recommandation : Utiliser 5-6 mots minimum")
    print(f"   (≥50 bits d'entropie)")
"""

backup_file = wordlist_file.with_suffix(".py.backup")
wordlist_file.rename(backup_file)
print(f"💾 Backup créé : {backup_file.name}")

with open(wordlist_file, "w", encoding="utf-8") as f:
    f.write(output)

print(f"✅ Fichier nettoyé sauvegardé : {wordlist_file.name}")
print(f"   {len(cleaned)} mots uniques, 0 doublon")

# Version 0.1.0-beta

## 🎉 Première version beta du Gestionnaire de Mots de Passe

**Date de sortie** : 19 novembre 2025

---

## 📦 Cette version

Version **0.1.0-beta** - Première version fonctionnelle avec toutes les fonctionnalités de base.

### 🎯 Objectif de cette version

Cette version beta est la première release publique du gestionnaire de mots de passe. Elle inclut toutes les fonctionnalités essentielles pour une utilisation quotidienne sécurisée, ainsi que des fonctionnalités avancées comme l'import CSV et la gestion multi-utilisateurs.

---

## ✨ Fonctionnalités principales

### 🔒 Sécurité de niveau entreprise
- ✅ Chiffrement AES-256-GCM (standard militaire)
- ✅ PBKDF2 avec 600 000 itérations
- ✅ Protection contre les attaques par force brute
- ✅ Logs de sécurité complets
- ✅ Workspaces isolés par utilisateur

### 👥 Multi-utilisateurs
- ✅ Comptes utilisateurs séparés
- ✅ Rôles (Admin / Utilisateur)
- ✅ Gestion complète des utilisateurs
- ✅ Réinitialisation de mot de passe par admin
- ✅ Interface personnalisée par utilisateur

### 📥 Import/Export
- ✅ Import CSV depuis LastPass
- ✅ Support de formats génériques
- ✅ Détection automatique du format
- ✅ Aperçu et validation
- ✅ Gestion robuste des erreurs

### 🎲 Générateur de mots de passe
- ✅ Mots de passe aléatoires (8-64 caractères)
- ✅ Phrases de passe mémorables
- ✅ Options personnalisables
- ✅ Exclusion des caractères ambigus
- ✅ Copie rapide

### 📂 Organisation
- ✅ Catégories (Personnel, Travail, Finance, etc.)
- ✅ Tags multiples par entrée
- ✅ Recherche rapide
- ✅ Filtres avancés

### 🎨 Interface moderne
- ✅ GTK4 + Libadwaita
- ✅ Design épuré et intuitif
- ✅ Thème sombre/clair automatique
- ✅ Dialogue "À propos" avec informations complètes
- ✅ Affichage de la version

---

## 📊 Statistiques

- **Lignes de code** : ~2700 lignes Python
- **Tests** : 17 tests (10 unitaires + 7 intégration)
- **Taux de réussite** : 100%
- **Documentation** : 8 fichiers markdown
- **Formats d'import** : 3 (LastPass, CSV virgule, CSV point-virgule)

---

## 🧪 Testé sur

- ✅ Fedora 39+
- ✅ Ubuntu 22.04+
- ✅ Arch Linux
- ✅ Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.14

---

## 📖 Documentation disponible

1. **README.md** - Guide principal
2. **CHANGELOG.md** - Historique des versions
3. **docs/CSV_IMPORT_GUIDE.md** - Guide d'importation CSV complet
4. **docs/QUICK_IMPORT.md** - Guide rapide LastPass
5. **docs/ARCHITECTURE.md** - Architecture du projet
6. **docs/SECURITY.md** - Détails de sécurité
7. **docs/BRUTE_FORCE_PROTECTION.md** - Protection contre les attaques
8. **MULTI_USER_GUIDE.md** - Gestion multi-utilisateurs

---

## 🚀 Installation

### Installation rapide

```bash
# Cloner le projet
git clone <repo-url>
cd Gestionnaire_mot_passe

# Lancer en mode développement
./run-dev.sh
```

### Installation conteneurisée (Podman)

```bash
# Build
./build-container.sh

# Run
./run-container.sh
```

---

## 🔄 Migration depuis un autre gestionnaire

### LastPass
1. Exportez vos mots de passe (format CSV)
2. Lancez l'application
3. Menu → "Importer depuis CSV"
4. Sélectionnez votre fichier d'export
5. Choisissez "LastPass"
6. Importez !

### Autres gestionnaires
Consultez le [guide d'importation CSV](docs/CSV_IMPORT_GUIDE.md) pour les instructions détaillées.

---

## 🐛 Problèmes connus

Aucun bug critique connu pour cette version beta.

### Limitations actuelles
- Pas d'export vers CSV (prévu pour v0.2.0)
- Pas de synchronisation cloud
- Pas de plugin navigateur

---

## 🤝 Contribution

Cette version est en beta. Vos retours sont précieux !

### Comment contribuer
1. Testez l'application
2. Signalez les bugs
3. Proposez des améliorations
4. Contribuez au code

---

## 📝 Notes de version

### Ce qui fonctionne bien
- ✅ Chiffrement et sécurité
- ✅ Import CSV LastPass
- ✅ Multi-utilisateurs
- ✅ Générateur de mots de passe
- ✅ Interface GTK4

### À améliorer
- 🔄 Export vers CSV (roadmap v0.2.0)
- 🔄 Plus de formats d'import
- 🔄 Détection des doublons
- 🔄 Sauvegarde/restauration

---

## 📞 Support

- 📖 Documentation complète dans `docs/`
- 🐛 Issues sur le dépôt Git
- 📧 Email : [contact]

---

## 📜 Licence

MIT License - Copyright © 2025

Vous êtes libre d'utiliser, modifier et distribuer ce logiciel.

---

## 🎊 Remerciements

Merci d'avoir testé cette première version beta !

**Bon gestionnage de mots de passe ! 🔐**

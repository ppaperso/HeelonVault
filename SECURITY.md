# Politique de Sécurité

## Versions Supportées

Nous fournissons des correctifs de sécurité pour les versions suivantes :

| Version | Supportée                 |
| ------- | ------------------        |
| 0.4.x   | :white_check_mark:        |
| 0.3.x   | :warning: Support limité  |
| < 0.3   | :x: Non supportée         |

## Signaler une Vulnérabilité

### ⚠️ IMPORTANT : NE CRÉEZ PAS D'ISSUE PUBLIQUE POUR LES VULNÉRABILITÉS DE SÉCURITÉ

Si vous découvrez une vulnérabilité de sécurité, merci de nous la signaler de manière responsable :

### 📧 Contact

Envoyez un email à : <security@heelonys.fr>

### 📝 Informations à inclure

Pour nous aider à évaluer et corriger rapidement la vulnérabilité, veuillez inclure :

- **Description détaillée** de la vulnérabilité
- **Étapes de reproduction** (si possible)
- **Impact potentiel** (quelles données/fonctionnalités sont affectées)
- **Version affectée** du logiciel
- **Votre environnement** (OS, version Python, etc.)
- **Preuve de concept** (si applicable, mais ne pas exploiter publiquement)
- **Suggestions de correction** (si vous en avez)

### ⏱️ Notre engagement

Nous nous engageons à :

1. **Accuser réception** de votre signalement sous **48 heures**
2. **Évaluer la vulnérabilité** et vous donner un retour sous **7 jours**
3. **Développer et tester un correctif** dans les plus brefs délais
4. **Publier un correctif** dès que possible (selon la gravité)
5. **Vous créditer publiquement** dans les notes de version (si vous le souhaitez)
6. **Coordonner la divulgation** avec vous avant toute annonce publique

### 🏆 Reconnaissance

Nous remercions les chercheurs en sécurité qui signalent les vulnérabilités de manière responsable. Avec votre accord, nous vous créditerons dans :

- Le fichier CHANGELOG.md
- Les notes de version
- Un fichier SECURITY_HALL_OF_FAME.md (si vous le souhaitez)

### ⚖️ Divulgation Responsable

Nous suivons les principes de divulgation responsable :

- **Ne divulguez pas** la vulnérabilité publiquement avant qu'un correctif soit disponible
- **Donnez-nous un délai raisonnable** pour corriger le problème (généralement 90 jours)
- **Ne tentez pas d'exploiter** la vulnérabilité au-delà de ce qui est nécessaire pour la démonstration
- **Respectez la vie privée** des utilisateurs et ne accédez/modifiez pas leurs données

---

## 🔒 Pratiques de Sécurité du Projet

### Cryptographie

Notre gestionnaire de mots de passe utilise des standards cryptographiques modernes :

| Composant | Implémentation | Standard |
| ----------- | ---------------- | ---------- |
| **Chiffrement symétrique** | AES-256-GCM | NIST FIPS 197 |
| **Dérivation de clé (KDF)** | PBKDF2-HMAC-SHA256 | NIST SP 800-132 |
| **Itérations KDF** | 600 000 | OWASP 2023+ |
| **Génération aléatoire** | Python `secrets` | Crypto-sûr |
| **Longueur de clé** | 256 bits | État de l'art |
| **Nonce/IV** | Unique par entrée | 96 bits (GCM) |
| **Salt** | Unique par utilisateur | ≥ 128 bits |

### Architecture de Sécurité

- **Séparation des données** : Chaque utilisateur a sa propre base de données SQLite
- **Permissions strictes** : Fichiers en mode 600 (lecture/écriture propriétaire uniquement)
- **Protection anti-brute force** : Maximum 5 tentatives de connexion ratées
- **Validation des mots de passe maîtres** : Critères stricts (longueur, complexité, mots communs)
- **Passphrases sécurisées** : Wordlist de 1053 mots (entropie ~50-60 bits)

### Données Chiffrées vs Non Chiffrées

Pour plus de détails sur le modèle de sécurité, consultez [SECURITY_MODEL.md](SECURITY_MODEL.md).

**Chiffré avec AES-256-GCM** :

- ✅ Mots de passe
- ✅ Notes
- ✅ Champs personnalisés

**Non chiffré** (pour recherche/tri) :

- ⚠️ Titre de l'entrée
- ⚠️ Nom d'utilisateur
- ⚠️ URL
- ⚠️ Catégorie
- ⚠️ Tags
- ⚠️ Métadonnées (dates de création/modification)

**Recommandation** : Ne mettez pas d'informations sensibles dans les champs non chiffrés.

---

## 🔍 Audits de Sécurité

### Audits Internes

Nous effectuons régulièrement des audits internes de sécurité :

- ✅ Analyse statique avec Ruff et Bandit
- ✅ Tests de sécurité automatisés (`test_security_improvements.py`)
- ✅ Revue de code pour chaque modification majeure

### Audits Externes

Nous accueillons favorablement les audits de sécurité externes :

- **Code open source** : Tout le code est disponible pour audit
- **Documentation complète** : Architecture et sécurité documentées
- **Tests reproductibles** : Suite de tests disponible dans `tests/`

---

## 📚 Ressources

### Documentation

- [Architecture](docs/ARCHITECTURE.md) - Vue d'ensemble technique
- [Modèle de Sécurité](SECURITY_MODEL.md) - Détails cryptographiques
- [Protection des Données](docs/DATA_PROTECTION.md) - Mesures de protection
- [Guide Multi-utilisateurs](docs/MULTI_USER_GUIDE.md) - Isolation des données

### Standards de Référence

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [NIST SP 800-63B - Digital Identity Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
- [NIST SP 800-132 - PBKDF Recommendations](https://csrc.nist.gov/publications/detail/sp/800-132/final)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

### Outils de Test de Sécurité

```bash
# Tests de sécurité
./run-security-tests.sh

# Analyse statique
ruff check src/
bandit -r src/

# Tests complets
python -m pytest tests/ -v
```

---

## ⚠️ Limitations Connues

### Par Conception

- **Pas de récupération de mot de passe maître** : La sécurité cryptographique implique qu'un mot de passe maître oublié = données perdues
- **Métadonnées non chiffrées** : Pour permettre recherche et tri (voir SECURITY_MODEL.md)
- **Stockage local uniquement** : Pas de synchronisation cloud (par choix de sécurité)

### En Développement

Consultez [ACTIONS_SECURITE_OPENSOURCE.md](ACTIONS_SECURITE_OPENSOURCE.md) pour les améliorations planifiées :

- Timeout de session automatique
- Vérification Have I Been Pwned (optionnelle)
- Authentification à deux facteurs (2FA)
- Export chiffré

---

## 🔄 Mises à Jour de Sécurité

Les correctifs de sécurité sont publiés :

- **Immédiatement** pour les vulnérabilités critiques
- **Dans les 7 jours** pour les vulnérabilités moyennes
- **Dans les 30 jours** pour les vulnérabilités mineures

Abonnez-vous aux [releases GitHub](https://github.com/[USERNAME]/password-manager/releases) pour être notifié.

---

## 📞 Contact

- **Vulnérabilités de sécurité** : [À CONFIGURER - Email sécurité]
- **Questions générales** : [GitHub Issues](https://github.com/[USERNAME]/password-manager/issues)
- **Discussions** : [GitHub Discussions](https://github.com/[USERNAME]/password-manager/discussions)

---

**Dernière mise à jour** : 2 mars 2026

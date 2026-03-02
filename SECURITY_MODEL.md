# 🔐 Modèle de Sécurité - Password Manager

**Version** : 0.4.0-beta  
**Date** : 2 mars 2026  
**Audience** : Utilisateurs, auditeurs de sécurité, contributeurs

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture cryptographique](#architecture-cryptographique)
3. [Données chiffrées vs non chiffrées](#données-chiffrées-vs-non-chiffrées)
4. [Génération de mots de passe](#génération-de-mots-de-passe)
5. [Menaces et limitations](#menaces-et-limitations)
6. [Bonnes pratiques](#bonnes-pratiques)
7. [FAQ Sécurité](#faq-sécurité)

---

## Vue d'ensemble

Ce gestionnaire de mots de passe utilise une approche **"zero-knowledge"** partielle : vos mots de passe sont chiffrés avec une clé dérivée de votre mot de passe maître, que nous ne stockons jamais en clair.

### Principe de fonctionnement

```text
Mot de passe maître
        ↓
    PBKDF2-HMAC-SHA256 (600 000 itérations)
        ↓
    Clé de chiffrement (256 bits)
        ↓
    AES-256-GCM
        ↓
    Données chiffrées stockées
```

### Garanties de sécurité

✅ **Nous garantissons** :

- Les mots de passe sont chiffrés avec AES-256-GCM (standard militaire)
- La clé de chiffrement dérive du mot de passe maître via PBKDF2 (600 000 itérations)
- Chaque entrée a un nonce unique (pas de réutilisation)
- Impossible de déchiffrer sans le mot de passe maître correct
- Pas de porte dérobée (code open source auditable)

⚠️ **Nous NE garantissons PAS** :

- Protection si votre ordinateur est compromis (keylogger, malware)
- Protection si votre mot de passe maître est faible ou deviné
- Récupération des données si vous oubliez votre mot de passe maître

---

## Architecture cryptographique

### Chiffrement symétrique : AES-256-GCM

**Algorithme** : Advanced Encryption Standard (AES) en mode Galois/Counter Mode (GCM)

**Paramètres** :

- **Taille de clé** : 256 bits (32 octets)
- **Mode** : GCM (Authenticated Encryption with Associated Data - AEAD)
- **Nonce** : 96 bits (12 octets) unique par entrée
- **Tag d'authentification** : 128 bits (détection de modification)

**Avantages** :

- ✅ Standard NIST approuvé (FIPS 197)
- ✅ Authentification intégrée (détecte les modifications)
- ✅ Résistant aux attaques connues
- ✅ Performances excellentes (instructions CPU AES-NI)

**Bibliothèque** : `cryptography` (Python, bindings OpenSSL)

### Dérivation de clé : PBKDF2-HMAC-SHA256

**Algorithme** : Password-Based Key Derivation Function 2 avec HMAC-SHA256

**Paramètres** :

- **Fonction de hachage** : SHA-256
- **Itérations** : 600 000 (conforme OWASP 2023+)
- **Salt** : Unique par utilisateur (128+ bits)
- **Longueur de sortie** : 256 bits (compatible AES-256)

**Objectif** : Rendre les attaques par force brute **extrêmement coûteuses**

**Temps de calcul** :

- Sur CPU moderne (11th Gen Intel i5) : ~200-300ms
- **Attaquant avec GPU** (RTX 4090) : ~10 000 hash/sec
- **Attaquant avec ferme de GPU** : ~1 million hash/sec (coût prohibitif)

**Exemple de résistance** :

```text
Mot de passe : 16 caractères alphanumériques + symboles
Entropie : ~95 bits
Combinaisons : 2^95 ≈ 4×10^28

Attaque avec 1 million hash/sec :
Temps moyen : 2^94 / (10^6 × 3600 × 24 × 365) ≈ 6×10^14 années
```

### Génération aléatoire : Python `secrets`

**Module** : `secrets` (Python 3.6+)

**Source d'entropie** :

- Linux : `/dev/urandom` (CSPRNG du noyau)
- Windows : `CryptGenRandom` (API Windows)
- macOS : `/dev/random`

**Garanties** :

- ✅ Cryptographiquement sûr (CSPRNG)
- ✅ Imprévisible
- ✅ Non déterministe

---

## Données chiffrées vs non chiffrées

### 🔒 Données CHIFFRÉES (confidentielles)

Ces données sont protégées par AES-256-GCM et **ne peuvent pas être lues** sans le mot de passe maître :

| Champ | Description | Exemple |
| ------- | ------------- | --------- |
| **password** | Le mot de passe de l'entrée | `MySecretP@ssw0rd123` |
| **notes** | Notes privées | `Code PIN : 1234` |
| **custom fields** | Champs personnalisés | `Clé API : sk_live_abc123...` |

**Format de stockage** :

```text
base64(nonce || ciphertext || tag)
```

**Impossibilité de déchiffrement sans clé** :

- Sans le mot de passe maître → pas de clé de déchiffrement
- Avec une clé incorrecte → échec d'authentification GCM
- Modification des données → détectée par le tag GCM

### 📂 Données NON CHIFFRÉES (métadonnées fonctionnelles)

Ces données sont stockées **en clair** dans la base de données SQLite :

| Champ | Description | Raison | Sensibilité |
| ------- | ------------- | -------- | ------------- |
| **title** | Titre de l'entrée | Recherche/affichage | ⚠️ Moyenne |
| **username** | Nom d'utilisateur | Recherche/tri | ⚠️ Moyenne |
| **url** | URL du site | Ouverture directe | ⚠️ Faible |
| **category** | Catégorie | Organisation/filtrage | ✅ Faible |
| **tags** | Étiquettes | Recherche avancée | ✅ Faible |
| **favorite** | Marqué favori | Tri/accès rapide | ✅ Négligeable |
| **created_at** | Date de création | Historique | ✅ Négligeable |
| **updated_at** | Date de modification | Dernière activité | ✅ Négligeable |
| **password_age** | Âge du mot de passe | Rappels de changement | ✅ Négligeable |

### ⚖️ Justification technique

**Pourquoi certaines données ne sont-elles pas chiffrées ?**

1. **Performance** : Recherche et tri impossibles sur données chiffrées (nécessiterait déchiffrement de toute la base)
2. **Fonctionnalité** : Affichage de la liste, ouverture d'URL, organisation
3. **Expérience utilisateur** : Recherche instantanée, tri par catégorie, filtres
4. **Compromis sécurité/usabilité** : Standard pour la plupart des gestionnaires de mots de passe

**Alternatives (non implémentées)** :

- **SQLCipher** : Chiffrement de toute la base (performance réduite, recherche limitée)
- **Index chiffrés** : Complexe et impact sur les performances
- **Recherche homomorphique** : Recherche pédagogique actuellement

### 🛡️ Recommandations d'utilisation

**Pour minimiser les risques** :

✅ **FAIRE** :

- Utiliser des titres génériques : `Email principal` au lieu de `Gmail john.doe@example.com`
- Éviter les noms d'utilisateur sensibles dans le champ username
- Utiliser le champ **notes** (chiffré) pour les informations sensibles
- Utiliser des **champs personnalisés** (chiffrés) pour données confidentielles

❌ **NE PAS FAIRE** :

- Mettre des informations confidentielles dans le titre : ❌ `Compte bancaire secret Suisse`
- Utiliser le champ URL pour des informations privées : ❌ `https://monsite.com?code_secret=abc123`
- Mettre des données sensibles dans les catégories/tags : ❌ Tag: `Compte illégal`

### 📊 Évaluation du risque

**Si un attaquant accède physiquement/virtuellement à votre ordinateur et vole le fichier de base de données** :

| Données | Accessible sans mot de passe maître | Risque |
| --------- | ------------------------------------- | -------- |
| Mots de passe | ❌ NON (chiffré AES-256) | ✅ Aucun |
| Notes | ❌ NON (chiffré AES-256) | ✅ Aucun |
| Titres des entrées | ✅ OUI (clair) | ⚠️ Moyen |
| Noms d'utilisateur | ✅ OUI (clair) | ⚠️ Moyen |
| URLs | ✅ OUI (clair) | ⚠️ Faible |
| Nombre d'entrées | ✅ OUI | ⚠️ Faible |

**Conclusion** : Un attaquant pourra voir **quels types de comptes vous avez** (emails, banques, réseaux sociaux), mais **PAS vos mots de passe**.

---

## Génération de mots de passe

### Mots de passe aléatoires

**Paramètres par défaut** :

- Longueur : 20 caractères
- Jeux de caractères : minuscules, majuscules, chiffres, symboles
- Exclusion : caractères ambigus (0, O, l, 1, I)

**Entropie** :

```text
Jeu de caractères : 26 + 26 + 10 + 19 - 5 = 76 caractères
Entropie : log₂(76^20) ≈ 130 bits

Résistance :
- Attaque en ligne (1000 essais/sec) : ~10^30 années
- Attaque offline (10^12 essais/sec) : ~10^18 années
```

**Verdict** : ✅ **Extrêmement sûr**

### Passphrases (phrases de passe)

**Paramètres par défaut** :

- Nombre de mots : 5
- Wordlist : 1053 mots français uniques
- Séparateur : `-`
- Ajout : 2 chiffres aléatoires

**Entropie** :

```text
Entropie de base : log₂(1053^5) ≈ 50 bits
Capitalisation aléatoire : +5 bits (2^5 combinaisons)
Chiffres (00-99) : +6.6 bits (log₂(100))
Total : ~61-62 bits

Résistance :
- Attaque avec dictionnaire (1053 mots) : ~10^15 combinaisons
- Temps (1 million hash/sec) : ~36 années
```

**Exemple** : `maison-Soleil-jardin-Montagne-foret42`

**Verdict** : ✅ **Bon** (suffisant pour la plupart des usages)

**Amélioration future** : Augmenter à 7776 mots (standard EFF Diceware) pour atteindre 77+ bits avec 6 mots.

---

## Menaces et limitations

### ✅ Protection CONTRE

| Menace | Protection |
| -------- | ----------- |
| **Interception réseau** | N/A (stockage local uniquement) |
| **Vol de base de données** | ✅ Mots de passe chiffrés AES-256 |
| **Force brute hors ligne** | ✅ PBKDF2 600k itérations (très lent) |
| **Rainbow tables** | ✅ Salt unique par utilisateur |
| **Modification non détectée** | ✅ Tag d'authentification GCM |
| **Réutilisation de nonce** | ✅ Génération aléatoire pour chaque entrée |
| **Attaque par timing** | ✅ Comparaisons en temps constant |

### ⚠️ Protection LIMITÉE contre

| Menace | Limitation |
| -------- | ------------ |
| **Keylogger** | ⚠️ Capture du mot de passe maître à la saisie |
| **Malware** | ⚠️ Accès mémoire pendant que l'app est déverrouillée |
| **Screen capture** | ⚠️ Capture des mots de passe affichés à l'écran |
| **Shoulder surfing** | ⚠️ Observation directe de la saisie |
| **Cold boot attack** | ⚠️ Lecture de la RAM (si non chiffrée) |
| **Evil maid attack** | ⚠️ Modification du système pendant accès physique |

### ❌ AUCUNE protection contre

| Menace | Explication |
| -------- | ------------- |
| **Mot de passe maître faible** | Si `password123`, attaque par dictionnaire réussira |
| **Mot de passe maître partagé** | Si divulgué, toutes les données sont compromises |
| **Backdoor dans l'OS** | Si le système d'exploitation est compromis |
| **Oubli du mot de passe** | **Récupération impossible** (by design) |

---

## Bonnes pratiques

### 🔐 Mot de passe maître

**FAIRE** ✅ :

- Utiliser **16+ caractères** avec majuscules, minuscules, chiffres et symboles
- OU utiliser une **passphrase de 6+ mots** (ex: `correct-horse-battery-staple-kitchen-purple`)
- Le **mémoriser** (ne PAS le stocker ailleurs)
- Le changer régulièrement (tous les 6-12 mois) si possible
- Utiliser un mot de passe unique (pas réutilisé ailleurs)

**NE PAS FAIRE** ❌ :

- Utiliser un mot commun du dictionnaire : ❌ `motdepasse`
- Réutiliser un mot de passe compromis : ❌ `Gmail2018!`
- Le stocker dans un fichier texte : ❌ `mot_de_passe.txt`
- Le partager avec quiconque

### 🗄️ Stockage des données

**FAIRE** ✅ :

- Garder des **backups chiffrés** réguliers (différentes localisations)
- Utiliser un **système de fichiers chiffré** (LUKS, BitLocker, FileVault)
- Protéger l'accès physique à votre ordinateur
- Verrouiller la session quand vous vous absentez

**NE PAS FAIRE** ❌ :

- Stocker la base sur un cloud non chiffré : ❌ Dropbox non chiffré
- Copier sur clé USB non chiffrée

### 🔑 Génération de mots de passe

**FAIRE** ✅ :

- Utiliser le générateur intégré (cryptographiquement sûr)
- Privilégier 20+ caractères pour les comptes critiques
- Utiliser des passphrases pour les mots de passe à retenir
- Vérifier que le mot de passe généré est accepté par le site cible

**NE PAS FAIRE** ❌ :

- Réduire la longueur à moins de 12 caractères
- Désactiver tous les types de caractères
- Réutiliser un mot de passe généré précédemment

### 🏷️ Organisation

**FAIRE** ✅ :

- Utiliser des titres **génériques et discrets** : `Email 1`, `Banque principale`
- Mettre les informations sensibles dans les **notes chiffrées**
- Utiliser les **catégories** pour organiser (non sensibles)
- Marquer en **favori** les entrées fréquemment utilisées

**NE PAS FAIRE** ❌ :

- Titres trop explicites : ❌ `Compte Bitcoin offshore wallet seed`
- Informations sensibles dans l'URL : ❌ `https://site.com?pin=1234`

---

## FAQ Sécurité

### Q1 : Mes mots de passe sont-ils vraiment sûrs ?

**R :** Oui, **si** :

- ✅ Votre mot de passe maître est fort (16+ caractères ou 6+ mots)
- ✅ Votre ordinateur n'est pas compromis (pas de malware/keylogger)
- ✅ Vous utilisez un système d'exploitation à jour avec patches de sécurité

Les mots de passe sont chiffrés avec AES-256-GCM, le même standard utilisé par les gouvernements et l'armée.

### Q2 : Que se passe-t-il si j'oublie mon mot de passe maître ?

**R :** **Vous perdez TOUTES vos données.** C'est la conséquence de la sécurité cryptographique forte.

**Solutions préventives** :

- Utilisez une passphrase mémorable (6+ mots)
- Écrivez-la sur papier dans un coffre-fort physique
- Partagez-la avec une personne de confiance (testament numérique)

### Q3 : Puis-je synchroniser avec plusieurs appareils ?

**R :** Pas nativement. Le gestionnaire est conçu pour un stockage local sécurisé.

**Solutions** :

- Copier manuellement le fichier de base (chiffré) via clé USB chiffrée
- Utiliser un cloud chiffré côté client (Cryptomator, Veracrypt)
- ⚠️ **Attention** : risques de conflits de versions

### Q4 : Le code est-il auditable ?

**R :** **Oui, 100% open source.**

```bash
# Voir le code de chiffrement
cat src/services/crypto_service.py

# Voir le générateur de mots de passe
cat src/services/password_generator.py

# Exécuter les tests de sécurité
./run-security-tests.sh
```

### Q5 : Y a-t-il une backdoor (porte dérobée) ?

**R :** **Non.** Le code est open source et auditable. Aucune télémétrie, aucune connexion externe, aucun accès distant.

Nous utilisons des bibliothèques standard (`cryptography`, `PyGObject`) elles aussi open source.

### Q6 : Est-ce plus sûr que [Gestionnaire X] ?

**R :** Comparaison avec les principaux gestionnaires :

| Fonctionnalité | Ce Projet | 1Password | Bitwarden | KeePassXC |
| ---------------- | ----------- | ----------- | ----------- | ----------- |
| Chiffrement | AES-256-GCM | AES-256-GCM | AES-256-CBC | AES-256/ChaCha20 |
| KDF | PBKDF2 600k | PBKDF2 650k | PBKDF2 600k | Argon2 |
| Open Source | ✅ | ❌ | ✅ | ✅ |
| Stockage local | ✅ | Optionnel | Optionnel | ✅ |
| Synchronisation | ❌ | ✅ | ✅ | Manuel |
| 2FA | ❌ (prévu) | ✅ | ✅ | ✅ (TOTP) |
| Audit professionnel | ❌ | ✅ | ✅ | ✅ |

**Verdict** : Sécurité cryptographique similaire aux leaders du marché, mais moins de fonctionnalités avancées (sync, 2FA).

### Q7 : Que faire si mon ordinateur est compromis ?

**R :** **Changez TOUS vos mots de passe immédiatement** depuis un ordinateur sain.

1. Déconnectez l'ordinateur compromis d'Internet
2. Utilisez un autre appareil sûr
3. Changez votre mot de passe maître en priorité
4. Changez tous vos mots de passe critiques (email, banque, etc.)
5. Activez la 2FA partout où possible
6. Nettoyez/réinstallez le système compromis

---

## 📚 Références

### Standards appliqués

- **NIST FIPS 197** : Advanced Encryption Standard (AES)
- **NIST SP 800-38D** : Galois/Counter Mode (GCM)
- **NIST SP 800-132** : PBKDF2 Recommendations
- **OWASP ASVS** : Application Security Verification Standard
- **OWASP Password Storage Cheat Sheet**

### Documentation technique

- [Architecture complète](docs/ARCHITECTURE.md)
- [Protection des données](docs/DATA_PROTECTION.md)
- [Actions de sécurité restantes](ACTIONS_SECURITE_OPENSOURCE.md)
- [Politique de sécurité](SECURITY.md)

### Bibliothèques utilisées

- [`cryptography`](https://cryptography.io/) (39.0.0+) - Cryptographie (bindings OpenSSL)
- [`secrets`](https://docs.python.org/3/library/secrets.html) - Génération aléatoire sécurisée
- [`sqlite3`](https://docs.python.org/3/library/sqlite3.html) - Stockage base de données

---

## ✅ Conclusion

Ce gestionnaire de mots de passe offre une **sécurité cryptographique de niveau professionnel** comparable aux solutions commerciales leaders.

**Points forts** :

- ✅ Chiffrement AES-256-GCM (état de l'art)
- ✅ KDF robuste (PBKDF2 600k itérations)
- ✅ Code open source auditable
- ✅ Pas de télémétrie, pas de cloud
- ✅ Stockage local sous votre contrôle

**Limitations à accepter** :

- ⚠️ Métadonnées non chiffrées (nécessaire pour la recherche/tri)
- ⚠️ Pas de synchronisation automatique
- ⚠️ Récupération impossible si mot de passe oublié
- ⚠️ Dépend de la sécurité du système d'exploitation

**Utilisez-le si** :

- ✅ Vous privilégiez la sécurité et le contrôle total
- ✅ Vous n'avez pas besoin de sync multi-appareils
- ✅ Vous comprenez et acceptez les compromis
- ✅ Vous voulez un gestionnaire open source auditable

**N'utilisez pas si** :

- ❌ Vous avez besoin de synchronisation transparente
- ❌ Vous pourriez oublier votre mot de passe maître
- ❌ Vous avez un système compromis/non sécurisé

---

**Document maintenu par** : Les contributeurs du projet  
**Dernière révision** : 2 mars 2026  
**Version du logiciel** : 0.4.0-beta

# Journal des modifications — HeelonVault

Langue: FR | [EN](CHANGELOG.en.md)

Toutes les modifications notables sont documentées ici, par version décroissante.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/).

---

## [1.0.0] — 2026-04-02

### Release stable

- Passage officiel en **1.0.0** (sortie stable), suppression du suffixe beta dans la version applicative et la documentation de référence.

### Rapport d'audit PDF

- En-tête premium visuel simplifié: suppression de l'encadré or.
- Nouveau titre principal en noir: **REGISTRE DE TRAÇABILITÉ DES ACCÈS**.
- Journal d'audit exporté sous forme de tableau exploitable (date, action, acteur, cible, détail).

### Traçabilité et lisibilité

- Résolution des identités acteur par nom d'affichage / nom utilisateur dans les exports.
- Enrichissement des cibles d'audit avec noms de coffre et titres de secrets quand disponibles.
- Enrichissement de l'événement `secret.created` avec le titre du secret dans le détail d'audit.

## [0.9.4-beta] — 2026-04-01

### Licence

- Passage de la licence Source-Available propriétaire à **Apache 2.0** : utilisation, modification et redistribution libres ; copyright et marque HEELONYS conservés.

### Système de licence applicative (LicenseService)

- Vérification Ed25519 des licences signées (fichier `~/.config/heelonvault/license.hvl` en dev, `/etc/heelonvault/license.hvl` en prod).
- Format JSON avec champ `payload` (objet JSON ou chaîne sérialisée) et `signature` (hex 128 car. ou base64).
- Fallback automatique sur licence **Community** si aucun fichier n'est présent ou si la vérification échoue.
- Tolérance automatique des espaces et du préfixe `0x` dans les valeurs hexadécimales (`sanitize_hex_input`).
- Journalisation audit `LicenseCheckSuccess` / `LicenseCheckFailure` au démarrage de l'application.

### Badges de licence en interface

- Badge **"Licence free"** / **"Licence pro — CLIENT"** sur la page de login (section hero), visible avant toute authentification.
- Badge de licence dans le bandeau d'en-tête de la fenêtre principale (à côté du badge BETA).
- Style CSS haute-visibilité `.login-license-badge` (dégradé vert sarcelle).
- Clés i18n `license-status-community`, `license-status-professional`, `license-status-invalid` ajoutées en FR/EN.

---

## [0.9.3-beta] — 2026-03-31

### Tableau de bord de sécurité

- Fenêtre de tableau de bord sécurité rendue via WebKitGTK (WebView-first, sans fallback GTK).
- Score de coffre global calculé en temps réel avec évaluation `zxcvbn`.
- Traductions dédiées en FR et EN pour tous les labels du tableau de bord.

### Historique de connexion

- Enregistrement de chaque connexion réussie dans la table `login_history` (migration 0007).
- Affichage de l'historique dans la vue `Profil & Sécurité`.

### Activation TOTP 2FA

- Activation guidée via QR-code dans `Profil & Sécurité`.
- Vérification obligatoire du premier code avant activation définitive.
- Secret TOTP chiffré en base (migration 0009).

### Corrections et robustesse

- Restauration de secret depuis la corbeille : transaction atomique avec restauration automatique du coffre parent si nécessaire (évite l'état "secret invisible").
- Résolution du coffre dans le dialogue d'édition des secrets multi-coffres.
- Correction de la persistance de l'enveloppe de mot de passe au rechargement.

---

## [0.9.2-beta] — 2026-03-27

### Internationalisation et UX

- Sélecteur de langue de login remplacé par des drapeaux FR/EN.
- Correction d'un gel UI lors des changements de langue sur l'écran de login.
- Harmonisation du rafraîchissement i18n dans les zones globales de la fenêtre principale (sidebar, tooltips, placeholders, titres de vues).
- Persistance et application à chaud de la langue utilisateur dans `Profil & Sécurité`.

### Installation, CI/CD et fiabilité release

- Installateur renforcé avec vérification explicite des artefacts critiques (`run.sh`, entrées desktop).
- Installation de deux entrées desktop (`com.heelonvault.rust.desktop` et `heelonvault.desktop`) pour compatibilité environnementale.
- Smoke test installateur ajouté au workflow de release.
- Pipeline CI dédié (`.github/workflows/ci.yml`) : format, lint, build, compilation des tests, validation desktop, smoke test.

### Bootstrap, clé de récupération et sauvegarde sécurisée

- Assistant d'initialisation en 3 étapes dans le dialogue de login : identité → serment (phrase 24 mots) → en attente.
- Phrase mnémotechnique 24 mots (style BIP39) générée à l'initialisation via `BackupService::generate_recovery_key()`.
- Vérification obligatoire de 2 mots tirés au sort avant validation.
- Copie presse-papier avec effacement automatique après 60 secondes.
- Ré-export de la clé de récupération depuis `Profil & Sécurité` pour tout administrateur.
- `BackupApplicationService` : contrôle d'accès RBAC sur les exports/imports `.hvb`.
- Journal d'audit introduit (table `audit_log`, migration 0013).

### Partage équipe, RBAC et UX admin

- Correction du partage de coffre vers une équipe : dérivation de la clé membre depuis `password_envelope` si la clé explicite n'est pas fournie.
- Protection anti faux-positif : échec explicite si aucun membre n'a reçu de clé de coffre.
- Sélecteur explicite de coffre dans le dialogue de partage (plus d'ambiguïté sur la cible).
- Badge ADMIN dans l'en-tête à côté de l'identité connectée.
- Affichage de l'état "coffre partagé" pour les coffres propriétaires.
- Normalisation des labels de badges FR en majuscules.
- Nettoyage i18n : suppression de la clé obsolète `main-vault-shared-badge`.

### Documentation bilingue

- Couverture FR/EN sur l'ensemble des documents Markdown opérationnels.
- Index central de documentation bilingue dans `docs/README.md`.

---

## [0.9.1-beta] — 2026-03-01

### Architecture initiale Rust

- Migration complète de l'architecture Python vers Rust (GTK4 + libadwaita).
- Couche service/repository/model en Rust avec `sqlx` et 9 migrations initiales.
- Authentification Argon2id, chiffrement AES-256-GCM, TOTP RFC 6238.
- Multi-utilisateur avec coffres isolés par utilisateur.
- Recherche multi-champs avec normalisation Unicode.
- Logs structurés JSON rotatifs via `tracing`.
- Politique Clippy sécurité (`clippy.toml`) interdisant `unwrap()`/`expect()` sur les chemins sensibles.

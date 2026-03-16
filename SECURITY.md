# Politique de Securite

## Versions supportees

Nous fournissons des correctifs de securite pour les versions suivantes :

| Version | Support |
| ------- | ------- |
| 0.4.x   | Oui     |
| 0.3.x   | Limite  |
| < 0.3   | Non     |

## Signaler une vulnerabilite

Ne creez pas d'issue publique pour une vulnerabilite de securite.

- Contact securite : `security@heelonys.fr`
- Merci d'inclure : description, etapes de reproduction, impact, version, environnement, preuve de concept et suggestions de correction.

### Engagement de reponse

1. Accuse de reception sous 48 heures.
2. Premier retour d'evaluation sous 7 jours.
3. Correctif selon severite (coordination de divulgation responsable).

## Etat actuel de la securite (mars 2026)

### Refonte cryptographique complete

La couche cryptographique a ete refondue autour de primitives modernes et d'une gestion des secrets plus stricte.

| Domaine | Implementation actuelle |
| ------- | ----------------------- |
| Chiffrement des secrets coffre | AES-256-GCM (nonce 96 bits unique par entree) |
| KDF coffre | PBKDF2-HMAC-SHA256, 600 000 iterations |
| Longueur de cle | 256 bits |
| Salt coffre | 32 bytes (min accepte 16 bytes) |
| Hash mots de passe utilisateurs | PBKDF2-HMAC-SHA256, 600 000 iterations, salt 32 bytes |
| Confidentialite des emails | HMAC-SHA256 + pepper local (`.email_pepper`) |
| Chiffrement secrets TOTP | AES-GCM avec cle systeme derivee (PBKDF2-SHA256, 100 000 iterations) |
| Codes de secours 2FA | HMAC-SHA256 (pas de stockage en clair) |
| Aleatoire cryptographique | Aleatoire systeme securise |

Points techniques importants :

- `CryptoService` utilise AES-GCM avec authentification integree (detection d'alteration).
- Les erreurs de dechiffrement sont normalisees (`invalid key or corrupted/tampered data`) pour limiter les fuites d'information.
- `CryptoService.clear()` effectue un effacement memoire best-effort de la cle en fin de session.

### Authentification et controle d'acces

- Authentification principale par email (avec hash HMAC + pepper cote stockage).
- Compatibilite legacy : connexion possible via username si necessaire.
- 2FA TOTP obligatoire dans le flux applicatif :
  - utilisateur sans 2FA configure : setup impose,
  - utilisateur 2FA actif : verification TOTP obligatoire avant ouverture du coffre.
- Roles : `user` et `admin` (gestion utilisateurs/sauvegardes reservee admin).

### Protection anti brute-force

Protection combinee :

- Delai artificiel cote auth : 1.5 s sur echec d'authentification.
- Delai progressif par identifiant : 1s, 2s, 4s, ... jusqu'a 32s.
- Verrouillage temporaire : 15 minutes apres 5 echecs.
- Rate limiting global anti-enumeration :
  - 5 tentatives/minute,
  - 30 tentatives/heure.
- Persistance de l'etat anti-bruteforce en local (`.login_attempts.json`, permissions `600`).

### Isolation des donnees

- Un espace de travail chiffre par utilisateur (`workspace_uuid`).
- Fichiers principaux :
  - `users.db` (metadonnees/auth),
  - `passwords_<workspace_uuid>.db`,
  - `salt_<workspace_uuid>.bin`.
- Permissions renforcees sur fichiers sensibles (`600`) appliquees au demarrage.

### Donnees chiffrees vs non chiffrees

Chiffrees (AES-256-GCM) :

- mots de passe,
- notes sensibles,
- secrets TOTP (cote service 2FA).

Non chiffrees (necessaires pour UX/recherche/tri) :

- titre,
- username de l'entree,
- URL,
- categorie,
- tags,
- metadonnees temporelles.

Recommandation : ne pas stocker de donnees confidentielles dans les champs non chiffres.

### Import / export

- Export CSV standard : en clair (a manipuler avec prudence).
- Export ZIP chiffre disponible (`pyzipper`, AES).
- Import CSV : controles de format et validation minimale, mais les donnees source restent de responsabilite utilisateur.

## Audits et tests

- Tests securite : executez les suites Rust sous `rust/tests/` via `cargo test`
- Revue de code systematique sur les changements sensibles (auth, crypto, stockage).
- Journalisation des evenements de securite sans exposition de secrets.

## 🐧 Compatible Red Hat/Fedora

- **Conteneurs** : UBI9/10 Podman-ready
- **Licences** : SPDX-compliant (REUSE lint ✅)
- **SBOM** : Généré avec Syft pour UBI
- **Partner** : Heelonys (Red Hat Partner)

## Limitations connues

- Pas de recuperation du mot de passe maitre (par conception).
- Certaines metadonnees restent en clair pour la recherche et l'ergonomie.
- Application orientee stockage local (pas de synchronisation cloud native).

## Ressources

- `docs/SECURITY.md`
- `docs/DATA_PROTECTION.md`
- `docs/ARCHITECTURE.md`
- `docs/MULTI_USER_GUIDE.md`

Standards utiles :

- OWASP Password Storage Cheat Sheet
- NIST SP 800-63B
- NIST SP 800-132

## Divulgation responsable

Merci de ne pas divulguer publiquement une faille avant disponibilite du correctif et coordination avec l'equipe securite.

---

Derniere mise a jour : 5 mars 2026

# HeelonVault — Secret Manager Evolution Spec v2

> Révision : adaptation Python 3.14, architecture CE/EE, stockage hybride blob, hygiène mémoire renforcée.

---

## 1. Objectif

Transformer HeelonVault d'un password manager en un **personal & professional secret manager** supportant :

- SSH key management
- API token storage
- Sensitive document storage

Ce spec est orienté implémentation pour la prochaine session de développement.

---

## 2. Périmètre

### In scope (Phase 1–3) — Community Edition (CE)

- Nouveaux types de secrets dans le modèle de données et l'UI
- Stockage sécurisé et récupération pour chaque type
- Migration depuis le schéma password-only existant
- Expérience liste/détail type-aware
- Contrôles de sécurité alignés sur le modèle de chiffrement existant

### Out of scope maintenant — réservé Enterprise Edition (EE)

- Cloud sync
- Team sharing et RBAC avancé au-delà des rôles locaux existants
- Intégration HSM
- Hardware-backed key storage APIs
- Audit logs avancés avec export SIEM
- SSO / SAML

### Règle CE/EE

> Tout le code de ce spec appartient au module `heelonvault.core` (CE, licence open source).
> Les features EE seront dans `heelonvault.ee` (module séparé, non inclus dans le repo public).
> Aucun hook EE ne doit être hardcodé dans `core` — utiliser des points d'extension (plugin interface ou event bus interne).

---

## 3. Modèle produit

Introduire une abstraction unifiée `SecretItem` avec des payloads typés.

### Types de secrets

| Valeur            | Description                          | Phase   |
| ----------------- | ------------------------------------ | ------- |
| password          | Mot de passe (existant)              | —       |
| api_token         | Token d'API                          | 1       |
| ssh_key           | Clé SSH (paire publique/privée)      | 2       |
| secure_document   | Document chiffré binaire             | 3       |

### Principes

- Un vault peut contenir tous les types de secrets
- Les métadonnées restent indexables et interrogeables
- Les payloads sensibles sont toujours chiffrés au repos
- Le comportement UI est type-spécifique mais stocké sous un modèle de domaine unifié
- La frontière CE/EE est tracée au niveau module, pas au niveau feature flag

---

## 4. Modèle de données

### 4.1 Contraintes existantes

- L'application stocke les entrées password dans des bases SQLite par vault
- Le chiffrement est géré par `CryptoService` + `PasswordService`

### 4.2 Additions de schéma proposées

#### Stratégie de cohabitation

Conserver la table `passwords` existante intacte. Ajouter une nouvelle table générique `secret_items` pour les types non-password en Phase 1. La convergence vers une table unifiée est reportée à une v2 post-stabilisation.

#### Table cible : `secret_items`

```sql
CREATE TABLE IF NOT EXISTS secret_items (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  secret_type   TEXT    NOT NULL CHECK (secret_type IN ('api_token', 'ssh_key', 'secure_document')),
  title         TEXT    NOT NULL,
  metadata_json TEXT    NOT NULL DEFAULT '{}',
  -- Pour api_token et ssh_key : secret_blob contient le payload chiffré inline
  -- Pour secure_document      : secret_blob contient l'envelope chiffrée + référence au fichier externe
  secret_blob   BLOB    NOT NULL,
  blob_storage  TEXT    NOT NULL DEFAULT 'inline' CHECK (blob_storage IN ('inline', 'file')),
  tags          TEXT    NOT NULL DEFAULT '[]',  -- JSON array sérialisé
  expires_at    TEXT,                           -- ISO 8601
  created_at    TEXT    NOT NULL,
  modified_at   TEXT    NOT NULL,
  usage_count   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_secret_items_type    ON secret_items(secret_type);
CREATE INDEX IF NOT EXISTS idx_secret_items_title   ON secret_items(title);
CREATE INDEX IF NOT EXISTS idx_secret_items_expires ON secret_items(expires_at);
CREATE INDEX IF NOT EXISTS idx_secret_items_tags    ON secret_items(tags);  -- FTS possible en v2
```

#### Colonne `blob_storage`

Introduite dès Phase 1 pour éviter une migration cassante en Phase 3 :

- `'inline'` → `secret_blob` contient le payload chiffré complet (api_token, ssh_key)
- `'file'`   → `secret_blob` contient une envelope JSON chiffrée avec la référence au fichier binaire externe (secure_document)

#### `tags` — format

JSON array sérialisé : `'["work", "production", "aws"]'`. Parsing côté service uniquement.

---

### 4.3 Métadonnées JSON par type

Chaque type a un `TypedDict` Python dédié (validé avant sérialisation) :

#### `api_token`

```python
class ApiTokenMetadata(TypedDict):
    provider:      str          # "aws", "github", "stripe", ...
    environment:   Literal["dev", "staging", "prod", "other"]
    scopes:        list[str]
    token_hint:    str          # derniers caractères masqués ex: "****Xk9p"
    expiration_warning_days: NotRequired[int]  # défaut: 30
```

#### `ssh_key`

```python
class SshKeyMetadata(TypedDict):
    algorithm:          Literal["ed25519", "rsa", "ecdsa", "dsa"]
    fingerprint:        str   # SHA256:...
    public_key_preview: str   # premiers + derniers caractères
    has_passphrase:     bool
    comment:            NotRequired[str]
    key_size:           NotRequired[int]  # pour RSA/ECDSA
```

#### `secure_document`

```python
class SecureDocumentMetadata(TypedDict):
    filename:   str
    mime_type:  str
    size_bytes: int
    sha256:     str   # intégrité du fichier avant chiffrement
    blob_path:  str   # chemin relatif depuis vault_blobs_root
```

---

### 4.4 Stockage des blobs de documents

```text
src/data/blobs/<vault_uuid>/<item_uuid>.bin
```

- `item_uuid` : UUID v4 généré à la création (indépendant de l'`id` SQLite auto-increment)
- **Écriture atomique** : écrire dans un `.tmp`, valider le SHA-256, puis `rename()` (atomique sur Linux/ext4/btrfs)
- **SELinux (Fedora)** : le répertoire `blobs/` doit avoir le contexte `svirt_sandbox_file_t` ou équivalent applicatif. Documenter dans le README d'installation.
- `secret_blob` en DB stocke l'envelope chiffrée (metadata + référence), jamais le corps binaire complet

---

## 5. Stratégie de migration

### 5.1 Versioning

- Ajouter un marqueur de version de schéma dans une table `db_metadata` (créée si absente)
- Incrémenter la version lors de l'introduction de `secret_items`

```sql
CREATE TABLE IF NOT EXISTS db_metadata (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- Valeur initiale si absente : schema_version = '1'
-- Après migration Phase 1   : schema_version = '2'
```

### 5.2 Étapes de migration

1. Détecter l'absence de `secret_items` ou `schema_version < 2`
2. Déclencher le backup via le service de backup existant
3. Créer la table `secret_items`, les indexes, et `db_metadata`
4. Laisser les entrées `passwords` existantes intactes
5. Marquer `schema_version = '2'`
6. Logger le succès ou l'échec (sans payloads sensibles)

### 5.3 Rollback

- En cas d'échec : annuler le démarrage du vault concerné avec une erreur user-friendly
- Le backup pré-migration permet une restauration manuelle
- Ne pas tenter de rollback automatique de schéma (risque de corruption)

---

## 6. Couche service

### 6.1 Nouveaux modèles de domaine

**`src/models/secret_item.py`** — Python 3.14, slots pour hygiène mémoire :

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass(slots=True)
class SecretItem:
    secret_type:  str
    title:        str
    metadata:     dict[str, Any]
    payload:      str | bytes        # toujours chiffré en transit vers/depuis le repository
    tags:         list[str]          = field(default_factory=list)
    blob_storage: str                = 'inline'
    expires_at:   datetime | None   = None
    created_at:   datetime | None   = None
    modified_at:  datetime | None   = None
    usage_count:  int                = 0
    id:           int | None        = None
    item_uuid:    str | None        = None  # UUID v4, stable pour blob_path
```

> **Note `slots=True`** : interdit l'ajout d'attributs dynamiques, réduit l'empreinte mémoire, facilite le zeroing des payloads en mémoire lors du panic lock.

**`src/models/secret_types.py`** — constantes et TypedDicts :

```python
from typing import Literal, TypedDict, NotRequired

SECRET_TYPE_API_TOKEN        = "api_token"
SECRET_TYPE_SSH_KEY          = "ssh_key"
SECRET_TYPE_SECURE_DOCUMENT  = "secure_document"
SECRET_TYPE_PASSWORD         = "password"

ALL_NEW_SECRET_TYPES = frozenset({SECRET_TYPE_API_TOKEN, SECRET_TYPE_SSH_KEY, SECRET_TYPE_SECURE_DOCUMENT})
```

---

### 6.2 Repository

**`src/repositories/secret_repository.py`**

```python
class SecretRepository:
    def list_items(
        self,
        secret_type: str | None = None,
        search_text: str | None = None,
        tag_filter:  list[str] | None = None,
        expired_only: bool = False,
    ) -> list[SecretItem]: ...

    def get_item(self, item_id: int) -> SecretItem | None: ...
    def get_item_by_uuid(self, item_uuid: str) -> SecretItem | None: ...
    def create_item(self, item: SecretItem) -> SecretItem: ...
    def update_item(self, item: SecretItem) -> SecretItem: ...
    def delete_item(self, item_id: int) -> bool: ...
    def record_usage(self, item_id: int, amount: int = 1) -> None: ...
```

---

### 6.3 Service

**`src/services/secret_service.py`**

Responsabilités :

- Valider la structure du payload spécifique au type via les `TypedDict`
- Chiffrer/déchiffrer le payload via le `CryptoService` existant
- Normaliser les champs de métadonnées
- Appliquer les politiques de sécurité pour export/reveal/copy
- Gérer le stockage hybride inline/file

```python
class SecretService:
    # API Tokens
    def create_api_token(self, title: str, token: str, metadata: ApiTokenMetadata) -> SecretItem: ...
    def reveal_api_token(self, item_id: int) -> str: ...  # déchiffre en mémoire, durée limitée

    # SSH Keys
    def create_ssh_key(self, title: str, private_key: str, public_key: str, metadata: SshKeyMetadata) -> SecretItem: ...
    def import_ssh_key_from_file(self, path: pathlib.Path, passphrase: str | None = None) -> SecretItem: ...
    def export_ssh_key(self, item_id: int, dest_path: pathlib.Path) -> None: ...

    # Secure Documents
    def import_document(self, title: str, source_path: pathlib.Path) -> SecretItem: ...
    def export_document(self, item_id: int, dest_path: pathlib.Path) -> None: ...

    # Commun
    def delete_secret(self, item_id: int) -> None: ...  # inclut suppression blob fichier si applicable
    def get_expiring_soon(self, days: int = 30) -> list[SecretItem]: ...
```

---

## 7. UI/UX

### 7.1 Navigation

Étendre la navigation gauche avec un groupe filtre `Secrets` :

- Tous
- Mots de passe
- Clés SSH
- Tokens API
- Documents

Défaut : `Tous`.

### 7.2 Rendu des cartes de liste

Variantes de cartes par `secret_type` :

- **Password** : comportement actuel inchangé
- **SSH Key** : algorithme + fingerprint + badge passphrase
- **API Token** : provider + env + badge expiration + badge scopes
- **Document** : nom de fichier + taille + mime type + badge intégrité

### 7.3 Variantes du panneau de détail

Basculer le formulaire du panneau droit selon le type sélectionné.

#### Formulaire SSH Key

- Titre
- Algorithme (sélecteur)
- Clé privée (masquée / reveal temporisé)
- Clé publique (copiable)
- Commentaire
- Passphrase présente (checkbox read-only)

#### Formulaire API Token

- Titre
- Provider
- Valeur du token (masquée / reveal temporisé)
- Scopes (tags)
- Environnement
- Expiration (date picker)

#### Formulaire Secure Document

- Titre
- File picker / import
- Résumé métadonnées (taille, mime, SHA-256 tronqué)
- Actions : Export, Reveal (aperçu si texte), Supprimer

### 7.4 Interactions premium

- **Copy avec timer d'auto-effacement** pour tokens et clés (cohérent avec comportement password existant)
- **Reveal temporisé avec remasquage** — configurable (défaut : 30 secondes)
- **Panic behavior uniforme** sur tous les types de secrets
- **Badges visuels** : expiration (< 30j = orange, expiré = rouge) et niveau de risque

---

## 8. Exigences de sécurité

### 8.1 Données au repos

- Tous les payloads secrets chiffrés via le flux master-key existant
- Aucun contenu brut (token, clé, document) dans les logs
- Les blobs de documents chiffrés avant écriture disque
- Écriture atomique pour les fichiers blobs (write → validate SHA-256 → rename)

### 8.2 Hygiène mémoire (best effort)

- Utiliser `@dataclass(slots=True)` pour permettre le zeroing des champs payload
- Réutiliser le chemin panic purge pour les nouveaux holders de payloads
- Vider les buffers UI lors du changement d'item ou de type
- Comportement de nettoyage clipboard cohérent sur tous les types
- Ne pas logguer les traceback incluant des valeurs de payload

### 8.3 SELinux (Fedora)

- Documenter les permissions requises sur `src/data/blobs/` dans `INSTALL.md`
- Tester sur un profil SELinux enforcing avant chaque release
- Ajouter un check au démarrage : si le répertoire blobs n'est pas accessible, logger un avertissement clair

### 8.4 Contrôles opérationnels

- **Soft Lock** : logout et retour à l'écran d'auth
- **Panic Lock** : best-effort purge mémoire + quit applicatif (tous types de secrets)

---

## 9. Contrats API et fichiers

### 9.1 Contrats de service internes

```python
SecretService.create_api_token(title, token, metadata) -> SecretItem
SecretService.create_ssh_key(title, private_key, public_key, metadata) -> SecretItem
SecretService.import_document(title, source_path) -> SecretItem
SecretService.export_document(item_id, dest_path) -> None
SecretService.reveal_api_token(item_id) -> str          # payload déchiffré, usage unique
SecretService.import_ssh_key_from_file(path, passphrase) -> SecretItem
SecretService.export_ssh_key(item_id, dest_path) -> None
SecretService.get_expiring_soon(days) -> list[SecretItem]
SecretService.delete_secret(item_id) -> None
```

### 9.2 Contrat filesystem pour les documents

- Chemin blob dérivé du vault UUID et de l'item UUID
- Pattern d'écriture atomique : `.tmp` → vérification SHA-256 → `rename()`
- Vérification d'intégrité SHA-256 à la lecture
- Nettoyage des fichiers orphelins (item supprimé sans blob supprimé) : tâche de maintenance optionnelle

---

## 10. Plan d'implémentation

### Phase 1 : API Tokens (valeur rapide)

1. Ajouter la table `secret_items` (avec `blob_storage`), `db_metadata`, et la migration
2. Ajouter le repository + squelette de service
3. Ajouter les `TypedDict` pour `ApiTokenMetadata`
4. Ajouter le type API token dans la liste et le panneau de détail
5. Ajouter les chaînes i18n (fr/de/it/en) et les tests

### Phase 2 : SSH Keys

1. Ajouter les `TypedDict` pour `SshKeyMetadata` et les formulaires
2. Ajouter l'import de clé depuis fichier + export sécurisé
3. Ajouter les helpers fingerprint et validation de format
4. Décision à prendre : **import-only en Phase 2** (génération in-app reportée à Phase 2.1)

### Phase 3 : Secure Documents

1. Activer `blob_storage = 'file'` et le chemin de stockage chiffré + hash d'intégrité
2. Ajouter les flux import/export et l'affichage métadonnées
3. Ajouter les garde-fous fichiers volumineux (limite configurable, défaut : **25 Mo**)
4. Tester les permissions SELinux sur Fedora

---

## 11. Stratégie de tests

### 11.1 Tests unitaires

- `test_secret_repository.py` — CRUD + filtres + usage_count
- `test_secret_service.py` — validation metadata, encrypt/decrypt, politiques de sécurité
- `test_document_encryption.py` — écriture atomique, intégrité SHA-256, rollback si hash invalide
- `test_ssh_metadata_parsing.py` — parsing fingerprint, algorithme, détection passphrase
- `test_migration.py` — migration depuis DB v1 (password-only) vers v2 (mixed)

### 11.2 Tests d'intégration

- Migration depuis DB password-only vers DB mixed-secrets
- Flux CRUD complets pour chaque nouveau type
- Comportement Panic / Soft Lock avec secrets chargés en mémoire

### 11.3 Tests de régression sécurité

- Aucun secret en clair dans les logs (analyse des outputs de log)
- Auto-clear clipboard pour copy token/clé
- Fichier document chiffré : absence de patterns plaintext dans le binaire
- Vérification que `slots=True` empêche bien l'injection d'attributs dynamiques sur `SecretItem`

---

## 12. Critères d'acceptance

- L'utilisateur peut créer / lire / mettre à jour / supprimer des API tokens
- L'utilisateur peut créer / importer / stocker des clés SSH avec clé privée chiffrée
- L'utilisateur peut importer et exporter des documents sécurisés chiffrés
- Le Panic et le Soft Lock fonctionnent de manière cohérente sur tous les types de secrets
- Les workflows password existants restent pleinement fonctionnels
- Les chaînes fr/de/it/en sont disponibles pour tous les nouveaux éléments UI
- Les migrations réussissent sur une DB Fedora avec SELinux enforcing
- Aucun payload sensible n'apparaît dans les logs ni dans les tracebacks

---

## 13. Décisions ouvertes — avec recommandations par défaut

| # | Question | Recommandation par défaut | Deadline |
| --- | ---------- | -------------------------- | ---------- |
| 1 | Garder la table `passwords` legacy long terme ou converger en v2 ? | **Converger en v2** post-stabilisation Phase 3. Pas de dette technique urgente. | Post-Phase 3 |
| 2 | Taille max document Phase 3 initiale ? | **25 Mo** — couvre la majorité des usages (PDF, certificats, archives légères) sans complexifier la gestion mémoire | Avant Phase 3 |
| 3 | Génération SSH in-app en Phase 2 ou import-only d'abord ? | **Import-only Phase 2**, génération in-app en Phase 2.1 — réduit la surface d'attaque au démarrage | Avant Phase 2 |

---

## 14. Découpage tâches Day-1

1. Créer la migration (`schema_version`, table `secret_items` avec `blob_storage`, indexes)
2. Créer le squelette repository `SecretRepository` + les `TypedDict` métadonnées
3. Créer `SecretItem` dataclass avec `slots=True` et `SecretService` API minimale
4. Ajouter le filtre type UI et le formulaire de détail API token
5. Ajouter les tests : migration + CRUD API token
6. Ajouter les entrées i18n et compiler pour toutes les locales

---

## 15. Architecture CE/EE — rappel

```text
heelonvault/
├── core/          ← CE, open source (tout ce spec)
│   ├── models/
│   ├── repositories/
│   ├── services/
│   └── ui/
└── ee/            ← EE, repo privé, ne pas référencer depuis core/
    ├── sync/
    ├── rbac/
    ├── audit/
    └── hsm/
```

Le module `core` ne doit contenir **aucune** référence directe à `ee`. Les points d'extension (hooks, event bus) sont définis dans `core` mais leur implémentation EE est injectée au démarrage.

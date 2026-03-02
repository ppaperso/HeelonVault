#!/usr/bin/env python3
"""Script de migration vers le système Email + TOTP + UUID.

Ce script migre l'ancien système basé sur username vers le nouveau système
avec authentification par email et 2FA obligatoire.

Opérations effectuées :
1. Backup complet de users.db
2. Ajout des nouvelles colonnes (email, email_hash, workspace_uuid, etc.)
3. Génération d'UUIDs pour chaque utilisateur
4. Renommage des fichiers passwords_*.db et salt_*.bin
5. Validation de la migration

IMPORTANT : Ce script doit être exécuté dans le venv du projet.
"""

import hashlib
import hmac
import logging
import secrets
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Exception levée en cas d'erreur de migration."""
    pass


class EmailTOTPMigration:
    """Gestionnaire de migration vers Email + TOTP + UUID."""

    MIGRATION_NAME = "email_totp_uuid_v1"

    def __init__(self, data_dir: Path, auto_backup: bool = True):
        """Initialise le gestionnaire de migration.

        Args:
            data_dir: Répertoire contenant les données (users.db, passwords_*.db, etc.)
            auto_backup: Si True, crée un backup avant migration
        """
        self.data_dir = Path(data_dir)
        self.users_db = self.data_dir / "users.db"
        self.auto_backup = auto_backup
        self.backup_dir: Path | None = None

        # Charger ou générer le pepper pour HMAC
        self._email_pepper = self._get_or_create_email_pepper()

        if not self.users_db.exists():
            raise MigrationError(f"❌ Base de données introuvable : {self.users_db}")

        logger.info(f"Migration initialisée pour : {self.data_dir}")

    def _get_or_create_email_pepper(self) -> bytes:
        """Récupère ou crée le pepper pour le hachage HMAC des emails.

        Returns:
            Pepper de 32 bytes
        """
        pepper_file = self.data_dir / ".email_pepper"

        if pepper_file.exists():
            pepper = pepper_file.read_bytes()
            logger.debug("Pepper email existant chargé")
        else:
            pepper = secrets.token_bytes(32)
            pepper_file.write_bytes(pepper)
            pepper_file.chmod(0o600)
            logger.info("Pepper email créé avec permissions 600")

        return pepper

    def hash_email(self, email: str) -> str:
        """Hash un email avec HMAC-SHA256 et pepper.

        Protection contre les attaques par dictionnaire sur users.db.

        Args:
            email: Email en clair

        Returns:
            Hash HMAC-SHA256 en hexadécimal
        """
        email_hash = hmac.new(
            self._email_pepper,
            email.lower().encode(),
            hashlib.sha256
        ).hexdigest()
        return email_hash

    def create_backup(self) -> Path:
        """Crée un backup complet avant migration.

        Returns:
            Chemin du répertoire de backup

        Raises:
            MigrationError: Si le backup échoue
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.data_dir / f"backup_pre_migration_{timestamp}"

        try:
            backup_dir.mkdir(parents=True, exist_ok=False)

            # Copier users.db
            shutil.copy2(self.users_db, backup_dir / "users.db")
            logger.info("✅ users.db sauvegardé")

            # Copier tous les passwords_*.db
            password_dbs = list(self.data_dir.glob("passwords_*.db"))
            for db_file in password_dbs:
                shutil.copy2(db_file, backup_dir / db_file.name)
            logger.info(f"✅ {len(password_dbs)} fichiers passwords_*.db sauvegardés")

            # Copier tous les salt_*.bin
            salt_files = list(self.data_dir.glob("salt_*.bin"))
            for salt_file in salt_files:
                shutil.copy2(salt_file, backup_dir / salt_file.name)
            logger.info(f"✅ {len(salt_files)} fichiers salt_*.bin sauvegardés")

            # Créer un tar.gz pour sécurité supplémentaire
            import tarfile
            tar_path = Path(str(backup_dir) + ".tar.gz")
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(backup_dir, arcname=backup_dir.name)
            logger.info(f"✅ Archive créée : {tar_path}")

            logger.info(f"✅ Backup complet créé : {backup_dir}")
            return backup_dir

        except Exception as e:
            logger.error(f"❌ Erreur lors du backup : {e}")
            raise MigrationError(f"Échec du backup : {e}") from e

    def check_migration_status(self, conn: sqlite3.Connection) -> str:
        """Vérifie si la migration a déjà été appliquée.

        Args:
            conn: Connexion à users.db

        Returns:
            'not_started', 'in_progress', 'completed'
        """
        cursor = conn.cursor()

        # Créer la table de suivi si elle n'existe pas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migration_status (
                id INTEGER PRIMARY KEY,
                migration_name TEXT UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT
            )
        ''')
        conn.commit()

        # Vérifier le statut
        cursor.execute('''
            SELECT status FROM migration_status
            WHERE migration_name = ?
        ''', (self.MIGRATION_NAME,))

        row = cursor.fetchone()
        if row is None:
            return 'not_started'
        return row[0]

    def mark_migration_started(self, conn: sqlite3.Connection):
        """Marque le début de la migration."""
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO migration_status (migration_name, status)
            VALUES (?, 'in_progress')
        ''', (self.MIGRATION_NAME,))
        conn.commit()
        logger.info("Migration marquée comme 'in_progress'")

    def mark_migration_completed(self, conn: sqlite3.Connection):
        """Marque la migration comme terminée."""
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE migration_status
            SET status = 'completed', applied_at = CURRENT_TIMESTAMP
            WHERE migration_name = ?
        ''', (self.MIGRATION_NAME,))
        conn.commit()
        logger.info("✅ Migration marquée comme 'completed'")

    def migrate_schema(self, conn: sqlite3.Connection):
        """Migre le schéma de la base de données.

        Ajoute les nouvelles colonnes pour email, TOTP, etc.
        """
        cursor = conn.cursor()

        logger.info("Ajout des nouvelles colonnes...")

        # Vérifier quelles colonnes existent déjà
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        columns_to_add = [
            ("email", "TEXT"),
            ("email_hash", "TEXT"),
            ("workspace_uuid", "TEXT"),
            ("secret_2fa", "TEXT"),
            ("totp_enabled", "INTEGER DEFAULT 0"),
            ("totp_confirmed", "INTEGER DEFAULT 0"),
            ("backup_codes", "TEXT"),
            ("last_password_change", "TIMESTAMP"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("last_failed_attempt", "TIMESTAMP"),
            ("account_locked_until", "TIMESTAMP"),
        ]

        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                    logger.info(f"  ✅ Colonne ajoutée : {col_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    logger.debug(f"  ⏭️  Colonne déjà existante : {col_name}")

        conn.commit()
        logger.info("✅ Schéma migré avec succès")

    def migrate_user_data(self, conn: sqlite3.Connection) -> list[tuple[str, str]]:
        """Migre les données des utilisateurs existants.

        Args:
            conn: Connexion à users.db

        Returns:
            Liste de tuples (username, workspace_uuid) pour renommage des fichiers
        """
        cursor = conn.cursor()

        # Récupérer les utilisateurs sans UUID
        cursor.execute('''
            SELECT id, username
            FROM users
            WHERE workspace_uuid IS NULL OR workspace_uuid = ''
        ''')
        users = cursor.fetchall()

        if not users:
            logger.info("Aucun utilisateur à migrer")
            return []

        logger.info(f"Migration de {len(users)} utilisateur(s)...")

        mappings = []
        for user_id, username in users:
            # Générer un UUID pour le workspace
            workspace_uuid = str(uuid.uuid4())

            # Créer un email temporaire
            temp_email = f"{username}@migration.local"

            # Hasher l'email avec HMAC
            email_hash = self.hash_email(temp_email)

            # Mettre à jour l'utilisateur
            cursor.execute('''
                UPDATE users
                SET workspace_uuid = ?,
                    email = ?,
                    email_hash = ?,
                    totp_enabled = 0,
                    totp_confirmed = 0
                WHERE id = ?
            ''', (workspace_uuid, temp_email, email_hash, user_id))

            mappings.append((username, workspace_uuid))
            logger.info(f"  ✅ {username} → UUID: {workspace_uuid[:8]}... | Email: {temp_email}")

        conn.commit()
        logger.info(f"✅ {len(mappings)} utilisateur(s) migré(s)")
        return mappings

    def rename_workspace_files(self, mappings: list[tuple[str, str]]):
        """Renomme les fichiers de workspace (passwords_*.db et salt_*.bin).

        Args:
            mappings: Liste de tuples (username, workspace_uuid)

        Raises:
            MigrationError: Si un conflit de fichier est détecté
        """
        logger.info("Renommage des fichiers de workspace...")

        for username, workspace_uuid in mappings:
            # Renommer passwords_username.db → passwords_uuid.db
            old_db = self.data_dir / f"passwords_{username}.db"
            new_db = self.data_dir / f"passwords_{workspace_uuid}.db"

            if old_db.exists():
                if new_db.exists():
                    raise MigrationError(
                        f"Conflit : {new_db} existe déjà ! Migration interrompue."
                    )
                old_db.rename(new_db)
                logger.info(f"  ✅ {old_db.name} → {new_db.name}")
            else:
                logger.warning(f"  ⚠️  Fichier manquant : {old_db}")

            # Renommer salt_username.bin → salt_uuid.bin
            old_salt = self.data_dir / f"salt_{username}.bin"
            new_salt = self.data_dir / f"salt_{workspace_uuid}.bin"

            if old_salt.exists():
                if new_salt.exists():
                    raise MigrationError(
                        f"Conflit : {new_salt} existe déjà ! Migration interrompue."
                    )
                old_salt.rename(new_salt)
                logger.info(f"  ✅ {old_salt.name} → {new_salt.name}")
            else:
                logger.warning(f"  ⚠️  Fichier manquant : {old_salt}")

        logger.info("✅ Fichiers renommés avec succès")

    def create_indexes(self, conn: sqlite3.Connection):
        """Crée les index pour améliorer les performances."""
        cursor = conn.cursor()

        indexes = [
            (
                "idx_users_email_hash",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_hash ON users(email_hash)"
            ),
            (
                "idx_users_workspace_uuid",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_workspace_uuid "
                "ON users(workspace_uuid)"
            ),
            (
                "idx_users_email",
                "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
            ),
        ]

        logger.info("Création des index...")
        for idx_name, idx_sql in indexes:
            cursor.execute(idx_sql)
            logger.info(f"  ✅ {idx_name}")

        conn.commit()
        logger.info("✅ Index créés")

    def validate_migration(self, conn: sqlite3.Connection) -> bool:
        """Valide que la migration s'est correctement déroulée.

        Returns:
            True si la validation réussit

        Raises:
            MigrationError: Si la validation échoue
        """
        logger.info("Validation de la migration...")
        cursor = conn.cursor()

        # Vérifier qu'aucun email_hash n'est NULL
        cursor.execute("SELECT COUNT(*) FROM users WHERE email_hash IS NULL OR email_hash = ''")
        null_email_hash = cursor.fetchone()[0]
        if null_email_hash > 0:
            raise MigrationError(f"❌ {null_email_hash} utilisateur(s) sans email_hash !")
        logger.info("  ✅ Tous les utilisateurs ont un email_hash")

        # Vérifier qu'aucun workspace_uuid n'est NULL
        cursor.execute(
            "SELECT COUNT(*) FROM users "
            "WHERE workspace_uuid IS NULL OR workspace_uuid = ''"
        )
        null_uuid = cursor.fetchone()[0]
        if null_uuid > 0:
            raise MigrationError(f"❌ {null_uuid} utilisateur(s) sans workspace_uuid !")
        logger.info("  ✅ Tous les utilisateurs ont un workspace_uuid")

        # Vérifier que tous les fichiers UUID existent
        cursor.execute("SELECT username, workspace_uuid FROM users")
        missing_files = []
        for _, workspace_uuid in cursor.fetchall():
            db_path = self.data_dir / f"passwords_{workspace_uuid}.db"
            salt_path = self.data_dir / f"salt_{workspace_uuid}.bin"

            if not db_path.exists():
                missing_files.append(str(db_path))
                logger.warning(f"  ⚠️  Base manquante : {db_path}")

            if not salt_path.exists():
                missing_files.append(str(salt_path))
                logger.warning(f"  ⚠️  Salt manquant : {salt_path}")

        if missing_files:
            logger.warning(f"⚠️  {len(missing_files)} fichier(s) manquant(s)")
            logger.warning("Cela peut être normal si certains utilisateurs "
                           "n'ont jamais eu de workspace")
        else:
            logger.info("  ✅ Tous les fichiers de workspace existent")

        logger.info("✅ Validation terminée")
        return True

    def run(self) -> bool:
        """Execute la migration complète.

        Returns:
            True si la migration réussit
        """
        try:
            logger.info("=" * 70)
            logger.info("DÉBUT DE LA MIGRATION : Email + TOTP + UUID")
            logger.info("=" * 70)

            # Étape 1 : Backup
            if self.auto_backup:
                self.backup_dir = self.create_backup()
                logger.info(f"📦 Backup sauvegardé dans : {self.backup_dir}")

            # Connexion à la base de données
            conn = sqlite3.connect(str(self.users_db))

            try:
                # Étape 2 : Vérifier le statut
                status = self.check_migration_status(conn)
                logger.info(f"Statut de migration : {status}")

                if status == 'completed':
                    logger.warning("⚠️  Migration déjà appliquée ! Aucune action nécessaire.")
                    return True

                if status == 'in_progress':
                    logger.error("❌ Migration déjà en cours ! Vérification manuelle requise.")
                    logger.error(f"   Vérifiez {self.users_db} et restaurez "
                                 "depuis {self.backup_dir} si nécessaire")
                    return False

                # Étape 3 : Marquer le début
                self.mark_migration_started(conn)

                # Étape 4 : Migrer le schéma
                self.migrate_schema(conn)

                # Étape 5 : Migrer les données utilisateurs
                mappings = self.migrate_user_data(conn)

                # Étape 6 : Renommer les fichiers
                if mappings:
                    self.rename_workspace_files(mappings)

                # Étape 7 : Créer les index
                self.create_indexes(conn)

                # Étape 8 : Valider
                self.validate_migration(conn)

                # Étape 9 : Marquer comme terminée
                self.mark_migration_completed(conn)

                logger.info("=" * 70)
                logger.info("✅ MIGRATION TERMINÉE AVEC SUCCÈS")
                logger.info("=" * 70)
                logger.info("")
                logger.info("PROCHAINES ÉTAPES :")
                logger.info("1. Fournir un email réel à la première connexion")
                logger.info("2. La configuration 2FA sera OBLIGATOIRE pour tous les utilisateurs")
                logger.info("3. Testez la connexion avec run-dev.sh avant de déployer en prod.")
                logger.info("")

                return True

            finally:
                conn.close()

        except MigrationError as e:
            logger.error(f"❌ ERREUR DE MIGRATION : {e}")
            logger.error("")
            logger.error("LA MIGRATION A ÉCHOUÉ !")
            logger.error(f"Restaurez depuis le backup : {self.backup_dir}")
            logger.error("")
            return False

        except Exception as e:
            logger.exception(f"❌ ERREUR INATTENDUE : {e}")
            logger.error("")
            logger.error("LA MIGRATION A ÉCHOUÉ !")
            logger.error(f"Restaurez depuis le backup : {self.backup_dir}")
            logger.error("")
            return False


def main():
    """Point d'entrée du script de migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migre le système vers Email + TOTP + UUID"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./data"),
        help="Répertoire contenant les données (défaut: ./data)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Ne pas créer de backup (NON RECOMMANDÉ)"
    )

    args = parser.parse_args()

    if args.no_backup:
        logger.warning("⚠️  Option --no-backup activée : aucun backup ne sera créé !")
        response = input("Êtes-vous sûr de vouloir continuer ? (oui/non) : ")
        if response.lower() not in ['oui', 'yes', 'y']:
            logger.info("Migration annulée par l'utilisateur")
            sys.exit(0)

    # Créer le gestionnaire et lancer la migration
    migration = EmailTOTPMigration(
        data_dir=args.data_dir,
        auto_backup=not args.no_backup
    )

    success = migration.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

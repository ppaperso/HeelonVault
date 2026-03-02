#!/usr/bin/env python3
"""Script de rollback pour annuler la migration Email + TOTP + UUID.

Ce script permet de restaurer les données depuis un backup créé avant migration.

IMPORTANT : Ce script doit être exécuté dans le venv du projet.
"""

import logging
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RollbackError(Exception):
    """Exception levée en cas d'erreur de rollback."""
    pass


class EmailTOTPRollback:
    """Gestionnaire de rollback de la migration."""

    MIGRATION_NAME = "email_totp_uuid_v1"

    def __init__(self, data_dir: Path, backup_dir: Path):
        """Initialise le gestionnaire de rollback.

        Args:
            data_dir: Répertoire contenant les données actuelles
            backup_dir: Répertoire de backup à restaurer
        """
        self.data_dir = Path(data_dir)
        self.backup_dir = Path(backup_dir)

        if not self.data_dir.exists():
            raise RollbackError(f"❌ Répertoire de données introuvable : {self.data_dir}")

        if not self.backup_dir.exists():
            raise RollbackError(f"❌ Répertoire de backup introuvable : {self.backup_dir}")

        self.users_db = self.data_dir / "users.db"
        self.backup_users_db = self.backup_dir / "users.db"

        if not self.backup_users_db.exists():
            raise RollbackError(f"❌ Backup users.db introuvable : {self.backup_users_db}")

        logger.info(f"Rollback initialisé : {self.data_dir} <- {self.backup_dir}")

    def create_rollback_backup(self) -> Path:
        """Crée un backup de l'état actuel avant rollback (au cas où).

        Returns:
            Chemin du backup de rollback
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rollback_backup_dir = self.data_dir / f"backup_before_rollback_{timestamp}"

        try:
            rollback_backup_dir.mkdir(parents=True, exist_ok=False)

            # Copier users.db
            if self.users_db.exists():
                shutil.copy2(self.users_db, rollback_backup_dir / "users.db")

            # Copier tous les passwords_*.db
            for db_file in self.data_dir.glob("passwords_*.db"):
                shutil.copy2(db_file, rollback_backup_dir / db_file.name)

            # Copier tous les salt_*.bin
            for salt_file in self.data_dir.glob("salt_*.bin"):
                shutil.copy2(salt_file, rollback_backup_dir / salt_file.name)

            logger.info(f"✅ Backup de rollback créé : {rollback_backup_dir}")
            return rollback_backup_dir

        except Exception as e:
            logger.error(f"❌ Erreur création backup de rollback : {e}")
            raise RollbackError(f"Échec du backup de rollback : {e}") from e

    def check_migration_can_rollback(self) -> bool:
        """Vérifie que le rollback peut être effectué en toute sécurité.

        Returns:
            True si le rollback est possible
        """
        try:
            # Vérifier que la migration a bien été appliquée
            conn = sqlite3.connect(str(self.users_db))
            cursor = conn.cursor()

            # Vérifier si la table migration_status existe
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='migration_status'
            """)
            if not cursor.fetchone():
                logger.warning("⚠️  Table migration_status introuvable, migration pas appliquée")
                conn.close()
                return True  # On peut quand même rollback

            # Vérifier le statut de la migration
            cursor.execute("""
                SELECT status FROM migration_status
                WHERE migration_name = ?
            """, (self.MIGRATION_NAME,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                logger.info("ℹ️  Migration jamais appliquée, rollback non nécessaire")
                return False

            status = row[0]
            if status != 'completed':
                logger.warning(f"⚠️  Migration en statut '{status}', rollback recommandé")

            return True

        except Exception:
            logger.exception("Erreur vérification statut migration")
            return True  # En cas de doute, autoriser le rollback

    def restore_users_db(self):
        """Restaure users.db depuis le backup."""
        logger.info("Restauration de users.db...")

        try:
            # Sauvegarder l'actuel avant écrasement
            if self.users_db.exists():
                temp_backup = self.users_db.with_suffix('.db.before_rollback')
                shutil.copy2(self.users_db, temp_backup)
                logger.debug(f"Backup temporaire : {temp_backup}")

            # Restaurer depuis le backup
            shutil.copy2(self.backup_users_db, self.users_db)
            logger.info("✅ users.db restauré")

        except Exception as e:
            logger.error(f"❌ Erreur restauration users.db : {e}")
            raise RollbackError(f"Échec restauration users.db : {e}") from e

    def restore_workspace_files(self):
        """Restaure les fichiers passwords_*.db et salt_*.bin."""
        logger.info("Restauration des fichiers de workspace...")

        # Récupérer les correspondances depuis le backup users.db
        try:
            conn = sqlite3.connect(str(self.backup_users_db))
            cursor = conn.cursor()

            # Vérifier si la colonne username existe
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'username' not in columns:
                logger.warning("⚠️  Col 'username' introuvable dans le backup, skip restore files")
                conn.close()
                return

            cursor.execute('SELECT username FROM users')
            usernames = [row[0] for row in cursor.fetchall()]
            conn.close()

            # Pour chaque username, restaurer les fichiers
            restored_count = 0
            for username in usernames:
                # Restaurer passwords_username.db
                backup_db = self.backup_dir / f"passwords_{username}.db"
                target_db = self.data_dir / f"passwords_{username}.db"

                if backup_db.exists():
                    shutil.copy2(backup_db, target_db)
                    restored_count += 1
                    logger.info(f"  ✅ Restauré : {backup_db.name}")

                # Restaurer salt_username.bin
                backup_salt = self.backup_dir / f"salt_{username}.bin"
                target_salt = self.data_dir / f"salt_{username}.bin"

                if backup_salt.exists():
                    shutil.copy2(backup_salt, target_salt)
                    logger.info(f"  ✅ Restauré : {backup_salt.name}")

            logger.info(f"✅ {restored_count} fichiers de workspace restaurés")

        except Exception as e:
            logger.exception("Erreur restauration fichiers workspace")
            raise RollbackError(f"Échec restauration fichiers : {e}") from e

    def cleanup_migrated_files(self):
        """Supprime les fichiers créés par la migration (UUID files)."""
        logger.info("Nettoyage des fichiers créés par la migration...")

        try:
            # Connexion au backup pour récupérer les UUIDs créés
            conn = sqlite3.connect(str(self.users_db))
            cursor = conn.cursor()

            # Vérifier si la colonne workspace_uuid existe
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'workspace_uuid' in columns:
                cursor.execute('SELECT workspace_uuid FROM users WHERE workspace_uuid IS NOT NULL')
                uuids = [row[0] for row in cursor.fetchall()]

                # Supprimer les fichiers UUID
                deleted_count = 0
                for uuid in uuids:
                    uuid_db = self.data_dir / f"passwords_{uuid}.db"
                    if uuid_db.exists():
                        uuid_db.unlink()
                        deleted_count += 1
                        logger.debug(f"  🗑️  Supprimé : {uuid_db.name}")

                    uuid_salt = self.data_dir / f"salt_{uuid}.bin"
                    if uuid_salt.exists():
                        uuid_salt.unlink()
                        logger.debug(f"  🗑️  Supprimé : {uuid_salt.name}")

                logger.info(f"✅ {deleted_count} fichiers UUID supprimés")

            conn.close()

        except Exception as e:
            logger.warning(f"⚠️  Erreur nettoyage fichiers UUID : {e}")
            # Non bloquant

    def run(self) -> bool:
        """Execute le rollback complet.

        Returns:
            True si le rollback réussit
        """
        try:
            logger.info("=" * 70)
            logger.info("DÉBUT DU ROLLBACK : Email + TOTP + UUID")
            logger.info("=" * 70)

            # Vérifier que le rollback est possible
            if not self.check_migration_can_rollback():
                logger.info("⏭️  Rollback non nécessaire")
                return True

            # Créer un backup de l'état actuel
            rollback_backup = self.create_rollback_backup()
            logger.info(f"📦 Backup de sécurité : {rollback_backup}")

            # Restaurer users.db
            self.restore_users_db()

            # Restaurer les fichiers de workspace
            self.restore_workspace_files()

            # Nettoyer les fichiers créés par la migration
            self.cleanup_migrated_files()

            logger.info("=" * 70)
            logger.info("✅ ROLLBACK TERMINÉ AVEC SUCCÈS")
            logger.info("=" * 70)
            logger.info("")
            logger.info("Les données ont été restaurées depuis le backup.")
            logger.info(f"Un backup de l'état avant rollback a été créé : {rollback_backup}")
            logger.info("")

            return True

        except RollbackError as e:
            logger.error(f"❌ ERREUR DE ROLLBACK : {e}")
            logger.error("")
            logger.error("LE ROLLBACK A ÉCHOUÉ !")
            logger.error("Restauration manuelle nécessaire.")
            logger.error("")
            return False

        except Exception as e:
            logger.exception(f"❌ ERREUR INATTENDUE : {e}")
            logger.error("")
            logger.error("LE ROLLBACK A ÉCHOUÉ !")
            logger.error("Restauration manuelle nécessaire.")
            logger.error("")
            return False


def extract_backup_tar(tar_path: Path) -> Path:
    """Extrait un backup tar.gz.

    Args:
        tar_path: Chemin vers le .tar.gz

    Returns:
        Chemin du répertoire extrait
    """
    logger.info(f"Extraction de {tar_path}...")
    extract_dir = tar_path.parent / tar_path.stem.replace('.tar', '')

    with tarfile.open(tar_path, 'r:gz') as tar:
        tar.extractall(tar_path.parent, filter='data')

    logger.info(f"✅ Extraction terminée : {extract_dir}")
    return extract_dir


def main():
    """Point d'entrée du script de rollback."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Rollback de la migration Email + TOTP + UUID"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./data"),
        help="Répertoire contenant les données actuelles (défaut: ./data)"
    )
    parser.add_argument(
        "--backup",
        type=Path,
        required=True,
        help="Répertoire de backup à restaurer (ou fichier .tar.gz)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forcer le rollback sans confirmation"
    )

    args = parser.parse_args()

    # Si c'est un .tar.gz, l'extraire d'abord
    backup_path = args.backup
    if backup_path.suffix == '.gz' and backup_path.stem.endswith('.tar'):
        backup_path = extract_backup_tar(backup_path)

    # Confirmation
    if not args.force:
        print("=" * 70)
        print("⚠️  ATTENTION : ROLLBACK DE LA MIGRATION")
        print("=" * 70)
        print(f"Répertoire de données : {args.data_dir}")
        print(f"Backup à restaurer     : {backup_path}")
        print("")
        print("Cette opération va :")
        print("  1. Restaurer users.db depuis le backup")
        print("  2. Restaurer tous les fichiers passwords_*.db et salt_*.bin")
        print("  3. Supprimer les fichiers créés par la migration (UUID)")
        print("")
        response = input("Êtes-vous sûr de vouloir continuer ? (oui/non) : ")
        if response.lower() not in ['oui', 'yes', 'y']:
            logger.info("Rollback annulé par l'utilisateur")
            sys.exit(0)

    # Créer le gestionnaire et lancer le rollback
    rollback = EmailTOTPRollback(
        data_dir=args.data_dir,
        backup_dir=backup_path
    )

    success = rollback.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

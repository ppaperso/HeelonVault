"""Service de sauvegarde automatique des bases de données."""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class BackupService:
    """Gère les sauvegardes automatiques des bases de données."""
    
    def __init__(self, data_dir: Path):
        """Initialise le service de sauvegarde.
        
        Args:
            data_dir: Répertoire contenant les bases de données
        """
        self.data_dir = data_dir
        self.backup_dir = data_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True, parents=True)
        logger.debug("BackupService initialisé avec data_dir=%s", data_dir)
    
    def create_backup(self, db_path: Path, username: str) -> Optional[Path]:
        """Crée une sauvegarde horodatée d'une base de données.
        
        Args:
            db_path: Chemin vers la base de données à sauvegarder
            username: Nom de l'utilisateur (pour le nom de fichier)
            
        Returns:
            Path: Chemin vers le fichier de sauvegarde créé, ou None si erreur
        """
        if not db_path.exists():
            logger.warning("Base de données inexistante: %s", db_path)
            return None
        
        try:
            # Obtenir la modification time du fichier
            mtime = db_path.stat().st_mtime
            
            # Vérifier si une sauvegarde récente existe déjà (moins de 1 minute)
            existing_backups = list(self.backup_dir.glob(f"passwords_{username}_*.db"))
            if existing_backups:
                latest_backup = max(existing_backups, key=lambda p: p.stat().st_mtime)
                latest_mtime = latest_backup.stat().st_mtime
                time_diff = mtime - latest_mtime
                
                if time_diff < 60:  # Moins d'une minute de différence
                    logger.debug("Sauvegarde récente déjà existante pour %s, skip", username)
                    return latest_backup
            
            # Créer le nom de fichier avec horodatage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"passwords_{username}_{timestamp}.db"
            backup_path = self.backup_dir / backup_name
            
            # Copier la base de données
            shutil.copy2(db_path, backup_path)
            
            # Définir les permissions appropriées (lecture/écriture propriétaire uniquement)
            backup_path.chmod(0o600)
            
            logger.info("Sauvegarde créée: %s (taille=%d bytes)", 
                       backup_path.name, backup_path.stat().st_size)
            
            # Nettoyer les anciennes sauvegardes (garder les 7 dernières)
            self._cleanup_old_backups(username, keep=7)
            
            return backup_path
            
        except Exception as e:
            logger.exception("Erreur lors de la création de la sauvegarde pour %s: %s", 
                           username, e)
            return None
    
    def create_user_db_backup(self, username: str) -> Optional[Path]:
        """Crée une sauvegarde de la base de données d'un utilisateur.
        
        Args:
            username: Nom de l'utilisateur
            
        Returns:
            Path: Chemin vers le fichier de sauvegarde ou None
        """
        db_path = self.data_dir / f"passwords_{username}.db"
        return self.create_backup(db_path, username)
    
    def create_full_system_backup(self) -> Optional[Path]:
        """Crée une sauvegarde complète de tout le système.
        
        Sauvegarde tous les fichiers sensibles :
        - users.db (base des utilisateurs)
        - passwords_*.db (toutes les bases de mots de passe)
        - salt_*.bin (tous les fichiers salt)
        
        Returns:
            Path: Chemin vers le dossier de sauvegarde ou None si erreur
        """
        try:
            # Créer un dossier de sauvegarde horodaté
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_folder_name = f"system_backup_{timestamp}"
            backup_folder = self.backup_dir / backup_folder_name
            backup_folder.mkdir(exist_ok=True, parents=True)
            
            files_backed_up = []
            
            # Sauvegarder users.db
            users_db = self.data_dir / "users.db"
            if users_db.exists():
                dest = backup_folder / "users.db"
                shutil.copy2(users_db, dest)
                dest.chmod(0o600)
                files_backed_up.append("users.db")
                logger.debug("Sauvegardé: users.db")
            
            # Sauvegarder toutes les bases de données passwords_*.db
            for db_file in self.data_dir.glob("passwords_*.db"):
                dest = backup_folder / db_file.name
                shutil.copy2(db_file, dest)
                dest.chmod(0o600)
                files_backed_up.append(db_file.name)
                logger.debug("Sauvegardé: %s", db_file.name)
            
            # Sauvegarder tous les fichiers salt_*.bin
            for salt_file in self.data_dir.glob("salt_*.bin"):
                dest = backup_folder / salt_file.name
                shutil.copy2(salt_file, dest)
                dest.chmod(0o600)
                files_backed_up.append(salt_file.name)
                logger.debug("Sauvegardé: %s", salt_file.name)
            
            # Créer un fichier manifest avec les détails
            manifest_path = backup_folder / "MANIFEST.txt"
            with open(manifest_path, 'w') as f:
                f.write("Sauvegarde système complète\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Nombre de fichiers: {len(files_backed_up)}\n")
                f.write("\nFichiers sauvegardés:\n")
                for filename in sorted(files_backed_up):
                    f.write(f"  - {filename}\n")
            manifest_path.chmod(0o600)
            
            # Sécuriser les permissions du dossier
            backup_folder.chmod(0o700)
            
            logger.info("Sauvegarde système complète créée: %s (%d fichiers)", 
                       backup_folder_name, len(files_backed_up))
            
            # Nettoyer les anciennes sauvegardes système (garder les 7 dernières)
            self._cleanup_old_system_backups(keep=7)
            
            return backup_folder
            
        except Exception as e:
            logger.exception("Erreur lors de la création de la sauvegarde système: %s", e)
            return None
    
    def _cleanup_old_system_backups(self, keep: int = 7):
        """Supprime les anciennes sauvegardes système.
        
        Args:
            keep: Nombre de sauvegardes à conserver (par défaut: 7)
        """
        try:
            backups = sorted(
                self.backup_dir.glob("system_backup_*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            old_backups = backups[keep:]
            
            for backup in old_backups:
                if backup.is_dir():
                    shutil.rmtree(backup)
                    logger.debug("Ancienne sauvegarde système supprimée: %s", backup.name)
            
            if old_backups:
                logger.info("Nettoyage: %d anciennes sauvegardes système supprimées", 
                          len(old_backups))
                
        except Exception as e:
            logger.exception("Erreur lors du nettoyage des sauvegardes système: %s", e)
    
    def list_system_backups(self) -> list[Path]:
        """Liste toutes les sauvegardes système.
        
        Returns:
            list[Path]: Liste des dossiers de sauvegarde, triés par date (plus récent en premier)
        """
        backups = sorted(
            self.backup_dir.glob("system_backup_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return backups
    
    def get_system_backup_info(self, backup_folder: Path) -> dict:
        """Récupère les informations sur une sauvegarde système.
        
        Args:
            backup_folder: Chemin vers le dossier de sauvegarde
            
        Returns:
            dict: Informations sur la sauvegarde
        """
        stat = backup_folder.stat()
        
        # Compter les fichiers dans le dossier
        files = list(backup_folder.glob("*"))
        file_count = len([f for f in files if f.name != "MANIFEST.txt"])
        
        # Calculer la taille totale
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        
        # Lire le manifest si disponible
        manifest_path = backup_folder / "MANIFEST.txt"
        file_list = []
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r') as f:
                    content = f.read()
                    # Extraire la liste des fichiers
                    if "Fichiers sauvegardés:" in content:
                        file_list = [line.strip().replace("- ", "") 
                                   for line in content.split("Fichiers sauvegardés:")[1].strip().split("\n")
                                   if line.strip().startswith("-")]
            except Exception:
                pass
        
        return {
            'name': backup_folder.name,
            'path': backup_folder,
            'size': total_size,
            'file_count': file_count,
            'files': file_list,
            'created': datetime.fromtimestamp(stat.st_mtime),
            'created_str': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def _cleanup_old_backups(self, username: str, keep: int = 7):
        """Supprime les anciennes sauvegardes pour ne garder que les N dernières.
        
        Args:
            username: Nom de l'utilisateur
            keep: Nombre de sauvegardes à conserver (par défaut: 7)
        """
        try:
            backups = sorted(
                self.backup_dir.glob(f"passwords_{username}_*.db"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Garder seulement les N dernières
            old_backups = backups[keep:]
            
            for backup in old_backups:
                backup.unlink()
                logger.debug("Ancienne sauvegarde supprimée: %s", backup.name)
            
            if old_backups:
                logger.info("Nettoyage effectué: %d anciennes sauvegardes supprimées pour %s", 
                          len(old_backups), username)
                
        except Exception as e:
            logger.exception("Erreur lors du nettoyage des sauvegardes pour %s: %s", 
                           username, e)
    
    def list_backups(self, username: str) -> list[Path]:
        """Liste toutes les sauvegardes d'un utilisateur.
        
        Args:
            username: Nom de l'utilisateur
            
        Returns:
            list[Path]: Liste des chemins de sauvegarde, triés par date (plus récent en premier)
        """
        backups = sorted(
            self.backup_dir.glob(f"passwords_{username}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return backups
    
    def get_backup_info(self, backup_path: Path) -> dict:
        """Récupère les informations sur une sauvegarde.
        
        Args:
            backup_path: Chemin vers le fichier de sauvegarde
            
        Returns:
            dict: Informations sur la sauvegarde (nom, date, taille)
        """
        stat = backup_path.stat()
        return {
            'name': backup_path.name,
            'path': backup_path,
            'size': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_mtime),
            'created_str': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def restore_backup(self, backup_path: Path, target_path: Path) -> bool:
        """Restaure une sauvegarde vers une base de données.
        
        Args:
            backup_path: Chemin vers le fichier de sauvegarde
            target_path: Chemin de destination
            
        Returns:
            bool: True si la restauration a réussi, False sinon
        """
        try:
            if not backup_path.exists():
                logger.error("Fichier de sauvegarde inexistant: %s", backup_path)
                return False
            
            # Créer une sauvegarde de sécurité avant de restaurer
            if target_path.exists():
                safety_backup = target_path.with_suffix('.db.before_restore')
                shutil.copy2(target_path, safety_backup)
                logger.info("Sauvegarde de sécurité créée: %s", safety_backup.name)
            
            # Restaurer
            shutil.copy2(backup_path, target_path)
            target_path.chmod(0o600)
            
            logger.info("Sauvegarde restaurée: %s → %s", 
                       backup_path.name, target_path.name)
            return True
            
        except Exception as e:
            logger.exception("Erreur lors de la restauration de %s: %s", 
                           backup_path, e)
            return False

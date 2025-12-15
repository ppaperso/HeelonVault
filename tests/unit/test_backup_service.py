"""Tests unitaires pour le service de sauvegarde."""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import time

from src.services.backup_service import BackupService


class TestBackupService(unittest.TestCase):
    """Tests pour le BackupService."""
    
    def setUp(self):
        """Crée un répertoire temporaire pour les tests."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.backup_service = BackupService(self.temp_dir)
        
        # Créer une fausse base de données
        self.test_db = self.temp_dir / "passwords_testuser.db"
        self.test_db.write_text("Contenu de test de la base de données")
    
    def tearDown(self):
        """Nettoie le répertoire temporaire."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_backup_service_initialization(self):
        """Test l'initialisation du service."""
        self.assertTrue(self.backup_service.backup_dir.exists())
        self.assertEqual(self.backup_service.data_dir, self.temp_dir)
    
    def test_create_backup_success(self):
        """Test la création d'une sauvegarde."""
        backup_path = self.backup_service.create_backup(self.test_db, "testuser")
        
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.exists())
        self.assertTrue(backup_path.name.startswith("passwords_testuser_"))
        self.assertTrue(backup_path.name.endswith(".db"))
        
        # Vérifier le contenu
        self.assertEqual(backup_path.read_text(), "Contenu de test de la base de données")
        
        # Vérifier les permissions (600)
        permissions = oct(backup_path.stat().st_mode)[-3:]
        self.assertEqual(permissions, "600")
    
    def test_create_backup_nonexistent_file(self):
        """Test avec un fichier inexistant."""
        fake_db = self.temp_dir / "nonexistent.db"
        backup_path = self.backup_service.create_backup(fake_db, "testuser")
        
        self.assertIsNone(backup_path)
    
    def test_create_user_db_backup(self):
        """Test la sauvegarde d'une base utilisateur."""
        backup_path = self.backup_service.create_user_db_backup("testuser")
        
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.exists())
    
    def test_list_backups(self):
        """Test le listage des sauvegardes."""
        # Créer plusieurs sauvegardes (avec délai > 60s pour éviter le skip)
        # Pour le test, on crée directement les fichiers
        backup1 = self.backup_service.backup_dir / "passwords_testuser_20251121_100000.db"
        backup1.write_text("Backup 1")
        time.sleep(0.1)
        backup2 = self.backup_service.backup_dir / "passwords_testuser_20251121_110000.db"
        backup2.write_text("Backup 2")
        
        backups = self.backup_service.list_backups("testuser")
        self.assertGreaterEqual(len(backups), 2)
        
        # Vérifier que c'est trié par date (plus récent en premier)
        if len(backups) >= 2:
            self.assertGreater(
                backups[0].stat().st_mtime,
                backups[1].stat().st_mtime
            )
    
    def test_cleanup_old_backups(self):
        """Test le nettoyage des anciennes sauvegardes."""
        # Créer 15 sauvegardes
        for i in range(15):
            backup_path = self.backup_service.backup_dir / f"passwords_testuser_{i:04d}.db"
            backup_path.write_text(f"Backup {i}")
            time.sleep(0.01)  # Assurer des timestamps différents
        
        # Nettoyer (garder 7)
        self.backup_service._cleanup_old_backups("testuser", keep=7)
        
        # Vérifier
        remaining_backups = self.backup_service.list_backups("testuser")
        self.assertEqual(len(remaining_backups), 7)
    
    def test_get_backup_info(self):
        """Test la récupération d'informations sur une sauvegarde."""
        backup_path = self.backup_service.create_backup(self.test_db, "testuser")
        
        info = self.backup_service.get_backup_info(backup_path)
        
        self.assertIn('name', info)
        self.assertIn('path', info)
        self.assertIn('size', info)
        self.assertIn('created', info)
        self.assertIn('created_str', info)
        
        self.assertEqual(info['path'], backup_path)
        self.assertGreater(info['size'], 0)
        self.assertIsInstance(info['created'], datetime)
    
    def test_restore_backup(self):
        """Test la restauration d'une sauvegarde."""
        # Créer une sauvegarde
        backup_path = self.backup_service.create_backup(self.test_db, "testuser")
        
        # Modifier le fichier original
        self.test_db.write_text("Contenu modifié")
        self.assertEqual(self.test_db.read_text(), "Contenu modifié")
        
        # Restaurer
        success = self.backup_service.restore_backup(backup_path, self.test_db)
        
        self.assertTrue(success)
        self.assertEqual(self.test_db.read_text(), "Contenu de test de la base de données")
        
        # Vérifier qu'une sauvegarde de sécurité a été créée
        safety_backup = self.test_db.with_suffix('.db.before_restore')
        self.assertTrue(safety_backup.exists())
        self.assertEqual(safety_backup.read_text(), "Contenu modifié")
    
    def test_restore_nonexistent_backup(self):
        """Test la restauration d'une sauvegarde inexistante."""
        fake_backup = self.temp_dir / "fake_backup.db"
        success = self.backup_service.restore_backup(fake_backup, self.test_db)
        
        self.assertFalse(success)
    
    def test_skip_recent_backup(self):
        """Test que les sauvegardes récentes sont ignorées."""
        # Créer une première sauvegarde
        backup1 = self.backup_service.create_backup(self.test_db, "testuser")
        self.assertIsNotNone(backup1)
        
        # Tenter de créer une autre sauvegarde immédiatement (< 1 minute)
        backup2 = self.backup_service.create_backup(self.test_db, "testuser")
        
        # Devrait retourner la sauvegarde existante
        self.assertEqual(backup1, backup2)
        
        # Vérifier qu'il n'y a qu'une seule sauvegarde
        backups = self.backup_service.list_backups("testuser")
        self.assertEqual(len(backups), 1)
    
    def test_backup_filename_format(self):
        """Test le format du nom de fichier de sauvegarde."""
        backup_path = self.backup_service.create_backup(self.test_db, "testuser")
        
        # Format attendu : passwords_testuser_YYYYMMDD_HHMMSS.db
        import re
        pattern = r'passwords_testuser_\d{8}_\d{6}\.db'
        self.assertIsNotNone(re.match(pattern, backup_path.name))
    
    def test_create_full_system_backup(self):
        """Test la création d'une sauvegarde système complète."""
        # Créer plusieurs fichiers de test simulant un système
        users_db = self.temp_dir / "users.db"
        users_db.write_text("Utilisateurs de test")
        
        pwd_db1 = self.temp_dir / "passwords_user1.db"
        pwd_db1.write_text("Mots de passe user1")
        
        pwd_db2 = self.temp_dir / "passwords_user2.db"
        pwd_db2.write_text("Mots de passe user2")
        
        salt1 = self.temp_dir / "salt_user1.bin"
        salt1.write_bytes(b"salt1_data")
        
        salt2 = self.temp_dir / "salt_user2.bin"
        salt2.write_bytes(b"salt2_data")
        
        # Créer la sauvegarde système
        backup_folder = self.backup_service.create_full_system_backup()
        
        self.assertIsNotNone(backup_folder)
        self.assertTrue(backup_folder.exists())
        self.assertTrue(backup_folder.is_dir())
        
        # Vérifier que tous les fichiers ont été sauvegardés
        self.assertTrue((backup_folder / "users.db").exists())
        self.assertTrue((backup_folder / "passwords_user1.db").exists())
        self.assertTrue((backup_folder / "passwords_user2.db").exists())
        self.assertTrue((backup_folder / "salt_user1.bin").exists())
        self.assertTrue((backup_folder / "salt_user2.bin").exists())
        self.assertTrue((backup_folder / "MANIFEST.txt").exists())
        
        # Vérifier les permissions du dossier
        permissions = oct(backup_folder.stat().st_mode)[-3:]
        self.assertEqual(permissions, "700")
    
    def test_list_system_backups(self):
        """Test le listage des sauvegardes système."""
        # Créer quelques fichiers de test
        users_db = self.temp_dir / "users.db"
        users_db.write_text("Test")
        
        # Créer deux sauvegardes manuellement avec des noms différents
        backup1 = self.backup_service.backup_dir / "system_backup_20251120_100000"
        backup1.mkdir()
        (backup1 / "users.db").write_text("Test1")
        
        time.sleep(0.1)
        
        backup2 = self.backup_service.backup_dir / "system_backup_20251121_100000"
        backup2.mkdir()
        (backup2 / "users.db").write_text("Test2")
        
        # Lister les sauvegardes
        backups = self.backup_service.list_system_backups()
        
        self.assertGreaterEqual(len(backups), 2)
        # Vérifier que c'est trié par date (plus récent en premier)
        if len(backups) >= 2:
            self.assertGreater(
                backups[0].stat().st_mtime,
                backups[1].stat().st_mtime
            )
    
    def test_get_system_backup_info(self):
        """Test la récupération d'informations sur une sauvegarde système."""
        # Créer des fichiers de test
        users_db = self.temp_dir / "users.db"
        users_db.write_text("Test users")
        
        pwd_db = self.temp_dir / "passwords_test.db"
        pwd_db.write_text("Test passwords")
        
        # Créer une sauvegarde
        backup_folder = self.backup_service.create_full_system_backup()
        
        # Récupérer les infos
        info = self.backup_service.get_system_backup_info(backup_folder)
        
        self.assertIn('name', info)
        self.assertIn('path', info)
        self.assertIn('size', info)
        self.assertIn('file_count', info)
        self.assertIn('files', info)
        self.assertIn('created', info)
        self.assertIn('created_str', info)
        
        self.assertEqual(info['path'], backup_folder)
        self.assertGreater(info['size'], 0)
        self.assertGreater(info['file_count'], 0)
        self.assertIsInstance(info['created'], datetime)


if __name__ == '__main__':
    unittest.main()

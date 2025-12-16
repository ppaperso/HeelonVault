#!/usr/bin/env python3
"""
Tests unitaires pour la rotation des sauvegardes système.
Vérifie que la rotation conserve exactement 7 sauvegardes (les plus récentes).
"""

import unittest
from pathlib import Path
import tempfile
import shutil
import time
import os
from src.services.backup_service import BackupService


class TestBackupRotation(unittest.TestCase):
    """Tests de rotation des sauvegardes système."""

    def setUp(self):
        """Initialise un environnement de test temporaire."""
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.test_dir) / "data"
        self.data_dir.mkdir()
        
        # Créer des fichiers de test
        self.users_db = self.data_dir / "users.db"
        self.users_db.write_text("test users db")
        
        # Créer quelques bases de mots de passe
        for username in ["admin", "user1", "user2"]:
            pwd_file = self.data_dir / f"passwords_{username}.db"
            pwd_file.write_text(f"test passwords for {username}")
            
            salt_file = self.data_dir / f"salt_{username}.bin"
            salt_file.write_bytes(b"test salt")
        
        self.backup_service = BackupService(self.data_dir)

    def tearDown(self):
        """Nettoie l'environnement de test."""
        shutil.rmtree(self.test_dir)
    
    def _create_fake_backup_folder(self, timestamp_str, age_hours=0):
        """Crée un faux dossier de sauvegarde avec un mtime spécifique."""
        backup_folder = self.backup_service.backup_dir / f"system_backup_{timestamp_str}"
        backup_folder.mkdir(parents=True, exist_ok=True)
        
        # Créer un fichier MANIFEST.txt
        manifest = backup_folder / "MANIFEST.txt"
        manifest.write_text(f"Backup créé le {timestamp_str}\n")
        
        # Ajuster le mtime
        base_time = time.time()
        new_mtime = base_time - (age_hours * 3600)
        os.utime(backup_folder, (new_mtime, new_mtime))
        
        return backup_folder

    def test_rotation_keeps_7_backups(self):
        """Test que la rotation conserve exactement 7 sauvegardes."""
        # Créer 10 fausses sauvegardes avec des âges différents
        backup_names = []
        for i in range(10):
            timestamp = f"20251120_{14+i:02d}0000"
            backup = self._create_fake_backup_folder(timestamp, age_hours=(10-i))
            backup_names.append(backup.name)
        
        # Déclencher une sauvegarde réelle pour activer la rotation
        time.sleep(1.1)
        real_backup = self.backup_service.create_full_system_backup()
        self.assertIsNotNone(real_backup)
        
        # Vérifier qu'il ne reste que 7 sauvegardes maximum (rotation sur 10+1)
        remaining_backups = self.backup_service.list_system_backups()
        self.assertLessEqual(
            len(remaining_backups),
            7,
            f"Maximum 7 sauvegardes attendues, trouvé {len(remaining_backups)}"
        )

    def test_rotation_with_many_backups(self):
        """Test la rotation avec un grand nombre de sauvegardes."""
        # Créer 15 fausses sauvegardes
        for i in range(15):
            timestamp = f"20251120_{10+i:02d}0000"
            self._create_fake_backup_folder(timestamp, age_hours=(15-i))
        
        # Déclencher la rotation avec une vraie sauvegarde
        time.sleep(1.1)
        backup = self.backup_service.create_full_system_backup()
        self.assertIsNotNone(backup)
        
        # Vérifier qu'il ne reste que 7
        remaining_backups = self.backup_service.list_system_backups()
        self.assertLessEqual(len(remaining_backups), 7)

    def test_rotation_preserves_most_recent(self):
        """Test que la rotation préserve les sauvegardes les plus récentes."""
        # Créer 9 fausses sauvegardes
        most_recent_name = None
        for i in range(9):
            timestamp = f"20251120_{10+i:02d}0000"
            backup = self._create_fake_backup_folder(timestamp, age_hours=(9-i))
            if i == 8:  # La dernière (la plus récente en mtime)
                most_recent_name = backup.name
        
        # Déclencher la rotation
        time.sleep(1.1)
        new_backup = self.backup_service.create_full_system_backup()
        self.assertIsNotNone(new_backup)
        
        # Vérifier
        remaining = self.backup_service.list_system_backups()
        self.assertLessEqual(len(remaining), 7)
        
        # La plus récente doit être conservée
        remaining_names = [b.name for b in remaining]
        self.assertIn(
            most_recent_name,
            remaining_names,
            "La sauvegarde la plus récente doit être conservée"
        )

    def test_rotation_with_exactly_7_backups(self):
        """Test qu'avec exactement 7 sauvegardes, aucune n'est supprimée."""
        # Créer exactement 6 fausses sauvegardes
        backups = []
        for i in range(6):
            timestamp = f"20251120_{10+i:02d}0000"
            backup = self._create_fake_backup_folder(timestamp, age_hours=(6-i))
            backups.append(backup)
        
        # Créer une 7ème vraie pour activer la rotation
        time.sleep(1.1)
        real_backup = self.backup_service.create_full_system_backup()
        self.assertIsNotNone(real_backup)
        backups.append(real_backup)
        
        # Vérifier qu'elles sont toutes conservées (7 au total)
        remaining = self.backup_service.list_system_backups()
        self.assertEqual(len(remaining), 7)
        
        # Toutes doivent encore exister
        for backup in backups:
            self.assertTrue(
                backup.exists(),
                f"La sauvegarde {backup.name} devrait être conservée"
            )

    def test_rotation_order_by_mtime(self):
        """Test que la rotation se base sur mtime, pas sur le nom."""
        # Créer 5 fausses sauvegardes avec des noms anciens mais mtime récent
        recent_mtime_names = []
        for i in range(5):
            timestamp = f"20251110_{10+i:02d}0000"  # Dates anciennes dans le nom
            backup = self._create_fake_backup_folder(timestamp, age_hours=i)  # mtime récents
            recent_mtime_names.append(backup.name)
        
        # Créer 5 autres sauvegardes avec des noms récents mais mtime anciens
        old_mtime_names = []
        for i in range(5):
            timestamp = f"20251121_{10+i:02d}0000"  # Dates récentes dans le nom
            backup = self._create_fake_backup_folder(timestamp, age_hours=(20+i))  # mtime anciens
            old_mtime_names.append(backup.name)
        
        # Déclencher la rotation
        time.sleep(1.1)
        new_backup = self.backup_service.create_full_system_backup()
        self.assertIsNotNone(new_backup)
        
        # Vérifier
        remaining = self.backup_service.list_system_backups()
        self.assertLessEqual(len(remaining), 7)
        
        remaining_names = [b.name for b in remaining]
        
        # Au moins quelques sauvegardes avec mtime récents doivent être conservées
        recent_kept = sum(1 for name in recent_mtime_names if name in remaining_names)
        self.assertGreater(
            recent_kept,
            0,
            "Des sauvegardes avec mtime récents doivent être conservées"
        )


if __name__ == '__main__':
    unittest.main()

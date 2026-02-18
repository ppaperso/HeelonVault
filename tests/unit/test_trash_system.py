"""Tests pour le système de corbeille."""

import unittest
import tempfile
import sqlite3
from pathlib import Path
from src.repositories.password_repository import PasswordRepository
from src.models.password_entry import PasswordRecord


class TestTrashSystem(unittest.TestCase):
    """Tests pour le système de corbeille."""

    def setUp(self):
        """Prépare l'environnement de test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        self.repository = PasswordRepository(self.db_path)

    def tearDown(self):
        """Nettoie après les tests."""
        self.repository.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_delete_entry_soft_delete(self):
        """Test que delete_entry effectue un soft delete."""
        # Créer une entrée de test
        record = PasswordRecord(
            title="Test Entry",
            username="testuser",
            password_data={"nonce": "test", "ciphertext": "encrypted"},
            url="https://example.com",
            notes_data={"nonce": "test", "ciphertext": "encrypted_notes"},
            category="Test",
            tags=["tag1", "tag2"],
        )
        
        # Insérer l'entrée
        entry_id = self.repository.insert_entry(record)
        self.assertIsNotNone(entry_id)
        
        # Vérifier qu'elle existe
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 1)
        
        # Supprimer l'entrée (soft delete)
        self.repository.delete_entry(entry_id)
        
        # Vérifier qu'elle n'apparaît plus dans la liste normale
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 0)
        
        # Vérifier qu'elle existe toujours dans la base de données
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passwords WHERE id=?", (entry_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_list_trash(self):
        """Test que list_trash retourne les entrées supprimées."""
        # Créer et supprimer plusieurs entrées
        for i in range(3):
            record = PasswordRecord(
                title=f"Test Entry {i}",
                username=f"testuser{i}",
                password_data={"nonce": f"test{i}", "ciphertext": f"encrypted_{i}"},
            )
            entry_id = self.repository.insert_entry(record)
            if i < 2:  # Supprimer seulement les 2 premières
                self.repository.delete_entry(entry_id)
        
        # Vérifier la corbeille
        trash = self.repository.list_trash()
        self.assertEqual(len(trash), 2)
        
        # Vérifier que la liste normale contient seulement l'entrée non supprimée
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 1)

    def test_restore_entry(self):
        """Test la restauration d'une entrée depuis la corbeille."""
        # Créer une entrée
        record = PasswordRecord(
            title="Test Entry",
            username="testuser",
            password_data={"nonce": "test", "ciphertext": "encrypted"},
        )
        entry_id = self.repository.insert_entry(record)
        
        # Supprimer l'entrée
        self.repository.delete_entry(entry_id)
        
        # Vérifier qu'elle est dans la corbeille
        trash = self.repository.list_trash()
        self.assertEqual(len(trash), 1)
        
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 0)
        
        # Restaurer l'entrée
        self.repository.restore_entry(entry_id)
        
        # Vérifier qu'elle n'est plus dans la corbeille
        trash = self.repository.list_trash()
        self.assertEqual(len(trash), 0)
        
        # Vérifier qu'elle est de retour dans la liste normale
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Test Entry")

    def test_delete_entry_permanently(self):
        """Test la suppression définitive d'une entrée."""
        # Créer une entrée
        record = PasswordRecord(
            title="Test Entry",
            username="testuser",
            password_data={"nonce": "test", "ciphertext": "encrypted"},
        )
        entry_id = self.repository.insert_entry(record)
        
        # Supprimer définitivement l'entrée
        self.repository.delete_entry_permanently(entry_id)
        
        # Vérifier qu'elle n'existe plus du tout
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passwords WHERE id=?", (entry_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_empty_trash(self):
        """Test le vidage complet de la corbeille."""
        # Créer et supprimer plusieurs entrées
        entry_ids = []
        for i in range(5):
            record = PasswordRecord(
                title=f"Test Entry {i}",
                username=f"testuser{i}",
                password_data={"nonce": f"test{i}", "ciphertext": f"encrypted_{i}"},
            )
            entry_id = self.repository.insert_entry(record)
            entry_ids.append(entry_id)
            self.repository.delete_entry(entry_id)
        
        # Vérifier la corbeille
        trash = self.repository.list_trash()
        self.assertEqual(len(trash), 5)
        
        # Vider la corbeille
        count = self.repository.empty_trash()
        self.assertEqual(count, 5)
        
        # Vérifier que la corbeille est vide
        trash = self.repository.list_trash()
        self.assertEqual(len(trash), 0)
        
        # Vérifier que les entrées sont définitivement supprimées
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passwords")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_get_entry_excludes_deleted(self):
        """Test que get_entry n'inclut pas les entrées supprimées par défaut."""
        # Créer une entrée
        record = PasswordRecord(
            title="Test Entry",
            username="testuser",
            password_data={"nonce": "test", "ciphertext": "encrypted"},
        )
        entry_id = self.repository.insert_entry(record)
        
        # Vérifier qu'on peut la récupérer
        entry = self.repository.get_entry(entry_id)
        self.assertIsNotNone(entry)
        
        # Supprimer l'entrée
        self.repository.delete_entry(entry_id)
        
        # Vérifier qu'on ne peut plus la récupérer par défaut
        entry = self.repository.get_entry(entry_id)
        self.assertIsNone(entry)
        
        # Vérifier qu'on peut la récupérer avec include_deleted=True
        entry = self.repository.get_entry(entry_id, include_deleted=True)
        self.assertIsNotNone(entry)

    def test_list_entries_with_include_deleted(self):
        """Test que list_entries peut inclure ou exclure les entrées supprimées."""
        # Créer plusieurs entrées
        for i in range(3):
            record = PasswordRecord(
                title=f"Test Entry {i}",
                username=f"testuser{i}",
                password_data={"nonce": f"test{i}", "ciphertext": f"encrypted_{i}"},
            )
            entry_id = self.repository.insert_entry(record)
            if i == 1:  # Supprimer seulement la deuxième
                self.repository.delete_entry(entry_id)
        
        # Vérifier sans les supprimées (défaut)
        entries = self.repository.list_entries()
        self.assertEqual(len(entries), 2)
        
        # Vérifier avec les supprimées
        entries = self.repository.list_entries(include_deleted=True)
        self.assertEqual(len(entries), 3)

    def test_migration_adds_deleted_at_column(self):
        """Test que la migration ajoute correctement la colonne deleted_at."""
        # Créer une base de données sans la colonne deleted_at
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                username TEXT,
                password_data TEXT NOT NULL,
                url TEXT,
                notes TEXT,
                category TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_changed TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()
        
        # Fermer et rouvrir le repository pour déclencher la migration
        self.repository.close()
        self.repository = PasswordRepository(self.db_path)
        
        # Vérifier que la colonne existe
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(passwords)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        
        self.assertIn("deleted_at", columns)


if __name__ == "__main__":
    unittest.main()

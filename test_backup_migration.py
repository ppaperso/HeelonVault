#!/usr/bin/env python3
"""Test du backup automatique avant migration."""

import logging
import sqlite3
import tempfile
from pathlib import Path

from src.repositories.password_repository import PasswordRepository
from src.services.backup_service import BackupService

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

def test_backup_before_migration():
    """Teste que le backup est créé automatiquement avant une migration."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Créer une vieille base de données SANS la colonne deleted_at
        old_db_path = tmpdir / "passwords_testuser.db"
        conn = sqlite3.connect(str(old_db_path))
        cursor = conn.cursor()
        
        # Créer l'ancienne structure (sans deleted_at)
        cursor.execute("""
            CREATE TABLE passwords (
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
        """)
        
        # Ajouter une entrée de test
        cursor.execute("""
            INSERT INTO passwords (title, username, password_data)
            VALUES ('Test', 'user@test.com', 'encrypted_data')
        """)
        conn.commit()
        conn.close()
        
        print(f"✅ Ancienne base de données créée: {old_db_path}")
        
        # Créer le service de backup
        backup_service = BackupService(tmpdir)
        
        # Vérifier qu'il n'y a pas encore de backup
        backups_before = list((tmpdir / "backups").glob("*.db"))
        print(f"📦 Backups avant migration: {len(backups_before)}")
        
        # Ouvrir le repository (cela devrait déclencher la migration ET le backup)
        print("\n🔄 Ouverture du repository (migration attendue)...")
        repo = PasswordRepository(old_db_path, backup_service)
        
        # Vérifier qu'un backup a été créé
        backups_after = list((tmpdir / "backups").glob("*.db"))
        print(f"📦 Backups après migration: {len(backups_after)}")
        
        if len(backups_after) > len(backups_before):
            backup_path = backups_after[-1]
            print(f"✅ Backup créé avec succès: {backup_path.name}")
            
            # Vérifier que le backup contient bien les données
            backup_conn = sqlite3.connect(str(backup_path))
            backup_cursor = backup_conn.cursor()
            backup_cursor.execute("SELECT COUNT(*) FROM passwords")
            count = backup_cursor.fetchone()[0]
            backup_conn.close()
            print(f"✅ Le backup contient {count} entrée(s)")
            
            # Vérifier que la colonne deleted_at n'existe PAS dans le backup
            backup_conn = sqlite3.connect(str(backup_path))
            backup_cursor = backup_conn.cursor()
            try:
                backup_cursor.execute("SELECT deleted_at FROM passwords LIMIT 1")
                print("❌ ERREUR: La colonne deleted_at existe dans le backup (elle ne devrait pas)")
            except sqlite3.OperationalError:
                print("✅ Le backup contient l'ancienne structure (sans deleted_at)")
            backup_conn.close()
        else:
            print("❌ ERREUR: Aucun backup créé!")
            return False
        
        # Vérifier que la nouvelle base a bien la colonne deleted_at
        cursor = repo.conn.cursor()
        try:
            cursor.execute("SELECT deleted_at FROM passwords LIMIT 1")
            print("✅ La base migrée contient bien la colonne deleted_at")
        except sqlite3.OperationalError:
            print("❌ ERREUR: La colonne deleted_at n'existe pas après migration")
            return False
        
        repo.close()
        
        print("\n🎉 Test réussi! Le backup automatique fonctionne correctement.")
        return True

if __name__ == "__main__":
    success = test_backup_before_migration()
    exit(0 if success else 1)

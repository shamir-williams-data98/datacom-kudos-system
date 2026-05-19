"""
Database layer for the Kudos System.
Handles schema creation, seed data, and query helpers using SQLite.
"""

import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "kudos.db")


def get_connection():
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize the database schema and seed data."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            avatar_color TEXT NOT NULL
        )
    """)

    # Create kudos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kudos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_visible BOOLEAN NOT NULL DEFAULT 1,
            moderated_by INTEGER,
            moderated_at DATETIME,
            moderation_reason TEXT,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id),
            FOREIGN KEY (moderated_by) REFERENCES users(id)
        )
    """)

    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kudos_created_at ON kudos(created_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kudos_sender ON kudos(sender_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kudos_receiver ON kudos(receiver_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kudos_visible ON kudos(is_visible)
    """)

    conn.commit()

    # Seed data if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        _seed_data(conn)

    conn.close()
    logger.info("Database initialized successfully")


def _seed_data(conn):
    """Insert seed employees and sample kudos."""
    cursor = conn.cursor()

    employees = [
        ("Aroha Nguyen", "aroha.nguyen@datacom.co.nz", "admin", "#6C5CE7"),
        ("Liam Patel", "liam.patel@datacom.co.nz", "user", "#00B894"),
        ("Sophie Chen", "sophie.chen@datacom.co.nz", "user", "#E17055"),
        ("Marcus Williams", "marcus.williams@datacom.co.nz", "user", "#0984E3"),
        ("Emma Tanaka", "emma.tanaka@datacom.co.nz", "user", "#E84393"),
        ("Jack Morrison", "jack.morrison@datacom.co.nz", "user", "#00CEC9"),
        ("Isla Ramirez", "isla.ramirez@datacom.co.nz", "user", "#FDCB6E"),
        ("Oliver Kim", "oliver.kim@datacom.co.nz", "user", "#A29BFE"),
        ("Mia Thompson", "mia.thompson@datacom.co.nz", "user", "#FF7675"),
    ]

    cursor.executemany(
        "INSERT INTO users (name, email, role, avatar_color) VALUES (?, ?, ?, ?)",
        employees,
    )

    # Seed a few sample kudos so the feed isn't empty on first load
    sample_kudos = [
        (2, 3, "Sophie, your code review feedback on the API project was incredibly thorough. Thank you for taking the time to help me improve!", "2026-05-17 09:15:00"),
        (4, 2, "Liam, thanks for staying late to help debug the deployment issue. Your dedication to the team is inspiring!", "2026-05-17 11:30:00"),
        (5, 6, "Jack, the onboarding documentation you created for new developers is outstanding. It saved me hours!", "2026-05-17 14:45:00"),
        (3, 8, "Oliver, your presentation at the all-hands meeting was so well-prepared. You made complex topics easy to understand.", "2026-05-18 08:20:00"),
        (7, 5, "Emma, thank you for mentoring me through my first sprint. Your patience and encouragement mean the world!", "2026-05-18 10:00:00"),
        (6, 9, "Mia, your design mockups for the new dashboard are beautiful. The client loved them!", "2026-05-18 12:30:00"),
    ]

    cursor.executemany(
        "INSERT INTO kudos (sender_id, receiver_id, message, created_at) VALUES (?, ?, ?, ?)",
        sample_kudos,
    )

    conn.commit()
    logger.info(f"Seeded {len(employees)} employees and {len(sample_kudos)} sample kudos")


# ─── Query Helpers ────────────────────────────────────────────────────────────


def get_all_users():
    """Return all users as a list of dicts."""
    conn = get_connection()
    rows = conn.execute("SELECT id, name, email, role, avatar_color FROM users ORDER BY name").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_by_id(user_id):
    """Return a single user by ID."""
    conn = get_connection()
    row = conn.execute("SELECT id, name, email, role, avatar_color FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_visible_kudos(page=1, per_page=20):
    """Return visible kudos with sender/receiver names, paginated."""
    conn = get_connection()
    offset = (page - 1) * per_page

    rows = conn.execute("""
        SELECT
            k.id,
            k.message,
            k.created_at,
            s.id AS sender_id,
            s.name AS sender_name,
            s.avatar_color AS sender_color,
            r.id AS receiver_id,
            r.name AS receiver_name,
            r.avatar_color AS receiver_color
        FROM kudos k
        JOIN users s ON k.sender_id = s.id
        JOIN users r ON k.receiver_id = r.id
        WHERE k.is_visible = 1
        ORDER BY k.created_at DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()

    # Get total count for pagination
    total = conn.execute("SELECT COUNT(*) FROM kudos WHERE is_visible = 1").fetchone()[0]
    conn.close()

    return {
        "kudos": [dict(row) for row in rows],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        },
    }


def get_hidden_kudos():
    """Return all hidden kudos with moderation metadata."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            k.id,
            k.message,
            k.created_at,
            k.moderation_reason,
            k.moderated_at,
            s.name AS sender_name,
            s.avatar_color AS sender_color,
            r.name AS receiver_name,
            r.avatar_color AS receiver_color,
            m.name AS moderator_name
        FROM kudos k
        JOIN users s ON k.sender_id = s.id
        JOIN users r ON k.receiver_id = r.id
        LEFT JOIN users m ON k.moderated_by = m.id
        WHERE k.is_visible = 0
        ORDER BY k.moderated_at DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_kudos(sender_id, receiver_id, message):
    """Insert a new kudos record. Returns the created kudos dict."""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO kudos (sender_id, receiver_id, message) VALUES (?, ?, ?)",
        (sender_id, receiver_id, message),
    )
    kudos_id = cursor.lastrowid
    conn.commit()

    # Fetch the created record with joined names
    row = conn.execute("""
        SELECT
            k.id,
            k.message,
            k.created_at,
            s.id AS sender_id,
            s.name AS sender_name,
            s.avatar_color AS sender_color,
            r.id AS receiver_id,
            r.name AS receiver_name,
            r.avatar_color AS receiver_color
        FROM kudos k
        JOIN users s ON k.sender_id = s.id
        JOIN users r ON k.receiver_id = r.id
        WHERE k.id = ?
    """, (kudos_id,)).fetchone()

    conn.close()
    return dict(row)


def check_duplicate_kudos(sender_id, receiver_id, minutes=5):
    """Check if a duplicate kudos was sent within the given time window."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COUNT(*) FROM kudos
        WHERE sender_id = ? AND receiver_id = ?
        AND created_at > datetime('now', ? || ' minutes')
    """, (sender_id, receiver_id, f"-{minutes}")).fetchone()
    conn.close()
    return row[0] > 0


def hide_kudos(kudos_id, moderated_by, reason=None):
    """Hide a kudos (soft-delete)."""
    conn = get_connection()
    conn.execute("""
        UPDATE kudos
        SET is_visible = 0,
            moderated_by = ?,
            moderated_at = ?,
            moderation_reason = ?
        WHERE id = ?
    """, (moderated_by, datetime.now().isoformat(), reason, kudos_id))
    conn.commit()
    conn.close()


def restore_kudos(kudos_id):
    """Restore a hidden kudos."""
    conn = get_connection()
    conn.execute("""
        UPDATE kudos
        SET is_visible = 1,
            moderated_by = NULL,
            moderated_at = NULL,
            moderation_reason = NULL
        WHERE id = ?
    """, (kudos_id,))
    conn.commit()
    conn.close()


def delete_kudos(kudos_id):
    """Permanently delete a kudos."""
    conn = get_connection()
    conn.execute("DELETE FROM kudos WHERE id = ?", (kudos_id,))
    conn.commit()
    conn.close()

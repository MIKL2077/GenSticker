import os
import sqlite3
from pathlib import Path
from ..dirs import get_data_dir


def root():
    path = Path(os.getenv('GENSTICKER_STATE_DIR') or get_data_dir()) / 'features'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def connect():
    db = sqlite3.connect(root() / 'features.sqlite3', timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY,key TEXT UNIQUE NOT NULL,version INTEGER NOT NULL,fingerprint TEXT NOT NULL,metadata TEXT NOT NULL,spec TEXT,status TEXT NOT NULL DEFAULT 'published');
    CREATE TABLE IF NOT EXISTS template_versions(template_id TEXT NOT NULL,version INTEGER NOT NULL,fingerprint TEXT NOT NULL,metadata TEXT NOT NULL,spec TEXT,PRIMARY KEY(template_id,version));
    CREATE TABLE IF NOT EXISTS candidates(hash TEXT PRIMARY KEY,source TEXT NOT NULL,status TEXT NOT NULL,reason TEXT,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,hash TEXT NOT NULL,created REAL NOT NULL,path TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,idempotency TEXT NOT NULL,asset_id TEXT NOT NULL,day TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,lease REAL NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,selection TEXT NOT NULL DEFAULT '[]',message TEXT NOT NULL DEFAULT '',analysis TEXT NOT NULL DEFAULT '{}',algorithm TEXT NOT NULL DEFAULT 'tags-v1',UNIQUE(user_id,idempotency));
    CREATE TABLE IF NOT EXISTS results(job_id TEXT NOT NULL,slot INTEGER NOT NULL,template_id TEXT NOT NULL,version INTEGER NOT NULL,key TEXT NOT NULL,tags TEXT NOT NULL,path TEXT NOT NULL,preview TEXT NOT NULL,PRIMARY KEY(job_id,slot));
    CREATE TABLE IF NOT EXISTS quotas(job_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,day TEXT NOT NULL,status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,job_id TEXT NOT NULL,type TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS preferences(user_id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1,weights TEXT NOT NULL DEFAULT '{}',updated REAL NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS budgets(day TEXT PRIMARY KEY,bytes INTEGER NOT NULL DEFAULT 0,candidates INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS cost_ledger(job_id TEXT PRIMARY KEY,provider TEXT NOT NULL,amount REAL NOT NULL DEFAULT 0,cpu_seconds REAL NOT NULL DEFAULT 0,bytes INTEGER NOT NULL DEFAULT 0);
    ''')
    return db

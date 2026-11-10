import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from src.config import IV_WINDOW_DAYS, TRIM_KEEP_DAYS, now_ist

DB_PATH = Path(__file__).parent.parent / "data" / "iv_history.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_iv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            iv REAL,
            spot REAL,
            expiry TEXT,
            strike REAL,
            option_type TEXT,
            UNIQUE(date, symbol)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            iv_rank REAL,
            iv_percentile REAL,
            current_iv REAL,
            UNIQUE(date, symbol)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

def store_daily_iv(date, symbol, iv, spot, expiry, strike, option_type='CE'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_iv 
        (date, symbol, iv, spot, expiry, strike, option_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date, symbol, iv, spot, expiry, strike, option_type))
    conn.commit()
    conn.close()

def store_daily_metrics(date, symbol, iv_rank, iv_percentile, current_iv):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_metrics 
        (date, symbol, iv_rank, iv_percentile, current_iv)
        VALUES (?, ?, ?, ?, ?)
    ''', (date, symbol, iv_rank, iv_percentile, current_iv))
    conn.commit()
    conn.close()

def get_historical_ivs(symbol, days=IV_WINDOW_DAYS):
    conn = sqlite3.connect(DB_PATH)
    # Cut-off is derived in IST — the runner clock is UTC, which would shift the
    # window by a day for runs that land after midnight IST.
    cutoff_date = (now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = '''
        SELECT date, iv FROM daily_iv 
        WHERE symbol = ? AND date >= ?
        ORDER BY date DESC
    '''
    df = pd.read_sql_query(query, conn, params=(symbol, cutoff_date))
    conn.close()
    return df

def get_all_symbols():
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT DISTINCT symbol FROM daily_iv"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df['symbol'].tolist()

def get_data_coverage():
    """Return (total_days, oldest_date, newest_date) from daily_iv table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT date), MIN(date), MAX(date) FROM daily_iv")
    result = cursor.fetchone()
    conn.close()
    return result

def get_symbol_history_count(symbol):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT date) FROM daily_iv WHERE symbol = ?", (symbol,))
    result = cursor.fetchone()[0]
    conn.close()
    return result

def trim_old_data(days=TRIM_KEEP_DAYS):
    """
    Delete records older than the most recent `days` trading days.
    Keeps only the last `days` days of data for each symbol.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(date) FROM daily_iv")
    max_date = cursor.fetchone()[0]
    
    if max_date is None:
        print("No data to trim")
        conn.close()
        return
    
    cutoff = (datetime.strptime(max_date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    
    cursor.execute("DELETE FROM daily_iv WHERE date < ?", (cutoff,))
    deleted_iv = cursor.rowcount
    cursor.execute("DELETE FROM daily_metrics WHERE date < ?", (cutoff,))
    deleted_metrics = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"Trimmed {deleted_iv} IV records and {deleted_metrics} metrics records older than {cutoff}")

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "iv_history.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM daily_iv')
    total_rows = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(DISTINCT date) FROM daily_iv')
    distinct_dates = cursor.fetchone()[0]

    cursor.execute('SELECT MIN(date), MAX(date) FROM daily_iv')
    min_date, max_date = cursor.fetchone()

    cursor.execute('SELECT COUNT(DISTINCT symbol) FROM daily_iv')
    distinct_symbols = cursor.fetchone()[0]

    conn.close()

    print('=== Database Summary ===')
    print(f'Total rows:        {total_rows}')
    print(f'Distinct dates:    {distinct_dates}')
    print(f'Date range:        {min_date} to {max_date}')
    print(f'Distinct symbols:  {distinct_symbols}')

if __name__ == "__main__":
    main()
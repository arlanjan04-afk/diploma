"""Симулятор: 12 контейнеров Кокшетау + история заполнения."""
import random
from datetime import datetime, timedelta
from database import init_db, get_conn, log_event

DEPOT = {"name": "Полигон ТБО", "lat": 53.3050, "lon": 69.4200}

CONTAINERS = [
    ("K-01", "ул. Абая, 89",          53.2845, 69.3897, 1100),
    ("K-02", "ул. Ауэзова, 154",      53.2912, 69.3955, 1100),
    ("K-03", "ул. Горького, 32",      53.2798, 69.3812, 1100),
    ("K-04", "пр. Назарбаева, 47",    53.2867, 69.3934, 1100),
    ("K-05", "ул. Сатпаева, 12",      53.2756, 69.3878, 770),
    ("K-06", "ул. М. Горького, 78",   53.2823, 69.3756, 1100),
    ("K-07", "ул. Кенесары, 201",     53.2934, 69.4012, 1100),
    ("K-08", "ул. Уалиханова, 65",    53.2789, 69.3923, 770),
    ("K-09", "ул. Пушкина, 99",       53.2876, 69.3845, 1100),
    ("K-10", "ул. Темирбекова, 23",   53.2812, 69.4087, 1100),
    ("K-11", "мкр. Васильковский, 5", 53.2967, 69.3756, 1100),
    ("K-12", "ул. Гагарина, 41",      53.2734, 69.3989, 770),
]


def seed_containers():
    with get_conn() as conn:
        for name, addr, lat, lon, cap in CONTAINERS:
            conn.execute("""
                INSERT OR IGNORE INTO containers (name, address, lat, lon, capacity_liters)
                VALUES (?, ?, ?, ?, ?)
            """, (name, addr, lat, lon, cap))
    print(f"OK: containers = {len(CONTAINERS)}")


def generate_history(days: int = 30):
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM containers").fetchall()
        conn.execute("DELETE FROM fill_history")
        now = datetime.now()
        start = now - timedelta(days=days)
        total = 0
        for r in rows:
            cid = r["id"]
            rate = random.uniform(8.0, 22.0)
            fill = random.uniform(10.0, 40.0)
            ts = start
            while ts <= now:
                delta = rate * (1 / 24) * random.uniform(0.6, 1.4)
                if ts.weekday() >= 5:
                    delta *= 0.7
                fill += delta
                if fill >= 95:
                    fill = random.uniform(5, 15)
                conn.execute(
                    "INSERT INTO fill_history (container_id, timestamp, fill_percent) VALUES (?, ?, ?)",
                    (cid, ts.isoformat(timespec="seconds"), round(fill, 2))
                )
                total += 1
                ts += timedelta(hours=1)
        print(f"OK: history rows = {total}")


def add_current_reading():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT c.id,
                (SELECT fill_percent FROM fill_history
                 WHERE container_id = c.id ORDER BY timestamp DESC LIMIT 1) AS last
            FROM containers c
        """).fetchall()
        now = datetime.now().isoformat(timespec="seconds")
        for r in rows:
            cur = r["last"] if r["last"] is not None else 30.0
            new_val = cur + random.uniform(1.5, 5.0)
            if new_val >= 95:
                new_val = random.uniform(5, 15)
            conn.execute(
                "INSERT INTO fill_history (container_id, timestamp, fill_percent) VALUES (?, ?, ?)",
                (r["id"], now, round(new_val, 2))
            )


def reset_and_seed(days: int = 30):
    init_db()
    seed_containers()
    generate_history(days)
    log_event("INFO", "Simulator: data regenerated")


def main():
    print(">> init_db()")
    init_db()
    print(">> seed_containers()")
    seed_containers()
    print(">> generate_history(30)")
    generate_history(days=30)
    log_event("INFO", "Simulator: initial data generated")
    print("\nDONE. Run: python -m streamlit run app.py")


if __name__ == "__main__":
    main()


def run(days: int = 30):
    """Алиас для совместимости с app.py — генерирует данные заново."""
    return reset_and_seed(days=days)

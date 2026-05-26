"""Прогноз и история — работает с таблицей fill_history."""
import pandas as pd
from database import get_conn


def get_history(container_id=None, days=30, hours=None, **kwargs):
    """История заполнения. Поддерживает и days, и hours."""
    if container_id is None:
        return pd.DataFrame()

    # Если задан hours — конвертируем в days
    if hours is not None:
        days = max(1, hours / 24)

    with get_conn() as conn:
        df = pd.read_sql_query(
            """SELECT timestamp AS ts, fill_percent
               FROM fill_history
               WHERE container_id = ?
                 AND timestamp >= datetime('now', ?)
               ORDER BY timestamp""",
            conn,
            params=(int(container_id), f"-{int(days*24)} hours")
        )
    if df.empty:
        return df
    df['ts'] = pd.to_datetime(df['ts'])
    df['timestamp'] = df['ts']  # дублируем для совместимости
    return df


def get_history_df(container_id, hours=168):
    """Алиас для совместимости с forecast_prophet."""
    return get_history(container_id=container_id, hours=hours)

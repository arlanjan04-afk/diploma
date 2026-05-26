"""Прогноз заполнения через Prophet."""
import pandas as pd
import numpy as np
from prophet import Prophet
from datetime import datetime, timedelta
import logging
from database import get_conn

logging.getLogger('prophet').setLevel(logging.WARNING)
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)


def get_history_df(container_id, hours=168):
    """История заполнения для Prophet."""
    with get_conn() as conn:
        df = pd.read_sql_query(
            """SELECT timestamp, fill_percent
               FROM fill_history
               WHERE container_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            conn, params=(container_id, hours)
        )
    if df.empty:
        return df
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df.sort_values('timestamp').reset_index(drop=True)


def predict_with_prophet(container_id, threshold=85, forecast_hours=48):
    """
    Прогнозирует заполнение на N часов вперёд через Prophet.
    Возвращает: (часов_до_порога, текущий_уровень, прогноз_DataFrame)
    """
    df = get_history_df(container_id, hours=168)
    if len(df) < 24:
        return None, None, None

    # Берём данные с последнего цикла (после сброса)
    diffs = df['fill_percent'].diff()
    reset_indices = df.index[diffs < -20].tolist()
    if reset_indices:
        df_cycle = df.iloc[reset_indices[-1]:].reset_index(drop=True)
    else:
        df_cycle = df

    if len(df_cycle) < 10:
        return None, float(df['fill_percent'].iloc[-1]), None

    # Готовим данные для Prophet
    prophet_df = df_cycle.rename(columns={'timestamp': 'ds', 'fill_percent': 'y'})

    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.8
    )

    try:
        model.fit(prophet_df)
    except Exception as e:
        print(f"Prophet error for container {container_id}: {e}")
        return None, float(df['fill_percent'].iloc[-1]), None

    future = model.make_future_dataframe(periods=forecast_hours, freq='h')
    forecast = model.predict(future)

    current_fill = float(df_cycle['fill_percent'].iloc[-1])

    future_forecast = forecast.tail(forecast_hours).reset_index(drop=True)
    threshold_hits = future_forecast[future_forecast['yhat'] >= threshold]

    if len(threshold_hits) > 0:
        hours_to_full = int(threshold_hits.index[0]) + 1
    else:
        hours_to_full = forecast_hours

    return hours_to_full, current_fill, forecast


def get_forecast_table_prophet(threshold=85):
    """Таблица прогнозов на основе Prophet для всех контейнеров."""
    with get_conn() as conn:
        containers = pd.read_sql_query("SELECT * FROM containers", conn)

    results = []
    for _, c in containers.iterrows():
        hours_left, current, _ = predict_with_prophet(int(c['id']), threshold)

        if hours_left is None:
            hours_left = 999
        if current is None:
            current = 0

        if hours_left < 12:
            priority = 'Срочно'
        elif hours_left < 24:
            priority = 'Скоро'
        else:
            priority = 'Норма'

        results.append({
            'id': int(c['id']),
            'name': c['name'],
            'address': c['address'],
            'lat': float(c['lat']),
            'lon': float(c['lon']),
            'capacity_liters': int(c['capacity_liters']),
            'current_fill': round(float(current), 1),
            'hours_to_full': round(float(hours_left), 1),
            'priority': priority
        })

    return pd.DataFrame(results).sort_values('hours_to_full').reset_index(drop=True)


def get_containers_to_collect_prophet(hours_horizon=24, min_fill=60):
    df = get_forecast_table_prophet()
    mask = (df['hours_to_full'] <= hours_horizon) | (df['current_fill'] >= min_fill)
    return df[mask].reset_index(drop=True)

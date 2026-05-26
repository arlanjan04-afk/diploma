import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from datetime import datetime

from database import (
    init_db, get_conn,
    get_notifications, clear_notifications,
)
from forecast import get_history
from forecast_prophet import (
    get_forecast_table_prophet,
    predict_with_prophet,
)
from routing import optimize_cvrp, calculate_savings
from pdf_report import generate_route_pdf
from simulator import DEPOT
import simulator
import telegram_bot

st.set_page_config(
    page_title="Умные контейнеры | Кокшетау",
    page_icon="🗑",
    layout="wide",
)


@st.cache_data(ttl=300)
def cached_forecast():
    return get_forecast_table_prophet()


@st.cache_data(ttl=300)
def cached_prophet_predict(container_id):
    return predict_with_prophet(container_id, forecast_hours=48)


st.title("🗑 Интеллектуальная система контроля контейнеров")
st.caption("г. Кокшетау · Prophet · CVRP · PDF · Telegram")


with st.sidebar:
    st.header("⚙️ Управление")

    if st.button("🔄 Сгенерировать данные заново"):
        with st.spinner("Генерация..."):
            simulator.run()
        st.cache_data.clear()
        st.success("Данные обновлены")
        st.rerun()

    if st.button("🧹 Очистить кэш прогнозов"):
        st.cache_data.clear()
        st.success("Кэш очищен")

    st.divider()
    st.subheader("🎯 Параметры планирования")
    horizon = st.slider("Горизонт планирования (ч)", 6, 48, 24)
    min_fill = st.slider("Мин. заполнение для вывоза, %", 30, 90, 60)

    st.divider()
    st.subheader("🚛 Парк техники")
    num_vehicles = st.slider("Кол-во мусоровозов", 1, 5, 2)
    vehicle_capacity = st.number_input(
        "Ёмкость машины, л", 1000, 20000, 5000, step=500
    )

    st.divider()
    st.subheader("🤖 Telegram-бот")
    ok, status = telegram_bot.test_connection()
    if ok:
        st.success(f"✅ {status}")
    else:
        st.warning(f"⚠️ {status}")


init_db()
with get_conn() as conn:
    count = conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
if count == 0:
    with st.spinner("Первичная генерация данных..."):
        simulator.run()


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📍 Карта и состояние",
    "🚛 Маршруты (CVRP)",
    "📊 Прогноз Prophet",
    "🤖 Telegram",
    "ℹ️ О системе",
])


with tab1:
    with st.spinner("Расчёт прогнозов (Prophet)..."):
        forecast_df = cached_forecast()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего контейнеров", len(forecast_df))
    c2.metric("🔴 Срочно", (forecast_df["priority"] == "Срочно").sum())
    c3.metric("🟡 Скоро",  (forecast_df["priority"] == "Скоро").sum())
    c4.metric("🟢 Норма",  (forecast_df["priority"] == "Норма").sum())

    st.subheader("Карта контейнеров")
    m = folium.Map(location=[53.285, 69.40], zoom_start=13)
    folium.Marker(
        [DEPOT["lat"], DEPOT["lon"]],
        popup="🏢 Автобаза",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(m)

    color_map = {"Срочно": "red", "Скоро": "orange", "Норма": "green"}
    for _, row in forecast_df.iterrows():
        folium.CircleMarker(
            [row["lat"], row["lon"]],
            radius=8 + row["current_fill"] / 10,
            popup=folium.Popup(
                f"<b>{row['name']}</b><br>{row['address']}<br>"
                f"Заполнение: <b>{row['current_fill']}%</b><br>"
                f"До переполнения: {row['hours_to_full']} ч<br>"
                f"Статус: {row['priority']}",
                max_width=250,
            ),
            color=color_map[row["priority"]],
            fill=True, fillOpacity=0.7,
        ).add_to(m)

    st_folium(m, width=None, height=500, returned_objects=[])

    st.subheader("📋 Таблица контейнеров")
    st.dataframe(
        forecast_df[["name", "address", "current_fill", "hours_to_full", "priority"]],
        use_container_width=True, hide_index=True,
    )


with tab2:
    st.subheader("🚛 Оптимизация маршрутов с учётом ёмкости (CVRP)")

    forecast_df = cached_forecast()
    to_collect = forecast_df[
        (forecast_df["hours_to_full"] <= horizon) |
        (forecast_df["current_fill"] >= min_fill)
    ].reset_index(drop=True)

    if len(to_collect) == 0:
        st.info("Контейнеров для вывоза нет.")
    else:
        st.write(f"**К вывозу отобрано:** {len(to_collect)} контейнеров")

        total_volume = (to_collect["capacity_liters"] * to_collect["current_fill"] / 100).sum()
        total_fleet_capacity = num_vehicles * vehicle_capacity

        c1, c2, c3 = st.columns(3)
        c1.metric("Объём мусора", f"{int(total_volume)} л")
        c2.metric("Ёмкость парка", f"{total_fleet_capacity} л")
        c3.metric("Загрузка парка", f"{total_volume/total_fleet_capacity*100:.1f}%")

        if total_volume > total_fleet_capacity:
            st.error("⚠️ Парка недостаточно! Увеличьте число машин или ёмкость.")

        with st.spinner("Расчёт CVRP (OR-Tools)..."):
            routes, total_km = optimize_cvrp(
                to_collect,
                num_vehicles=num_vehicles,
                vehicle_capacity=vehicle_capacity,
            )
            naive_km, savings_pct = calculate_savings(to_collect, total_km)

        if not routes:
            st.error("Не удалось построить маршруты. Увеличьте ёмкость машин.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Машин задействовано", len(routes))
            c2.metric("Общий пробег", f"{total_km:.2f} км")
            c3.metric("Без оптимизации", f"{naive_km:.2f} км")
            c4.metric("💰 Экономия", f"{savings_pct:.1f}%")

            m2 = folium.Map(location=[53.285, 69.40], zoom_start=13)
            route_colors = ["blue", "red", "green", "purple", "orange"]

            folium.Marker(
                [DEPOT["lat"], DEPOT["lon"]],
                popup="🏢 Автобаза",
                icon=folium.Icon(color="black", icon="home", prefix="fa"),
            ).add_to(m2)

            for idx, route in enumerate(routes):
                color = route_colors[idx % len(route_colors)]
                coords = [(p["lat"], p["lon"]) for p in route["points"]]

                folium.PolyLine(
                    coords, color=color, weight=4, opacity=0.7,
                    tooltip=f"Мусоровоз №{route['vehicle_id']}",
                ).add_to(m2)

                counter = 0
                for p in route["points"]:
                    if p["type"] == "container":
                        counter += 1
                        folium.Marker(
                            [p["lat"], p["lon"]],
                            popup=f"М{route['vehicle_id']} · #{counter}<br>"
                                  f"{p['name']}<br>{p['address']}<br>"
                                  f"Заполнение: {p['current_fill']}%",
                            icon=folium.DivIcon(html=f"""
                                <div style="background:{color};color:white;
                                            border-radius:50%;width:30px;height:30px;
                                            text-align:center;line-height:30px;
                                            font-weight:bold;border:2px solid white;">
                                    {counter}
                                </div>
                            """),
                        ).add_to(m2)

            st_folium(m2, width=None, height=550, returned_objects=[])

            st.subheader("📋 Маршруты по машинам")
            for route in routes:
                with st.expander(
                    f"🚚 Мусоровоз №{route['vehicle_id']} · "
                    f"{route['distance_km']:.1f} км · "
                    f"загрузка {route['load_percent']}%"
                ):
                    points_table = []
                    counter = 0
                    for p in route["points"]:
                        if p["type"] == "depot":
                            points_table.append({
                                "№": "—", "Точка": "🏢 Автобаза",
                                "Адрес": p["address"],
                                "Заполнение": "—", "Объём, л": "—",
                            })
                        else:
                            counter += 1
                            points_table.append({
                                "№": counter, "Точка": p["name"],
                                "Адрес": p["address"],
                                "Заполнение": f"{p['current_fill']}%",
                                "Объём, л": p["volume_liters"],
                            })
                    st.dataframe(
                        pd.DataFrame(points_table),
                        use_container_width=True, hide_index=True,
                    )

                    col_pdf, col_tg = st.columns(2)
                    with col_pdf:
                        pdf_buffer = generate_route_pdf(
                            route, route_index=route["vehicle_id"]
                        )
                        st.download_button(
                            "📄 Скачать PDF маршрута",
                            data=pdf_buffer.getvalue(),
                            file_name=f"route_vehicle_{route['vehicle_id']}_"
                                      f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            key=f"pdf_{route['vehicle_id']}",
                        )
                    with col_tg:
                        if st.button("📤 Отправить в Telegram",
                                     key=f"tg_{route['vehicle_id']}"):
                            pdf = generate_route_pdf(
                                route, route_index=route["vehicle_id"]
                            )
                            ok, msg = telegram_bot.send_document(
                                pdf.getvalue(),
                                f"route_{route['vehicle_id']}.pdf",
                                caption=(
                                    f"🚚 Маршрут для мусоровоза №{route['vehicle_id']}\n"
                                    f"Пробег: {route['distance_km']:.1f} км\n"
                                    f"Загрузка: {route['load_percent']}%"
                                ),
                                subject="route_pdf",
                            )
                            if ok:
                                st.success("✅ Отправлено в Telegram")
                            else:
                                st.error(f"Ошибка: {msg}")


with tab3:
    st.subheader("📊 Прогноз заполнения (Facebook Prophet)")

    forecast_df = cached_forecast()
    selected = st.selectbox(
        "Выберите контейнер:",
        forecast_df["id"].tolist(),
        format_func=lambda x: (
            f"{forecast_df[forecast_df['id']==x]['name'].iloc[0]} — "
            f"{forecast_df[forecast_df['id']==x]['address'].iloc[0]}"
        ),
    )

    with st.spinner("Обучение Prophet..."):
        hours_left, current, forecast = cached_prophet_predict(selected)

    if forecast is None:
        st.warning("Недостаточно данных для прогноза.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Текущее заполнение", f"{current:.1f}%")
        c2.metric("До порога 85%", f"{hours_left} ч")
        c3.metric("Прогноз на", "48 часов")

        hist_df = get_history(selected, hours=168)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_df["timestamp"], y=hist_df["fill_percent"],
            mode="lines", name="Факт", line=dict(color="blue", width=2),
        ))

        future_part = forecast.tail(48)
        fig.add_trace(go.Scatter(
            x=future_part["ds"], y=future_part["yhat"],
            mode="lines", name="Прогноз Prophet",
            line=dict(color="red", dash="dash", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=future_part["ds"], y=future_part["yhat_upper"],
            fill=None, mode="lines", line=dict(width=0), showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=future_part["ds"], y=future_part["yhat_lower"],
            fill="tonexty", mode="lines", line=dict(width=0),
            name="Доверительный интервал 80%",
            fillcolor="rgba(255,0,0,0.15)",
        ))

        fig.add_hline(y=85, line_dash="dash", line_color="orange",
                      annotation_text="Порог вывоза (85%)")

        fig.update_layout(
            title="Заполнение и прогноз Prophet",
            xaxis_title="Дата",
            yaxis_title="Заполнение, %",
            hovermode="x unified",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.info(
            "🧠 **Prophet** раскладывает временной ряд на тренд + "
            "дневную и недельную сезонность, затем экстраполирует."
        )


with tab4:
    st.subheader("🤖 Управление уведомлениями")

    ok, status = telegram_bot.test_connection()
    if ok:
        st.success(f"✅ {status}")
    else:
        st.error(f"❌ {status}")

    st.divider()
    st.subheader("📤 Отправить уведомления")

    forecast_df = cached_forecast()
    col1, col2 = st.columns(2)

    with col1:
        st.write("**Срочные контейнеры**")
        urgent_count = (forecast_df["priority"] == "Срочно").sum()
        st.write(f"Сейчас: 🔴 {urgent_count} шт.")
        if st.button("📨 Отправить список диспетчеру", use_container_width=True):
            ok, msg = telegram_bot.notify_urgent_containers(forecast_df)
            if ok:
                st.success("✅ Сообщение отправлено")
            else:
                st.error(f"Ошибка: {msg}")

    with col2:
        st.write("**Тестовое сообщение**")
        test_msg = st.text_input("Текст:", "🧪 Проверка связи с системой")
        if st.button("📨 Отправить тест", use_container_width=True):
            ok, msg = telegram_bot.send_message(test_msg, subject="manual_test")
            if ok:
                st.success("✅ Отправлено")
            else:
                st.error(f"Ошибка: {msg}")

    st.divider()
    st.subheader("📋 Лог последних уведомлений")

    col_a, col_b, _ = st.columns([1, 1, 3])
    with col_a:
        limit = st.selectbox("Показать", [20, 50, 100, 500],
                             index=1, key="notif_limit")
    with col_b:
        if st.button("🔄 Обновить", key="notif_refresh"):
            st.rerun()

    df_notif = get_notifications(limit=limit)

    if df_notif.empty:
        st.info("Уведомлений пока нет. Отправьте тестовое сообщение выше.")
    else:
        total = len(df_notif)
        ok_cnt = int((df_notif["status"] == "ok").sum())
        err_cnt = int((df_notif["status"] == "error").sum())

        m1, m2, m3 = st.columns(3)
        m1.metric("Всего", total)
        m2.metric("✅ Успешно", ok_cnt)
        m3.metric("❌ Ошибок", err_cnt)

        show = df_notif[["ts", "channel", "status", "recipient",
                         "message", "error"]].copy()
        show.columns = ["Время", "Канал", "Статус", "Получатель",
                        "Сообщение", "Ошибка"]

        def _color_status(v):
            if v == "ok":
                return "background-color:#d4edda;color:#155724"
            if v == "error":
                return "background-color:#f8d7da;color:#721c24"
            return ""

        st.dataframe(
            show.style.map(_color_status, subset=["Статус"]),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Скачать CSV",
                show.to_csv(index=False).encode("utf-8-sig"),
                file_name="notifications.csv",
                mime="text/csv",
            )
        with c2:
            if st.button("🗑️ Очистить лог", type="secondary"):
                clear_notifications()
                st.success("Лог очищен")
                st.rerun()


with tab5:
    st.markdown("""
## ℹ️ О системе

**Интеллектуальная система контроля и прогнозирования заполнения
контейнеров для отходов** разработана для коммунальных служб
города **Кокшетау**.

### 🎯 Решаемые задачи
- 📡 Мониторинг в реальном времени
- 🧠 Прогнозирование (**Facebook Prophet**)
- 🚛 Маршруты с учётом ёмкости (**CVRP**)
- 📄 PDF маршрутные листы
- 🤖 Уведомления в **Telegram**

### 👨‍🎓 Информация о проекте
- **Студент:** [Ваше ФИО]
- **Группа:** [Группа]
- **Руководитель:** [ФИО руководителя]
- **Город:** Кокшетау, Казахстан · **Год:** 2025
""")


st.divider()
st.caption("© 2025 · Дипломная работа · г. Кокшетау")


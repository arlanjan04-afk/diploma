import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
from datetime import datetime

from database import init_db, get_conn
from forecast import get_history
from forecast_prophet import (
    get_forecast_table_prophet, 
    get_containers_to_collect_prophet,
    predict_with_prophet
)
from routing import optimize_cvrp, calculate_savings, haversine
from pdf_report import generate_route_pdf
from simulator import DEPOT
import simulator
import telegram_bot

st.set_page_config(
    page_title="РЈРјРЅС‹Рµ РєРѕРЅС‚РµР№РЅРµСЂС‹ | РљРѕРєС€РµС‚Р°Сѓ",
    page_icon="рџ—‘",
    layout="wide"
)

# ============ РљСЌС€РёСЂРѕРІР°РЅРёРµ С‚СЏР¶С‘Р»С‹С… РѕРїРµСЂР°С†РёР№ ============
@st.cache_data(ttl=300)
def cached_forecast():
    return get_forecast_table_prophet()

@st.cache_data(ttl=300)
def cached_prophet_predict(container_id):
    return predict_with_prophet(container_id, forecast_hours=48)

# ============ Р—Р°РіРѕР»РѕРІРѕРє ============
st.title("рџ—‘ РРЅС‚РµР»Р»РµРєС‚СѓР°Р»СЊРЅР°СЏ СЃРёСЃС‚РµРјР° РєРѕРЅС‚СЂРѕР»СЏ РєРѕРЅС‚РµР№РЅРµСЂРѕРІ")
st.caption("Рі. РљРѕРєС€РµС‚Р°Сѓ В· Prophet В· CVRP В· PDF В· Telegram")

# ============ РЎР°Р№РґР±Р°СЂ ============
with st.sidebar:
    st.header("вљ™пёЏ РЈРїСЂР°РІР»РµРЅРёРµ")
    
    if st.button("рџ”„ РЎРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ РґР°РЅРЅС‹Рµ Р·Р°РЅРѕРІРѕ"):
        with st.spinner("Р“РµРЅРµСЂР°С†РёСЏ..."):
            simulator.run()
        st.cache_data.clear()
        st.success("Р”Р°РЅРЅС‹Рµ РѕР±РЅРѕРІР»РµРЅС‹")
        st.rerun()
    
    if st.button("рџ§№ РћС‡РёСЃС‚РёС‚СЊ РєСЌС€ РїСЂРѕРіРЅРѕР·РѕРІ"):
        st.cache_data.clear()
        st.success("РљСЌС€ РѕС‡РёС‰РµРЅ")
    
    st.divider()
    st.subheader("рџЋЇ РџР°СЂР°РјРµС‚СЂС‹ РїР»Р°РЅРёСЂРѕРІР°РЅРёСЏ")
    horizon = st.slider("Р“РѕСЂРёР·РѕРЅС‚ РїР»Р°РЅРёСЂРѕРІР°РЅРёСЏ (С‡)", 6, 48, 24)
    min_fill = st.slider("РњРёРЅ. Р·Р°РїРѕР»РЅРµРЅРёРµ РґР»СЏ РІС‹РІРѕР·Р°, %", 30, 90, 60)
    
    st.divider()
    st.subheader("рџљ› РџР°СЂРє С‚РµС…РЅРёРєРё")
    num_vehicles = st.slider("РљРѕР»-РІРѕ РјСѓСЃРѕСЂРѕРІРѕР·РѕРІ", 1, 5, 2)
    vehicle_capacity = st.number_input(
        "РЃРјРєРѕСЃС‚СЊ РјР°С€РёРЅС‹, Р»", 1000, 20000, 5000, step=500
    )
    
    st.divider()
    st.subheader("рџ¤– Telegram-Р±РѕС‚")
    ok, status = telegram_bot.test_connection()
    if ok:
        st.success(f"вњ… {status}")
    else:
        st.warning(f"вљ пёЏ {status}")

# ============ РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ ============
init_db()
with get_conn() as conn:
    count = conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
if count == 0:
    with st.spinner("РџРµСЂРІРёС‡РЅР°СЏ РіРµРЅРµСЂР°С†РёСЏ РґР°РЅРЅС‹С…..."):
        simulator.run()

# ============ Р’РєР»Р°РґРєРё ============
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "рџ“Ќ РљР°СЂС‚Р° Рё СЃРѕСЃС‚РѕСЏРЅРёРµ",
    "рџљ› РњР°СЂС€СЂСѓС‚С‹ (CVRP)",
    "рџ“Љ РџСЂРѕРіРЅРѕР· Prophet",
    "рџ¤– Telegram",
    "в„№пёЏ Рћ СЃРёСЃС‚РµРјРµ"
])

# ---------- TAB 1: РљР°СЂС‚Р° ----------
with tab1:
    with st.spinner("Р Р°СЃС‡С‘С‚ РїСЂРѕРіРЅРѕР·РѕРІ (Prophet)..."):
        forecast_df = cached_forecast()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Р’СЃРµРіРѕ РєРѕРЅС‚РµР№РЅРµСЂРѕРІ", len(forecast_df))
    col2.metric("рџ”ґ РЎСЂРѕС‡РЅРѕ", (forecast_df['priority'] == 'РЎСЂРѕС‡РЅРѕ').sum())
    col3.metric("рџџЎ РЎРєРѕСЂРѕ", (forecast_df['priority'] == 'РЎРєРѕСЂРѕ').sum())
    col4.metric("рџџў РќРѕСЂРјР°", (forecast_df['priority'] == 'РќРѕСЂРјР°').sum())
    
    st.subheader("РљР°СЂС‚Р° РєРѕРЅС‚РµР№РЅРµСЂРѕРІ")
    m = folium.Map(location=[53.285, 69.40], zoom_start=13)
    folium.Marker(
        [DEPOT['lat'], DEPOT['lon']],
        popup="рџЏў РђРІС‚РѕР±Р°Р·Р°",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)
    
    color_map = {'РЎСЂРѕС‡РЅРѕ': 'red', 'РЎРєРѕСЂРѕ': 'orange', 'РќРѕСЂРјР°': 'green'}
    for _, row in forecast_df.iterrows():
        folium.CircleMarker(
            [row['lat'], row['lon']],
            radius=8 + row['current_fill'] / 10,
            popup=folium.Popup(
                f"<b>{row['name']}</b><br>{row['address']}<br>"
                f"Р—Р°РїРѕР»РЅРµРЅРёРµ: <b>{row['current_fill']}%</b><br>"
                f"Р”Рѕ РїРµСЂРµРїРѕР»РЅРµРЅРёСЏ: {row['hours_to_full']} С‡<br>"
                f"РЎС‚Р°С‚СѓСЃ: {row['priority']}",
                max_width=250
            ),
            color=color_map[row['priority']],
            fill=True, fillOpacity=0.7
        ).add_to(m)
    
    st_folium(m, width=None, height=500, returned_objects=[])
    
    st.subheader("рџ“‹ РўР°Р±Р»РёС†Р° РєРѕРЅС‚РµР№РЅРµСЂРѕРІ")
    st.dataframe(
        forecast_df[['name', 'address', 'current_fill', 'hours_to_full', 'priority']],
        use_container_width=True, hide_index=True
    )

# ---------- TAB 2: CVRP-РјР°СЂС€СЂСѓС‚С‹ ----------
with tab2:
    st.subheader("рџљ› РћРїС‚РёРјРёР·Р°С†РёСЏ РјР°СЂС€СЂСѓС‚РѕРІ СЃ СѓС‡С‘С‚РѕРј С‘РјРєРѕСЃС‚Рё (CVRP)")
    
    forecast_df = cached_forecast()
    to_collect = forecast_df[
        (forecast_df['hours_to_full'] <= horizon) | 
        (forecast_df['current_fill'] >= min_fill)
    ].reset_index(drop=True)
    
    if len(to_collect) == 0:
        st.info("РљРѕРЅС‚РµР№РЅРµСЂРѕРІ РґР»СЏ РІС‹РІРѕР·Р° РЅРµС‚.")
    else:
        st.write(f"**Рљ РІС‹РІРѕР·Сѓ РѕС‚РѕР±СЂР°РЅРѕ:** {len(to_collect)} РєРѕРЅС‚РµР№РЅРµСЂРѕРІ")
        
        total_volume = (to_collect['capacity_liters'] * to_collect['current_fill'] / 100).sum()
        total_fleet_capacity = num_vehicles * vehicle_capacity
        
        c1, c2, c3 = st.columns(3)
        c1.metric("РћР±СЉС‘Рј РјСѓСЃРѕСЂР°", f"{int(total_volume)} Р»")
        c2.metric("РЃРјРєРѕСЃС‚СЊ РїР°СЂРєР°", f"{total_fleet_capacity} Р»")
        c3.metric("Р—Р°РіСЂСѓР·РєР° РїР°СЂРєР°", f"{total_volume/total_fleet_capacity*100:.1f}%")
        
        if total_volume > total_fleet_capacity:
            st.error(f"вљ пёЏ РџР°СЂРєР° РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ! РЈРІРµР»РёС‡СЊС‚Рµ С‡РёСЃР»Рѕ РјР°С€РёРЅ РёР»Рё С‘РјРєРѕСЃС‚СЊ.")
        
        with st.spinner("Р Р°СЃС‡С‘С‚ CVRP (OR-Tools)..."):
            routes, total_km = optimize_cvrp(
                to_collect, 
                num_vehicles=num_vehicles, 
                vehicle_capacity=vehicle_capacity
            )
            naive_km, savings_pct = calculate_savings(to_collect, total_km)
        
        if not routes:
            st.error("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕСЃС‚СЂРѕРёС‚СЊ РјР°СЂС€СЂСѓС‚С‹. РЈРІРµР»РёС‡СЊС‚Рµ С‘РјРєРѕСЃС‚СЊ РјР°С€РёРЅ.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("РњР°С€РёРЅ Р·Р°РґРµР№СЃС‚РІРѕРІР°РЅРѕ", len(routes))
            c2.metric("РћР±С‰РёР№ РїСЂРѕР±РµРі", f"{total_km:.2f} РєРј")
            c3.metric("Р‘РµР· РѕРїС‚РёРјРёР·Р°С†РёРё", f"{naive_km:.2f} РєРј")
            c4.metric("рџ’° Р­РєРѕРЅРѕРјРёСЏ", f"{savings_pct:.1f}%")
            
            # РљР°СЂС‚Р° СЃРѕ РІСЃРµРјРё РјР°СЂС€СЂСѓС‚Р°РјРё СЂР°Р·РЅС‹С… С†РІРµС‚РѕРІ
            m2 = folium.Map(location=[53.285, 69.40], zoom_start=13)
            route_colors = ['blue', 'red', 'green', 'purple', 'orange']
            
            folium.Marker(
                [DEPOT['lat'], DEPOT['lon']],
                popup="рџЏў РђРІС‚РѕР±Р°Р·Р°",
                icon=folium.Icon(color="black", icon="home", prefix="fa")
            ).add_to(m2)
            
            for idx, route in enumerate(routes):
                color = route_colors[idx % len(route_colors)]
                coords = [(p['lat'], p['lon']) for p in route['points']]
                
                folium.PolyLine(
                    coords, color=color, weight=4, opacity=0.7,
                    tooltip=f"РњСѓСЃРѕСЂРѕРІРѕР· в„–{route['vehicle_id']}"
                ).add_to(m2)
                
                counter = 0
                for p in route['points']:
                    if p['type'] == 'container':
                        counter += 1
                        folium.Marker(
                            [p['lat'], p['lon']],
                            popup=f"Рњ{route['vehicle_id']} В· #{counter}<br>"
                                  f"{p['name']}<br>{p['address']}<br>"
                                  f"Р—Р°РїРѕР»РЅРµРЅРёРµ: {p['current_fill']}%",
                            icon=folium.DivIcon(html=f"""
                                <div style="background:{color};color:white;
                                            border-radius:50%;width:30px;height:30px;
                                            text-align:center;line-height:30px;
                                            font-weight:bold;border:2px solid white;">
                                    {counter}
                                </div>
                            """)
                        ).add_to(m2)
            
            st_folium(m2, width=None, height=550, returned_objects=[])
            
            # Р”РµС‚Р°Р»Рё РїРѕ РєР°Р¶РґРѕР№ РјР°С€РёРЅРµ
            st.subheader("рџ“‹ РњР°СЂС€СЂСѓС‚С‹ РїРѕ РјР°С€РёРЅР°Рј")
            for route in routes:
                with st.expander(
                    f"рџљљ РњСѓСЃРѕСЂРѕРІРѕР· в„–{route['vehicle_id']} В· "
                    f"{route['distance_km']:.1f} РєРј В· "
                    f"Р·Р°РіСЂСѓР·РєР° {route['load_percent']}%"
                ):
                    points_table = []
                    counter = 0
                    for p in route['points']:
                        if p['type'] == 'depot':
                            points_table.append({
                                'в„–': 'вЂ”', 'РўРѕС‡РєР°': 'рџЏў РђРІС‚РѕР±Р°Р·Р°',
                                'РђРґСЂРµСЃ': p['address'],
                                'Р—Р°РїРѕР»РЅРµРЅРёРµ': 'вЂ”', 'РћР±СЉС‘Рј, Р»': 'вЂ”'
                            })
                        else:
                            counter += 1
                            points_table.append({
                                'в„–': counter, 'РўРѕС‡РєР°': p['name'],
                                'РђРґСЂРµСЃ': p['address'],
                                'Р—Р°РїРѕР»РЅРµРЅРёРµ': f"{p['current_fill']}%",
                                'РћР±СЉС‘Рј, Р»': p['volume_liters']
                            })
                    st.dataframe(pd.DataFrame(points_table), 
                                 use_container_width=True, hide_index=True)
                    
                    # PDF Рё Telegram РєРЅРѕРїРєРё
                    col_pdf, col_tg = st.columns(2)
                    
                    with col_pdf:
                        pdf_buffer = generate_route_pdf(
                            route, route_index=route['vehicle_id']
                        )
                        st.download_button(
                            "рџ“„ РЎРєР°С‡Р°С‚СЊ PDF РјР°СЂС€СЂСѓС‚Р°",
                            data=pdf_buffer.getvalue(),
                            file_name=f"route_vehicle_{route['vehicle_id']}_"
                                      f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            key=f"pdf_{route['vehicle_id']}"
                        )
                    
                    with col_tg:
                        if st.button(
                            f"рџ“¤ РћС‚РїСЂР°РІРёС‚СЊ РІ Telegram",
                            key=f"tg_{route['vehicle_id']}"
                        ):
                            pdf = generate_route_pdf(route, route_index=route['vehicle_id'])
                            ok, msg = telegram_bot.send_document(
                                pdf.getvalue(),
                                f"route_{route['vehicle_id']}.pdf",
                                caption=f"рџљљ РњР°СЂС€СЂСѓС‚ РґР»СЏ РјСѓСЃРѕСЂРѕРІРѕР·Р° в„–{route['vehicle_id']}\n"
                                        f"РџСЂРѕР±РµРі: {route['distance_km']:.1f} РєРј\n"
                                        f"Р—Р°РіСЂСѓР·РєР°: {route['load_percent']}%"
                            )
                            if ok:
                                st.success("вњ… РћС‚РїСЂР°РІР»РµРЅРѕ РІ Telegram")
                            else:
                                st.error(f"РћС€РёР±РєР°: {msg}")

# ---------- TAB 3: Prophet РїСЂРѕРіРЅРѕР· ----------
with tab3:
    st.subheader("рџ“Љ РџСЂРѕРіРЅРѕР· Р·Р°РїРѕР»РЅРµРЅРёСЏ (Facebook Prophet)")
    
    forecast_df = cached_forecast()
    selected = st.selectbox(
        "Р’С‹Р±РµСЂРёС‚Рµ РєРѕРЅС‚РµР№РЅРµСЂ:",
        forecast_df['id'].tolist(),
        format_func=lambda x: f"{forecast_df[forecast_df['id']==x]['name'].iloc[0]} вЂ” "
                              f"{forecast_df[forecast_df['id']==x]['address'].iloc[0]}"
    )
    
    with st.spinner("РћР±СѓС‡РµРЅРёРµ Prophet..."):
        hours_left, current, forecast = cached_prophet_predict(selected)
    
    if forecast is None:
        st.warning("РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ РїСЂРѕРіРЅРѕР·Р°.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("РўРµРєСѓС‰РµРµ Р·Р°РїРѕР»РЅРµРЅРёРµ", f"{current:.1f}%")
        c2.metric("Р”Рѕ РїРѕСЂРѕРіР° 85%", f"{hours_left} С‡")
        c3.metric("РџСЂРѕРіРЅРѕР· РЅР°", "48 С‡Р°СЃРѕРІ")
        
        # Р“СЂР°С„РёРє: РёСЃС‚РѕСЂРёСЏ + РїСЂРѕРіРЅРѕР· + РґРѕРІРµСЂРёС‚РµР»СЊРЅС‹Р№ РёРЅС‚РµСЂРІР°Р»
        hist_df = get_history(selected, hours=168)
        
        import plotly.graph_objects as go
        fig = go.Figure()
        
        # РСЃС‚РѕСЂРёС‡РµСЃРєРѕРµ Р·Р°РїРѕР»РЅРµРЅРёРµ
        fig.add_trace(go.Scatter(
            x=hist_df['timestamp'], y=hist_df['fill_percent'],
            mode='lines', name='Р¤Р°РєС‚', line=dict(color='blue', width=2)
        ))
        
        # РџСЂРѕРіРЅРѕР·
        future_part = forecast.tail(48)
        fig.add_trace(go.Scatter(
            x=future_part['ds'], y=future_part['yhat'],
            mode='lines', name='РџСЂРѕРіРЅРѕР· Prophet',
            line=dict(color='red', dash='dash', width=2)
        ))
        
        # Р”РѕРІРµСЂРёС‚РµР»СЊРЅС‹Р№ РёРЅС‚РµСЂРІР°Р»
        fig.add_trace(go.Scatter(
            x=future_part['ds'], y=future_part['yhat_upper'],
            fill=None, mode='lines', line=dict(width=0), showlegend=False
        ))
        fig.add_trace(go.Scatter(
            x=future_part['ds'], y=future_part['yhat_lower'],
            fill='tonexty', mode='lines', line=dict(width=0),
            name='Р”РѕРІРµСЂРёС‚РµР»СЊРЅС‹Р№ РёРЅС‚РµСЂРІР°Р» 80%',
            fillcolor='rgba(255,0,0,0.15)'
        ))
        
        # РџРѕСЂРѕРі
        fig.add_hline(y=85, line_dash="dash", line_color="orange",
                      annotation_text="РџРѕСЂРѕРі РІС‹РІРѕР·Р° (85%)")
        
        fig.update_layout(
            title=f"Р—Р°РїРѕР»РЅРµРЅРёРµ Рё РїСЂРѕРіРЅРѕР· Prophet",
            xaxis_title="Р”Р°С‚Р°",
            yaxis_title="Р—Р°РїРѕР»РЅРµРЅРёРµ, %",
            hovermode='x unified',
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.info(
            "рџ§  **РљР°Рє СЂР°Р±РѕС‚Р°РµС‚ Prophet:** РјРѕРґРµР»СЊ СЂР°СЃРєР»Р°РґС‹РІР°РµС‚ РІСЂРµРјРµРЅРЅРѕР№ "
            "СЂСЏРґ РЅР° С‚СЂРµРЅРґ + РґРЅРµРІРЅСѓСЋ Рё РЅРµРґРµР»СЊРЅСѓСЋ СЃРµР·РѕРЅРЅРѕСЃС‚СЊ, Р·Р°С‚РµРј "
            "СЌРєСЃС‚СЂР°РїРѕР»РёСЂСѓРµС‚. Р”РѕРІРµСЂРёС‚РµР»СЊРЅС‹Р№ РёРЅС‚РµСЂРІР°Р» РїРѕРєР°Р·С‹РІР°РµС‚ "
            "РЅРµРѕРїСЂРµРґРµР»С‘РЅРЅРѕСЃС‚СЊ РїСЂРѕРіРЅРѕР·Р°."
        )

# ---------- TAB 4: Telegram ----------
with tab4:
    st.subheader("рџ¤– РЈРїСЂР°РІР»РµРЅРёРµ СѓРІРµРґРѕРјР»РµРЅРёСЏРјРё")
    
    ok, status = telegram_bot.test_connection()
    if ok:
        st.success(f"вњ… {status}")
    else:
        st.error(f"вќЊ {status}")
        st.markdown("""
        **РќР°СЃС‚СЂРѕР№РєР° Р±РѕС‚Р°:**
        1. РЎРѕР·РґР°Р№С‚Рµ Р±РѕС‚Р° С‡РµСЂРµР· [@BotFather](https://t.me/BotFather) вЂ” РєРѕРјР°РЅРґР° `/newbot`
        2. РџРѕР»СѓС‡РёС‚Рµ С‚РѕРєРµРЅ
        3. РќР°РїРёС€РёС‚Рµ Р±РѕС‚Сѓ Р»СЋР±РѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
        4. РћС‚РєСЂРѕР№С‚Рµ `https://api.telegram.org/bot<РўРћРљР•Рќ>/getUpdates` Рё РЅР°Р№РґРёС‚Рµ СЃРІРѕР№ `chat_id`
        5. РЎРѕР·РґР°Р№С‚Рµ С„Р°Р№Р» `.env` РІ РєРѕСЂРЅРµ РїСЂРѕРµРєС‚Р°:
        ```
        TELEGRAM_BOT_TOKEN=РІР°С€_С‚РѕРєРµРЅ
        TELEGRAM_CHAT_ID=РІР°С€_chat_id
        ```
        6. РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚Рµ Streamlit
        """)
    
    st.divider()
    st.subheader("рџ“¤ РћС‚РїСЂР°РІРёС‚СЊ СѓРІРµРґРѕРјР»РµРЅРёСЏ")
    
    forecast_df = cached_forecast()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**РЎСЂРѕС‡РЅС‹Рµ РєРѕРЅС‚РµР№РЅРµСЂС‹**")
        urgent_count = (forecast_df['priority'] == 'РЎСЂРѕС‡РЅРѕ').sum()
        st.write(f"РЎРµР№С‡Р°СЃ: рџ”ґ {urgent_count} С€С‚.")
        if st.button("рџ“Ё РћС‚РїСЂР°РІРёС‚СЊ СЃРїРёСЃРѕРє РґРёСЃРїРµС‚С‡РµСЂСѓ", use_container_width=True):
            ok, msg = telegram_bot.notify_urgent_containers(forecast_df)
            if ok:
                st.success("вњ… РЎРѕРѕР±С‰РµРЅРёРµ РѕС‚РїСЂР°РІР»РµРЅРѕ")
            else:
                st.error(f"РћС€РёР±РєР°: {msg}")
    
    with col2:
        st.write("**РўРµСЃС‚РѕРІРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ**")
        test_msg = st.text_input("РўРµРєСЃС‚:", "рџ§Є РџСЂРѕРІРµСЂРєР° СЃРІСЏР·Рё СЃ СЃРёСЃС‚РµРјРѕР№")
        if st.button("рџ“Ё РћС‚РїСЂР°РІРёС‚СЊ С‚РµСЃС‚", use_container_width=True):
            ok, msg = telegram_bot.send_message(test_msg)
            if ok:
                st.success("вњ… РћС‚РїСЂР°РІР»РµРЅРѕ")
            else:
                st.error(f"РћС€РёР±РєР°: {msg}")
    
    st.divider()
    st.subheader("рџ“‹ Р›РѕРі РїРѕСЃР»РµРґРЅРёС… СѓРІРµРґРѕРјР»РµРЅРёР№")
    st.caption("Р’ СЌС‚РѕР№ РІРµСЂСЃРёРё Р»РѕРі РЅРµ СЃРѕС…СЂР°РЅСЏРµС‚СЃСЏ. РњРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ С‚Р°Р±Р»РёС†Сѓ `notifications` РІ Р‘Р”.")

# ---------- TAB 5: Рћ СЃРёСЃС‚РµРјРµ ----------
with tab5:
    st.markdown("""
    ## в„№пёЏ Рћ СЃРёСЃС‚РµРјРµ
    
    **РРЅС‚РµР»Р»РµРєС‚СѓР°Р»СЊРЅР°СЏ СЃРёСЃС‚РµРјР° РєРѕРЅС‚СЂРѕР»СЏ Рё РїСЂРѕРіРЅРѕР·РёСЂРѕРІР°РЅРёСЏ Р·Р°РїРѕР»РЅРµРЅРёСЏ 
    РєРѕРЅС‚РµР№РЅРµСЂРѕРІ РґР»СЏ РѕС‚С…РѕРґРѕРІ** СЂР°Р·СЂР°Р±РѕС‚Р°РЅР° РґР»СЏ РєРѕРјРјСѓРЅР°Р»СЊРЅС‹С… СЃР»СѓР¶Р± 
    РіРѕСЂРѕРґР° **РљРѕРєС€РµС‚Р°Сѓ**.
    
    ### рџЋЇ Р РµС€Р°РµРјС‹Рµ Р·Р°РґР°С‡Рё
    - рџ“Ў РњРѕРЅРёС‚РѕСЂРёРЅРі СЃРѕСЃС‚РѕСЏРЅРёСЏ РєРѕРЅС‚РµР№РЅРµСЂРѕРІ РІ СЂРµР°Р»СЊРЅРѕРј РІСЂРµРјРµРЅРё
    - рџ§  РџСЂРѕРіРЅРѕР·РёСЂРѕРІР°РЅРёРµ РїРµСЂРµРїРѕР»РЅРµРЅРёСЏ СЃ РїРѕРјРѕС‰СЊСЋ ML (**Facebook Prophet**)
    - рџљ› РџРѕСЃС‚СЂРѕРµРЅРёРµ РѕРїС‚РёРјР°Р»СЊРЅС‹С… РјР°СЂС€СЂСѓС‚РѕРІ РІС‹РІРѕР·Р° СЃ СѓС‡С‘С‚РѕРј С‘РјРєРѕСЃС‚Рё РјР°С€РёРЅ (**CVRP**)
    - рџ“„ РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРѕРµ С„РѕСЂРјРёСЂРѕРІР°РЅРёРµ РјР°СЂС€СЂСѓС‚РЅС‹С… Р»РёСЃС‚РѕРІ (**PDF**)
    - рџ¤– РЈРІРµРґРѕРјР»РµРЅРёСЏ РґРёСЃРїРµС‚С‡РµСЂР° Рё РІРѕРґРёС‚РµР»РµР№ С‡РµСЂРµР· **Telegram-Р±РѕС‚**
    - рџ’° РЎРѕРєСЂР°С‰РµРЅРёРµ РїСЂРѕР±РµРіР° Рё СЂР°СЃС…РѕРґР° С‚РѕРїР»РёРІР° РЅР° **20вЂ“40%**
    
    ### рџ›  РЎС‚РµРє С‚РµС…РЅРѕР»РѕРіРёР№
    
    | РљРѕРјРїРѕРЅРµРЅС‚ | РўРµС…РЅРѕР»РѕРіРёСЏ | РќР°Р·РЅР°С‡РµРЅРёРµ |
    |---|---|---|
    | Р‘Р°Р·Р° РґР°РЅРЅС‹С… | SQLite | РҐСЂР°РЅРµРЅРёРµ РґР°С‚С‡РёРєРѕРІ Рё РёСЃС‚РѕСЂРёРё |
    | РџСЂРѕРіРЅРѕР· | **Facebook Prophet** | Р’СЂРµРјРµРЅРЅС‹Рµ СЂСЏРґС‹ СЃ СЃРµР·РѕРЅРЅРѕСЃС‚СЊСЋ |
    | РћРїС‚РёРјРёР·Р°С†РёСЏ РјР°СЂС€СЂСѓС‚РѕРІ | **Google OR-Tools (CVRP)** | РќРµСЃРєРѕР»СЊРєРѕ РјР°С€РёРЅ + С‘РјРєРѕСЃС‚СЊ |
    | Р Р°СЃС‡С‘С‚ СЂР°СЃСЃС‚РѕСЏРЅРёР№ | Haversine formula | Р“РµРѕРґРµР·РёС‡РµСЃРєРёРµ РґРёСЃС‚Р°РЅС†РёРё |
    | РљР°СЂС‚С‹ | Folium / OpenStreetMap | Р’РёР·СѓР°Р»РёР·Р°С†РёСЏ РјР°СЂС€СЂСѓС‚РѕРІ |
    | Р’РµР±-РёРЅС‚РµСЂС„РµР№СЃ | Streamlit | РџР°РЅРµР»СЊ РґРёСЃРїРµС‚С‡РµСЂР° |
    | PDF-РѕС‚С‡С‘С‚С‹ | ReportLab | РњР°СЂС€СЂСѓС‚РЅС‹Рµ Р»РёСЃС‚С‹ |
    | РЈРІРµРґРѕРјР»РµРЅРёСЏ | Telegram Bot API | РњРѕР±РёР»СЊРЅС‹Р№ РєР°РЅР°Р» СЃРІСЏР·Рё |
    | РЎРёРјСѓР»СЏС†РёСЏ | NumPy | Р­РјСѓР»СЏС†РёСЏ РґР°С‚С‡РёРєРѕРІ |
    
    ### рџ§  РђР»РіРѕСЂРёС‚Рј СЂР°Р±РѕС‚С‹ СЃРёСЃС‚РµРјС‹
    
    1. **РЎР±РѕСЂ РґР°РЅРЅС‹С….** Р”Р°С‚С‡РёРєРё (РІ РїСЂРѕРµРєС‚Рµ СЌРјСѓР»РёСЂСѓСЋС‚СЃСЏ) РєР°Р¶РґС‹Р№ С‡Р°СЃ
       РїРµСЂРµРґР°СЋС‚ СѓСЂРѕРІРµРЅСЊ Р·Р°РїРѕР»РЅРµРЅРёСЏ РІ Р‘Р” SQLite. РЎРёРјСѓР»СЏС‚РѕСЂ СѓС‡РёС‚С‹РІР°РµС‚
       РїРѕС‡Р°СЃРѕРІС‹Рµ РєРѕР»РµР±Р°РЅРёСЏ, РІС‹С…РѕРґРЅС‹Рµ Рё РёРЅРґРёРІРёРґСѓР°Р»СЊРЅСѓСЋ СЃРєРѕСЂРѕСЃС‚СЊ
       РЅР°РїРѕР»РЅРµРЅРёСЏ РєР°Р¶РґРѕРіРѕ РєРѕРЅС‚РµР№РЅРµСЂР°.
    
    2. **РџСЂРѕРіРЅРѕР·РёСЂРѕРІР°РЅРёРµ (Prophet).** Р”Р»СЏ РєР°Р¶РґРѕРіРѕ РєРѕРЅС‚РµР№РЅРµСЂР° РѕР±СѓС‡Р°РµС‚СЃСЏ
       Р°РґРґРёС‚РёРІРЅР°СЏ РјРѕРґРµР»СЊ:
       
       *y(t) = g(t) + s(t) + Оµ*
       
       РіРґРµ **g(t)** вЂ” С‚СЂРµРЅРґ, **s(t)** вЂ” СЃСѓС‚РѕС‡РЅР°СЏ Рё РЅРµРґРµР»СЊРЅР°СЏ
       СЃРµР·РѕРЅРЅРѕСЃС‚СЊ, **Оµ** вЂ” С€СѓРј. РњРѕРґРµР»СЊ СЌРєСЃС‚СЂР°РїРѕР»РёСЂСѓРµС‚ РЅР° 48 С‡Р°СЃРѕРІ
       Рё РѕРїСЂРµРґРµР»СЏРµС‚ РјРѕРјРµРЅС‚ РїРµСЂРµСЃРµС‡РµРЅРёСЏ РїРѕСЂРѕРіР° 85%.
    
    3. **РћС‚Р±РѕСЂ РєРѕРЅС‚РµР№РЅРµСЂРѕРІ.** Р’ РїР»Р°РЅ РІС‹РІРѕР·Р° РїРѕРїР°РґР°СЋС‚ РєРѕРЅС‚РµР№РЅРµСЂС‹,
       РєРѕС‚РѕСЂС‹Рµ РїРµСЂРµРїРѕР»РЅСЏС‚СЃСЏ РІ Р±Р»РёР¶Р°Р№С€РёРµ N С‡Р°СЃРѕРІ Р»РёР±Рѕ СѓР¶Рµ РїСЂРµРІС‹СЃРёР»Рё
       РјРёРЅРёРјР°Р»СЊРЅС‹Р№ РїРѕСЂРѕРі Р·Р°РїРѕР»РЅРµРЅРёСЏ.
    
    4. **РћРїС‚РёРјРёР·Р°С†РёСЏ РјР°СЂС€СЂСѓС‚РѕРІ (CVRP).** Р—Р°РґР°С‡Р°:
       - **Р”Р°РЅРѕ:** РґРµРїРѕ, N РєРѕРЅС‚РµР№РЅРµСЂРѕРІ, M РјСѓСЃРѕСЂРѕРІРѕР·РѕРІ, С‘РјРєРѕСЃС‚СЊ Q.
       - **РќР°Р№С‚Рё:** СЂР°Р·Р±РёРµРЅРёРµ С‚РѕС‡РµРє РїРѕ РјР°С€РёРЅР°Рј Рё РїРѕСЂСЏРґРѕРє РѕР±СЉРµР·РґР° С‚Р°Рє,
         С‡С‚РѕР±С‹ СЃСѓРјРјР°СЂРЅС‹Р№ РїСЂРѕР±РµРі Р±С‹Р» РјРёРЅРёРјР°Р»СЊРЅС‹Рј, Р° Р·Р°РіСЂСѓР·РєР° РєР°Р¶РґРѕР№
         РјР°С€РёРЅС‹ в‰¤ Q.
       - **Р РµС€РµРЅРёРµ:** Р°Р»РіРѕСЂРёС‚Рј Guided Local Search РІ OR-Tools
         (РјРµС‚Р°СЌРІСЂРёСЃС‚РёРєР° СЃ Р»РѕРєР°Р»СЊРЅС‹Рј РїРѕРёСЃРєРѕРј Рё С€С‚СЂР°С„Р°РјРё).
    
    5. **Р”РѕСЃС‚Р°РІРєР° РїР»Р°РЅР°.** Р”РёСЃРїРµС‚С‡РµСЂ РїРѕР»СѓС‡Р°РµС‚ СѓРІРµРґРѕРјР»РµРЅРёРµ РІ Telegram
       Рё PDF РјР°СЂС€СЂСѓС‚РЅС‹Р№ Р»РёСЃС‚ РґР»СЏ РєР°Р¶РґРѕРіРѕ РІРѕРґРёС‚РµР»СЏ. Р’РѕРґРёС‚РµР»СЊ РІРёРґРёС‚
       РїРѕСЃР»РµРґРѕРІР°С‚РµР»СЊРЅРѕСЃС‚СЊ С‚РѕС‡РµРє, Р°РґСЂРµСЃР° Рё РѕР±СЉС‘Рј РјСѓСЃРѕСЂР° РІ РєР°Р¶РґРѕРј.
    
    ### рџ“€ Р­С„С„РµРєС‚ РѕС‚ РІРЅРµРґСЂРµРЅРёСЏ
    
    | РџРѕРєР°Р·Р°С‚РµР»СЊ | Р”Рѕ | РџРѕСЃР»Рµ | Р­РєРѕРЅРѕРјРёСЏ |
    |---|---|---|---|
    | РџСЂРѕР±РµРі Р·Р° СЃРјРµРЅСѓ | ~80 РєРј | ~50 РєРј | **~37%** |
    | Р Р°СЃС…РѕРґ С‚РѕРїР»РёРІР° | 32 Р» | 20 Р» | **~37%** |
    | Р–Р°Р»РѕР± РЅР° РїРµСЂРµРїРѕР»РЅРµРЅРёРµ | РјРЅРѕРіРѕ | СЂРµРґРєРѕ | **РІ СЂР°Р·С‹** |
    | Р’СЂРµРјСЏ РґРёСЃРїРµС‚С‡РµСЂР° | 1вЂ“2 С‡ | 5 РјРёРЅ | **РІ 12 СЂР°Р·** |
    | Р’С‹Р±СЂРѕСЃС‹ COв‚‚ | Р±Р°Р·РѕРІС‹Рµ | в€’37% | **Р·РЅР°С‡РёС‚РµР»СЊРЅРѕРµ** |
    
    ### рџ”Њ Р Р°Р·РІРёС‚РёРµ РїСЂРѕРµРєС‚Р° (РїСЂРѕРјС‹С€Р»РµРЅРЅР°СЏ РІРµСЂСЃРёСЏ)
    
    - **РђРїРїР°СЂР°С‚РЅР°СЏ С‡Р°СЃС‚СЊ:** СѓР»СЊС‚СЂР°Р·РІСѓРєРѕРІС‹Рµ РґР°С‚С‡РёРєРё HC-SR04 РёР»Рё ToF VL53L0X
      РЅР° Р±Р°Р·Рµ ESP32 СЃ РїРёС‚Р°РЅРёРµРј РѕС‚ Li-Ion Р°РєРєСѓРјСѓР»СЏС‚РѕСЂР° + СЃРѕР»РЅРµС‡РЅРѕР№ РїР°РЅРµР»Рё.
    - **РџРµСЂРµРґР°С‡Р° РґР°РЅРЅС‹С…:** MQTT РїРѕРІРµСЂС… NB-IoT РёР»Рё LoRaWAN вЂ”
      РЅРёР·РєРѕРµ СЌРЅРµСЂРіРѕРїРѕС‚СЂРµР±Р»РµРЅРёРµ, РїРѕРєСЂС‹С‚РёРµ РґРѕ 10 РєРј.
    - **Backend:** FastAPI + PostgreSQL + Redis РґР»СЏ РѕС‡РµСЂРµРґРё Р·Р°РґР°С‡.
    - **РџСЂРѕРіРЅРѕР·:** Prophet в†’ LSTM/Transformer РґР»СЏ Р±РѕР»РµРµ РґР»РёРЅРЅС‹С…
      РіРѕСЂРёР·РѕРЅС‚РѕРІ Рё СѓС‡С‘С‚Р° РІРЅРµС€РЅРёС… С„Р°РєС‚РѕСЂРѕРІ (РїСЂР°Р·РґРЅРёРєРё, РїРѕРіРѕРґР°).
    - **РњР°СЂС€СЂСѓС‚РёР·Р°С†РёСЏ:** РёРЅС‚РµРіСЂР°С†РёСЏ СЃ **OSRM** РёР»Рё **Yandex Routing API**
      РґР»СЏ СЂР°СЃС‡С‘С‚Р° РїРѕ СЂРµР°Р»СЊРЅС‹Рј РґРѕСЂРѕРіР°Рј РљРѕРєС€РµС‚Р°Сѓ, Р° РЅРµ РїРѕ РїСЂСЏРјРѕР№.
    - **РњРѕР±РёР»СЊРЅРѕРµ РїСЂРёР»РѕР¶РµРЅРёРµ** РґР»СЏ РІРѕРґРёС‚РµР»СЏ СЃ РЅР°РІРёРіР°С†РёРµР№ Рё
      РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµРј РІС‹РІРѕР·Р° РєР°Р¶РґРѕР№ С‚РѕС‡РєРё.
    - **РђРЅР°Р»РёС‚РёС‡РµСЃРєРёР№ РґР°С€Р±РѕСЂРґ** РґР»СЏ РіРѕСЂРѕРґСЃРєРѕР№ Р°РґРјРёРЅРёСЃС‚СЂР°С†РёРё:
      СЃС‚Р°С‚РёСЃС‚РёРєР° РїРѕ СЂР°Р№РѕРЅР°Рј, KPI РїРѕРґСЂСЏРґС‡РёРєРѕРІ, РїСЂРѕРіРЅРѕР· Р±СЋРґР¶РµС‚Р°.
    
    ### рџ‘ЁвЂЌрџЋ“ РРЅС„РѕСЂРјР°С†РёСЏ Рѕ РїСЂРѕРµРєС‚Рµ
    
    - **РЎС‚СѓРґРµРЅС‚:** [Р’Р°С€Рµ Р¤РРћ]
    - **Р“СЂСѓРїРїР°:** [Р“СЂСѓРїРїР°]
    - **Р СѓРєРѕРІРѕРґРёС‚РµР»СЊ:** [Р¤РРћ СЂСѓРєРѕРІРѕРґРёС‚РµР»СЏ]
    - **Р“РѕСЂРѕРґ:** РљРѕРєС€РµС‚Р°Сѓ, РљР°Р·Р°С…СЃС‚Р°РЅ
    - **Р“РѕРґ:** 2025
    """)

st.divider()
st.caption(
    "В© 2025 В· Р”РёРїР»РѕРјРЅР°СЏ СЂР°Р±РѕС‚Р° В· Рі. РљРѕРєС€РµС‚Р°Сѓ В· "
    "Prophet + OR-Tools (CVRP) + ReportLab + Telegram Bot API"
)

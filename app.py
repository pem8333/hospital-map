import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import os
import random
import json
from datetime import datetime, timedelta, timezone

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="대한민국 환자경험 지도(PX Map)", layout="wide", initial_sidebar_state="expanded")

# --- 기본 메뉴 및 헤더 숨기기 ---
hide_menu_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_menu_style, unsafe_allow_html=True)

# --- 세션 상태(Session State) 초기화 ---
if 'compare_list' not in st.session_state:
    st.session_state.compare_list = []
if 'visited' not in st.session_state:
    st.session_state.visited = True
    is_new_visit = True
else:
    is_new_visit = False

# --- CSS 스타일링 ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] button {
        border: 2px solid #1D4ED8 !important; border-radius: 8px !important;
        padding: 10px 24px !important; font-size: 18px !important; font-weight: bold !important;
        color: #1D4ED8 !important; margin-right: 10px !important; background-color: white !important;
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        background-color: #1D4ED8 !important; color: white !important;
    }
    [data-testid="stSidebar"] a { text-decoration: none !important; font-weight: 500; color: #1D4ED8; }
    [data-testid="stSidebar"] a:hover { color: #1E3A8A; font-weight: 700; }
    span[data-baseweb="tag"] { background-color: #EFF6FF !important; border: 1px solid #93C5FD !important; color: #1D4ED8 !important; }
    .compare-card { background-color: #F8FAFC; padding: 20px; border-radius: 10px; border: 1px solid #E2E8F0; height: 100%; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    .score-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px dashed #CBD5E1; }
    .diff-minus { color: #E11D48; font-weight: bold; font-size: 14px; }
    .diff-plus { color: #059669; font-weight: bold; font-size: 14px; }
    .diff-same { color: #64748B; font-weight: bold; font-size: 14px; }
    .footer-text { font-size: 12px; color: #6B7280; text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px solid #E5E7EB; }
    </style>
""", unsafe_allow_html=True)

# --- 방문자 수 관리 함수 ---
def manage_visitor_count(is_new_visit):
    visitor_file = "visitors.json"
    
    # 한국 시간(KST) 설정
    KST = timezone(timedelta(hours=9))
    today_date = datetime.now(KST).strftime('%Y-%m-%d')
    
    data = {"date": today_date, "today": 0, "total": 0}
    
    if os.path.exists(visitor_file):
        try:
            with open(visitor_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except: pass
        
    if data.get("date") != today_date:
        data["date"] = today_date
        data["today"] = 0
        
    if is_new_visit:
        data["today"] += 1
        data["total"] += 1
        try:
            with open(visitor_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except: pass
        
    return data["today"], data["total"]

today_count, total_count = manage_visitor_count(is_new_visit)

# 2. 데이터 로드 및 전처리 (수동 수집 CSV 전용)
@st.cache_data(show_spinner=False)
def load_and_preprocess_data():
    df = pd.read_excel('전국 환자경험평가 최종 결과2.xlsx')
    df['구분'] = df['구분'].replace({'상종': '상급종합병원', '종합': '종합병원'})
    df['지역'] = df['소재지'].apply(lambda x: str(x).split(' ')[0])
    
    domains_list = ['1. 간호사 영역', '2. 의사 영역', '3. 투약 및 치료과정', '4. 정서적 지지', '5. 환자 안전과 병원 환경', '6. 환자권리 보장', '7. 전반적 평가']
    for d in domains_list:
        df[f'{d}_상위%'] = df[d].rank(pct=True, ascending=False) * 100
        
    cache_file = 'geocoded_hospitals.csv'
    
    if os.path.exists(cache_file):
        cached_coords = pd.read_csv(cache_file)
        cached_coords['Latitude'] = pd.to_numeric(cached_coords['Latitude'], errors='coerce')
        cached_coords['Longitude'] = pd.to_numeric(cached_coords['Longitude'], errors='coerce')
        
        df = pd.merge(df, cached_coords[['병원명', 'Latitude', 'Longitude']], on='병원명', how='left')
        
        df['Latitude'] = df['Latitude'].fillna(36.5)
        df['Longitude'] = df['Longitude'].fillna(127.5)
    else:
        st.error(f"🚨 '{cache_file}' 파일이 폴더에 없습니다! 수동으로 수집하신 CSV 파일을 업로드해 주세요.")
        st.stop()
    
    return df, domains_list

df, domains = load_and_preprocess_data()
national_avg = df[domains].mean().to_dict()

# 3. 사이드바 구성
st.sidebar.header("🔍 조건 필터")
st.sidebar.caption("여러 개를 동시 선택 및 해제할 수 있습니다.")

selected_region = st.sidebar.multiselect("1. 시/도 선택", sorted(list(df['지역'].unique())))
selected_type = st.sidebar.multiselect("2. 병원 종별 선택", list(df['구분'].unique()))
selected_grade = st.sidebar.multiselect("3. 평가 등급 선택", sorted(list(df['평가등급'].unique())))

filtered_df = df.copy()
if selected_region: filtered_df = filtered_df[filtered_df['지역'].isin(selected_region)]
if selected_type: filtered_df = filtered_df[filtered_df['구분'].isin(selected_type)]
if selected_grade: filtered_df = filtered_df[filtered_df['평가등급'].isin(selected_grade)]

def add_filtered_hospitals():
    st.session_state.compare_list = filtered_df['병원명'].tolist()

st.sidebar.markdown("---")
st.sidebar.header("🏥 심층 분석 병원 선택")
st.sidebar.caption("※ 지도나 리스트에서 확인한 병원을 검색하거나, 아래 버튼을 눌러 지도에 남은 병원들을 한 번에 추가하세요.")

selected_hospitals = st.sidebar.multiselect(
    "비교할 병원들을 선택하세요", 
    options=df['병원명'].sort_values().tolist(),
    default=st.session_state.compare_list,
    key="compare_list" 
)

if st.sidebar.button("🗺️ 지도에 표시된 병원 비교하기", on_click=add_filtered_hospitals, use_container_width=True):
    pass 

if selected_hospitals:
    st.sidebar.markdown("##### [선택된 비교 그룹]")
    for h in selected_hospitals:
        st.sidebar.markdown(f"✅ {h}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 💡 유용한 정보")
st.sidebar.markdown("""
- [환자경험평가란? (유튜브)](https://www.youtube.com/watch?v=1b88aaD1MM8)
- [평가 결과 안내문 (심평원)](https://www.hira.or.kr/ra/eval/asmInfo.do?evlCd=30&pgmid=HIRAA030004000000)
- [심사평가원 직접 조회](https://www.hira.or.kr/ra/eval/getDiagEvlList.do?pgmid=HIRAA030004000100)
- [관련 언론 보도 보기](https://www.google.com/search?q=%ED%99%98%EC%9E%90%EA%B2%BD%ED%97%98%ED%8F%89%EA%B0%80&tbm=nws)
""")

# [수정] 구분선과 함께 방문자 통계 텍스트만 심플하게 배치
st.sidebar.markdown("---")
st.sidebar.caption(f"📈 **방문자 통계** | 오늘: **{today_count:,}**명 / 누적: **{total_count:,}**명")


# 4. 메인 화면
try:
    if os.path.exists("banner.png"):
        st.image("banner.png", use_container_width=True)
    elif os.path.exists("서비스 배너.PNG"):
        st.image("서비스 배너.PNG", use_container_width=True)
except: pass

st.title("전국 환자경험 지도(PX Map)")
st.markdown("##### 건강보험심사평가원 '환자경험평가' 데이터를 기반으로 쉽고 빠르게 병원을 비교할 수 있습니다.")

tab1, tab2 = st.tabs(["대한민국 환자경험 지도", "심층 분석 대시보드"])

# --- TAB 1: 지도 기능 ---
with tab1:
    st.caption("📍 지도에서 마커를 클릭하여 병원 정보를 확인하세요. 상세 비교를 원하시면 좌측 사이드바에서 병원을 검색해 추가할 수 있습니다.")
    
    map_center = [filtered_df['Latitude'].mean(), filtered_df['Longitude'].mean()] if not filtered_df.empty and filtered_df['Latitude'].mean() != 36.5 else [36.2, 127.8]
    m = folium.Map(location=map_center, zoom_start=7, tiles="OpenStreetMap")
    
    region_fallback = {
        '서울특별시': [37.5665, 126.9780], '부산광역시': [35.1796, 129.0756], '대구광역시': [35.8714, 128.6014],
        '인천광역시': [37.4563, 126.7052], '광주광역시': [35.1595, 126.8526], '전남광주통합특별시': [35.1595, 126.8526],
        '대전광역시': [36.3504, 127.3845], '울산광역시': [35.5384, 129.3114], '세종특별자치시': [36.4800, 127.2890],
        '경기도': [37.2752, 127.0095], '강원특별자치도': [37.8854, 127.7298], '충청북도': [36.6356, 127.4913],
        '충청남도': [36.6588, 126.6728], '전북특별자치도': [35.8203, 127.1087], '전라북도': [35.8203, 127.1087],
        '전라남도': [34.8159, 126.4629], '경상북도': [36.5754, 128.5058], '경상남도': [35.2383, 128.6925],
        '제주특별자치도': [33.4890, 126.4983]
    }
    
    for idx, row in filtered_df.iterrows():
        lat, lon = row['Latitude'], row['Longitude']
        if lat == 36.5:
            base_coords = region_fallback.get(row['지역'], [36.5, 127.5])
            lat = base_coords[0] + random.uniform(-0.04, 0.04)
            lon = base_coords[1] + random.uniform(-0.04, 0.04)
        
        grade_str = str(row['평가등급']).strip()
        if '1등급' in grade_str: color = 'blue'
        elif '2등급' in grade_str: color = 'green'
        else: color = 'orange'
            
        detail_link = row['상세보기 링크'] if '상세보기 링크' in row and pd.notna(row['상세보기 링크']) else ""
        link_html = f"<br><a href='{detail_link}' target='_blank' style='display:inline-block; margin-top:8px; padding:5px 10px; background:#1D4ED8; color:white; text-decoration:none; border-radius:5px;'>🔍 심평원 상세보기</a>" if detail_link else ""
        
        popup_html = f"""
        <div style="width:220px; font-family:sans-serif;">
            <b style="font-size:15px;">{row['병원명']}</b> ({row['구분']})<br>
            <span style="color:{color}; font-weight:bold;">{row['평가등급']}</span> 
            | 종합: {row['종합점수']:.2f}점<br>
            <hr style="margin:8px 0">
            <small>{row['소재지']}</small>
            {link_html}
        </div>
        """
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['병원명']}",
            icon=folium.Icon(color=color, icon='info-sign')
        ).add_to(m)

    st_folium(m, width="100%", height=500, returned_objects=[], key="px_main_map")
    
    st.markdown("""
    <div style="text-align:center; padding:10px; background-color:#F8FAFC; border-radius:5px; margin-bottom:5px; border:1px solid #E2E8F0;">
        <b>등급 표기 안내:</b> 
        <span style="color:#1D4ED8; font-weight:bold; margin:0 15px;">🔵 1등급</span>
        <span style="color:#059669; font-weight:bold; margin:0 15px;">🟢 2등급</span>
        <span style="color:#EA580C; font-weight:bold; margin:0 15px;">🟠 3~5등급</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.caption("※ 지도에 표시된 위치가 실제 위치와 다소 차이가 있을 수 있으니 참고용으로 사용 부탁드립니다.")
    
    st.markdown("---")
    st.markdown("##### 💡 조건 필터 결과 리스트")
    if filtered_df.empty: st.warning("선택하신 조건에 일치하는 병원이 없습니다.")
    else:
        display_cols = ['순위', '병원명', '구분', '평가등급', '종합점수', '소재지', '전화번호']
        display_df = filtered_df[display_cols].copy()
        display_df['종합점수'] = display_df['종합점수'].apply(lambda x: f"{x:.2f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# --- TAB 2: 심층 분석 대시보드 ---
with tab2:
    if len(selected_hospitals) == 0:
        st.warning("분석할 병원이 없습니다. 좌측 사이드바에서 비교할 병원을 검색하여 선택해주세요.")
    else:
        compare_df = df[df['병원명'].isin(selected_hospitals)].copy()
        compare_df = compare_df.sort_values(by='종합점수', ascending=False)
        top_hosp = compare_df.iloc[0]
        
        st.markdown("#### 평가 영역별 비교")
        st.caption(f"※ 비교 그룹 내 종합점수 1위 병원(**{top_hosp['병원명']}**)을 기준으로 각 영역별 점수 격차를 나타냅니다.")
        
        cols = st.columns(len(compare_df) if len(compare_df) <= 4 else 4)
        for i, (idx, row) in enumerate(compare_df.iterrows()):
            with cols[i % 4]:
                def get_diff_html(current_val, top_val):
                    diff = current_val - top_val
                    if diff == 0: return f"<span class='diff-same'>(-)</span>"
                    elif diff < 0: return f"<span class='diff-minus'>(▼ {abs(diff):.2f})</span>"
                    else: return f"<span class='diff-plus'>(▲ {abs(diff):.2f})</span>"

                html_content = f"""
                <div class="compare-card">
                    <h4 style="color:#1E3A8A; margin-bottom:0px;">{row['병원명']}</h4>
                    <p style="color:#64748B; font-size:14px; margin-top:0px;">{row['구분']} | {row['평가등급']}</p>
                    <div style="background-color:#DBEAFE; padding:10px; border-radius:5px; text-align:center; margin-bottom:15px;">
                        <span style="font-size:14px; color:#1E3A8A;">종합점수</span><br>
                        <b style="font-size:20px; color:#1E3A8A;">{row['종합점수']:.2f}</b> {get_diff_html(row['종합점수'], top_hosp['종합점수'])}
                    </div>
                """
                for d in domains:
                    html_content += f"<div class='score-row'><span>{d.split('. ')[1]}</span> <span>{row[d]:.2f} {get_diff_html(row[d], top_hosp[d])}</span></div>"
                html_content += "</div><br>"
                st.markdown(html_content, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 병원별 강점/약점 분석")
        sw_cols = st.columns(len(compare_df) if len(compare_df) <= 3 else 3)
        
        for i, (idx, row) in enumerate(compare_df.iterrows()):
            h_scores = {d: row[d] for d in domains}
            strongest = max(h_scores, key=h_scores.get)
            weakest = min(h_scores, key=h_scores.get)
            
            with sw_cols[i % 3]:
                st.markdown(f"""
                <div style='background-color:#F0FDF4; padding:15px; border-radius:10px; margin-bottom:15px; border:1px solid #BBF7D0;'>
                    <h5 style='color:#064E3B; font-weight:bold; margin-top:0;'>🏥 {row['병원명']}</h5>
                    <p style='margin:5px 0;'><b style='color:#059669;'>[최고 우수 영역]</b> {strongest.split('. ')[1]}<br>
                    <small>({row[strongest]:.2f}점 / 전국 상위 {row[strongest+'_상위%']:.1f}%)</small></p>
                    <p style='margin:0;'><b style='color:#E11D48;'>[집중 개선 영역]</b> {weakest.split('. ')[1]}<br>
                    <small>({row[weakest]:.2f}점 / 전국 상위 {row[weakest+'_상위%']:.1f}%)</small></p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 📊 영역별 방사형(Radar) 차트 분석")
        
        st.markdown("##### 1. 비교 그룹 간 분석")
        categories = [d.split('. ')[1] for d in domains]
        fig_all = go.Figure()
        for idx, row in compare_df.iterrows():
            fig_all.add_trace(go.Scatterpolar(r=[row[d] for d in domains], theta=categories, fill='toself', name=row['병원명'], opacity=0.3))
        fig_all.update_layout(polar=dict(radialaxis=dict(visible=True, range=[60, 100])), showlegend=True, height=450)
        st.plotly_chart(fig_all, use_container_width=True)
        
        st.markdown("##### 2. 병원별 상세 지표 분석")
        chart_cols = st.columns(2)
        for i, (idx, row) in enumerate(compare_df.iterrows()):
            h_region = row['지역']
            region_avg = df[df['지역'] == h_region][domains].mean().to_dict()
            
            fig_ind = go.Figure()
            fig_ind.add_trace(go.Scatterpolar(r=[row[d] for d in domains], theta=categories, fill='toself', name=row['병원명'], line_color='#1D4ED8'))
            fig_ind.add_trace(go.Scatterpolar(r=[region_avg[d] for d in domains], theta=categories, fill='toself', name=f"{h_region} 평균", line_color='#10B981', opacity=0.4))
            fig_ind.add_trace(go.Scatterpolar(r=[national_avg[d] for d in domains], theta=categories, fill='none', name="전국 평균", line=dict(color='#EF4444', dash='dash')))
            fig_ind.update_layout(title=f"🏥 {row['병원명']}", polar=dict(radialaxis=dict(visible=True, range=[60, 100])), height=400)
            
            with chart_cols[i % 2]:
                st.plotly_chart(fig_ind, use_container_width=True)

# --- 최하단 설명글 (Footer) ---
st.markdown("""
<div class='footer-text'>
    본 서비스는 건강보험심사평가원이 공개한 2025년 제5차 환자경험평가 결과를 기반으로 제작되었습니다. <br>
    지도 기반 탐색을 통해 지역별·병원별 환자경험 수준을 쉽고 직관적으로 비교할 수 있으며, 합리적인 의료기관 선택과 환자 중심 문화 형성에 도움이 되는 정보를 제공합니다.
</div>
""", unsafe_allow_html=True)

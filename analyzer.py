import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client, Client
import io
from datetime import date

# --- Configuration ---
SUPABASE_URL: str = "https://kjzkdebwhnwecuaaxerv.supabase.co"
SUPABASE_KEY: str = "sb_publishable_LvtH9iUC9QkhYNUwMcVQCA_j3v-FVHQ"
BUCKET_NAME: str = "realty-data"
FILE_PATH_IN_STORAGE: str = "realty-data-1141215/test101-1141111.csv"
TARGET_COMMUNITY: str = "國家大第"

# --- Data Loading Function ---
@st.cache_data
def load_data( ):
    """Downloads data from Supabase Storage, loads it, and pre-filters for the target community."""
    try:
        # 初始化 Supabase 客戶端
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        # 下載檔案內容為 bytes
        res = supabase.storage.from_(BUCKET_NAME).download(FILE_PATH_IN_STORAGE)

        # 使用 io.BytesIO 將 bytes 直接讀取到 pandas
        data = io.BytesIO(res)
        df = pd.read_csv(data)

        # 重新命名欄位
        column_mapping = {
            '社區簡稱': 'community_name',
            '交易日期': 'date_of_transaction_roc',
            '單價(萬元/坪)': 'unit_price_per_ping',
            '總價(萬元)': 'total_price',
            '交易標的': 'transaction_target'
        }
        df.rename(columns=column_mapping, inplace=True)

        # 轉換數值型態
        df['unit_price_per_ping'] = pd.to_numeric(df['unit_price_per_ping'], errors='coerce')
        df['total_price'] = pd.to_numeric(df['total_price'], errors='coerce')

        # 轉換民國紀元日期為西元 datetime 物件 (修正日期格式處理)
        def convert_roc_date(roc_date_str):
            try:
                # 假設格式為 YYY/MM/DD (例如: 101/11/19)
                parts = roc_date_str.split('/')
                if len(parts) == 3:
                    year, month, day = map(int, parts)
                    return pd.to_datetime(f"{year + 1911}-{month}-{day}")
                return pd.NaT
            except Exception:
                return pd.NaT # 轉換失敗返回 NaT

        df['date_of_transaction'] = df['date_of_transaction_roc'].apply(convert_roc_date)
        
        # 預先篩選：只保留目標社區的數據
        df_filtered = df[df['community_name'] == TARGET_COMMUNITY].copy()
        
        # 移除日期為 NaT 的紀錄，確保日期篩選功能正常
        df_filtered.dropna(subset=['date_of_transaction'], inplace=True)

        return df_filtered

    except Exception as e:
        st.error(f"從 Supabase 下載或處理數據時發生錯誤: {e}")
        return pd.DataFrame()

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title(f"斗六市{TARGET_COMMUNITY} 101-114111 實價登錄查詢")

# 載入數據
df_full = load_data()

if df_full.empty:
    st.error("數據載入失敗或目標社區無數據。請檢查 Supabase 憑證、檔案路徑或社區名稱。")
else:
    # 獲取日期範圍的預設值
    min_date = df_full['date_of_transaction'].min().date()
    max_date = df_full['date_of_transaction'].max().date()

    # 1. 增加 Streamlit 側邊欄和日期範圍選擇器
    with st.sidebar:
        st.header("數據篩選")
        
        # 確保 date_range 是一個包含兩個日期的元組
        # 設置預設值為 min_date 和 max_date
        date_range = st.date_input(
            "選擇交易日期範圍",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

    # 2. 篩選數據
    filtered_df = df_full.copy()
    if len(date_range) == 2:
        start_date = pd.to_datetime(date_range[0])
        end_date = pd.to_datetime(date_range[1])
        
        # 執行日期篩選
        filtered_df = filtered_df[
            (filtered_df['date_of_transaction'] >= start_date) & 
            (filtered_df['date_of_transaction'] <= end_date)
        ]
    
    # 處理篩選結果
    if filtered_df.empty:
        st.warning("在選定的日期範圍內沒有找到數據。請調整篩選條件。")
    else:
        st.subheader(f"篩選結果：共 {len(filtered_df)} 筆交易")

        # 3. 顯示總結指標
        col1, col2, col3 = st.columns(3)
        
        # 成交筆數
        col1.metric(label="成交筆數", value=f"{len(filtered_df):,}")

        # 市場成交最多單價 (Mode)
        # 移除 NaN 值後計算眾數
        mode_unit_price_data = filtered_df['unit_price_per_ping'].dropna()
        mode_unit_price = mode_unit_price_data.mode()
        mode_unit_price_str = f"{mode_unit_price.iloc[0]:.2f} 萬元/坪" if not mode_unit_price.empty else "N/A"
        col2.metric(label="市場成交最多單價", value=mode_unit_price_str)

        # 市場成交最多總價 (Mode)
        mode_total_price_data = filtered_df['total_price'].dropna()
        mode_total_price = mode_total_price_data.mode()
        mode_total_price_str = f"{mode_total_price.iloc[0]:,} 萬元" if not mode_total_price.empty else "N/A"
        col3.metric(label="市場成交最多總價", value=mode_total_price_str)

        st.markdown("---")

        # 4. 繪製趨勢圖
        
        # 準備繪圖數據 (按月平均)
        df_trend = filtered_df.set_index('date_of_transaction').resample('M').agg({
            'unit_price_per_ping': 'mean',
            'total_price': 'mean'
        }).reset_index()
        
        # 處理眾數標示
        most_frequent_unit_price = mode_unit_price.iloc[0] if not mode_unit_price.empty else filtered_df['unit_price_per_ping'].mean()
        most_frequent_total_price = mode_total_price.iloc[0] if not mode_total_price.empty else filtered_df['total_price'].mean()

        # --- 成交單價趨勢圖 ---
        st.header("成交單價趨勢 (按月平均)")
        
        # **定義單價基礎圖表**
        base_unit_chart = alt.Chart(df_trend).encode(
            x=alt.X('date_of_transaction', title='成交時間', axis=alt.Axis(format="%Y-%m")),
            y=alt.Y('unit_price_per_ping', title='單價 (萬元/坪)'),
        ).properties(
            title='成交單價趨勢'
        ).configure_axis(
            labelFont='sans-serif',
            titleFont='sans-serif'
        ).configure_title(
            font='sans-serif'
        )

        # 趨勢線圖
        line_unit = base_unit_chart.mark_line(point=True).encode(
            tooltip=[
                alt.Tooltip('date_of_transaction', title='月份', format="%Y-%m"), 
                alt.Tooltip('unit_price_per_ping', title='平均單價', format=".2f")
            ]
        )
        
        # 標示眾數線（使用獨立數據源，但 Y 軸名稱與主圖表一致）
        rule_unit = alt.Chart(pd.DataFrame({'unit_price_per_ping': [most_frequent_unit_price]})).mark_rule(
            color='red', 
            strokeDash=[5, 5]
        ).encode(
            y='unit_price_per_ping:Q',
            tooltip=[alt.Tooltip('unit_price_per_ping', title='最常見單價', format=".2f")]
        )
        
        # **使用 + 運算符疊加圖表 (修正)**
        st.altair_chart(line_unit + rule_unit, use_container_width=True)

        # --- 總價趨勢圖 ---
        st.header("總價趨勢 (按月平均)")
        
        # **定義總價基礎圖表**
        base_total_chart = alt.Chart(df_trend).encode(
            x=alt.X('date_of_transaction', title='成交時間', axis=alt.Axis(format="%Y-%m")),
            y=alt.Y('total_price', title='總價 (萬元)'),
        ).properties(
            title='總價趨勢'
        ).configure_axis(
            labelFont='sans-serif',
            titleFont='sans-serif'
        ).configure_title(
            font='sans-serif'
        )

        # 趨勢線圖
        line_total = base_total_chart.mark_line(point=True).encode(
            tooltip=[
                alt.Tooltip('date_of_transaction', title='月份', format="%Y-%m"), 
                alt.Tooltip('total_price', title='平均總價', format=".0f")
            ]
        )
        
        # 標示眾數線（使用獨立數據源，但 Y 軸名稱與主圖表一致）
        rule_total = alt.Chart(pd.DataFrame({'total_price': [most_frequent_total_price]})).mark_rule(
            color='red', 
            strokeDash=[5, 5]
        ).encode(
            y='total_price:Q',
            tooltip=[alt.Tooltip('total_price', title='最常見總價', format=".0f")]
        )
        
        # **使用 + 運算符疊加圖表 (修正)**
        st.altair_chart(line_total + rule_total, use_container_width=True)

        # 5. 顯示數據表格 (完整篩選後的數據)
        st.header("原始數據表格")
        st.dataframe(filtered_df)

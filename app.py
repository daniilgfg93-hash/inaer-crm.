import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import uuid
import time
import os
import base64
import json

# ==========================================
# 1. БАЗОВЫЕ НАСТРОЙКИ И СОСТОЯНИЕ
# ==========================================
st.set_page_config(page_title="INÆR CRM PRO", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

# Инициализация состояния
if "cart" not in st.session_state: st.session_state.cart = []
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "username" not in st.session_state: st.session_state.username = ""
if "role" not in st.session_state: st.session_state.role = ""

# ГЛОБАЛЬНЫЙ CSS ДЛЯ КРАСИВОГО ИНТЕРФЕЙСА
st.markdown("""
<style>
    /* Убираем стандартные кружочки в боковом меню и делаем их кнопками */
    [data-testid="stSidebar"] [role="radiogroup"] {
        gap: 0.5rem;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        background-color: transparent;
        padding: 10px 15px;
        border-radius: 8px;
        cursor: pointer;
        width: 100%;
        transition: all 0.2s ease;
        border: 1px solid transparent;
        margin: 0;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background-color: #f1f5f9;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] {
        background-color: #e2e8f0;
        border: 1px solid #cbd5e1;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] p {
        font-weight: 700;
        color: #0f172a;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    
    /* Стилизация радио-кнопок статусов заказов (чтобы тоже были без кружочков) */
    div.status-filter [role="radiogroup"] label {
        background-color: white;
        padding: 8px 12px;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
        margin-bottom: 4px;
        cursor: pointer;
    }
    div.status-filter [role="radiogroup"] label:hover { background-color: #f8fafc; }
    div.status-filter [role="radiogroup"] label[data-checked="true"] { border-left: 4px solid #3b82f6; font-weight: bold; background-color: #f1f5f9; }
    div.status-filter [role="radiogroup"] label > div:first-child { display: none !important; }

    /* Компактность форм и метрик */
    div[data-testid="stForm"] { background: white; border: 1px solid #e1e5eb; border-radius: 8px; padding: 1.5rem; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
""", unsafe_allow_html=True)

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/11QUolb_hXw0-YPOc_tBEre0GPX4hO9NesflLTJn4BA8/edit"

DB_STRUCTURE = {
    "Товары": ["ID", "Наименование", "Категория", "Остаток", "Себестоимость", "Цена продажи", "URL фото", "Описание"],
    "Продажи": ["Дата", "ID Товара", "Товар", "Кол-во", "Цена 1шт", "Сумма продажи", "Себестоимость (общ)", "Чистая прибыль", "Скидка", "Клиент", "Телефон", "Тип доставки", "Адрес", "ID Заказа", "ТТН", "Статус", "Менеджер"],
    "Закупки": ["Дата", "Товар", "Кол-во", "Сумма (грн)", "Сумма ($)", "Курс", "Себестоимость 1шт", "Поставщик", "Комментарий", "Сотрудник"],
    "Списания": ["Дата", "Товар", "Кол-во", "Сумма убытка", "Причина", "Комментарий", "Сотрудник"],
    "Финансы": ["Дата", "Тип операции", "Категория", "Сумма (грн)", "Комментарий", "Сотрудник"],
    "Логи": ["Дата", "Пользователь", "Роль", "Действие", "Детали"],
    "Настройки": ["Категории", "Поставщики", "Доставка", "Причины списания", "Категории финансов", "Статусы заказов"]
}

# ==========================================
# 2. АВТОРИЗАЦИЯ
# ==========================================
USERS_FILE = 'users.json'

def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {"password": "admin", "role": "Админ", "name": "Администратор"},
            "manager": {"password": "123", "role": "Менеджер", "name": "Менеджер Продаж"},
            "buyer": {"password": "123", "role": "Закупщик", "name": "Менеджер Склада"}
        }
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_users, f, ensure_ascii=False, indent=4)
        return default_users
    else:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

users_db = load_users()

if not st.session_state.logged_in:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<h2 style='text-align: center; color: #2a313d;'>💎 ВХОД В INÆR CRM PRO</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            login = st.text_input("Логин")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("ВОЙТИ", use_container_width=True):
                if login in users_db and users_db[login]["password"] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = users_db[login]["name"]
                    st.session_state.role = users_db[login]["role"]
                    st.rerun()
                else:
                    st.error("Неверный логин или пароль")
    st.stop()

# ==========================================
# 3. ПОДКЛЮЧЕНИЕ К БД И ФУНКЦИИ
# ==========================================
@st.cache_resource
def init_connection():
    client = gspread.service_account(filename='credentials.json')
    return client.open_by_url(SPREADSHEET_URL)

try: db = init_connection()
except Exception as e: st.error(f"Ошибка БД: {e}"); st.stop()

@st.cache_resource(ttl=3600)
def verify_and_create_structure():
    try:
        existing = [ws.title for ws in db.worksheets()]
        for name, headers in DB_STRUCTURE.items():
            if name not in existing:
                ws = db.add_worksheet(title=name, rows="1000", cols="20")
                ws.append_row(headers); time.sleep(1)
                if name == "Настройки":
                    ws.append_row(["Парфюм", "Олег", "Новая Почта", "Брак", "Вложение средств", "Новый"])
                    ws.append_row(["Авто-парфюм", "Кремчик", "Укр Почта", "Использовано как тестер", "Снятие", "Обрабатывается"])
                    ws.append_row(["Расходники", "Рынок", "Самовывоз", "Потеряно", "Аренда", "Передан в доставку"])
                    ws.append_row(["Свечи", "", "", "", "Зарплата", "Завершен"])
                    ws.append_row(["", "", "", "", "", "Отменен"])
            else:
                ws = db.worksheet(name)
                cur_h = ws.row_values(1)
                miss = [h for h in headers if h not in cur_h]
                if miss:
                    for i, h in enumerate(miss): ws.update_cell(1, len(cur_h)+i+1, h)
                    time.sleep(1)
    except: pass

verify_and_create_structure()

@st.cache_data(ttl=15)
def load_table(sheet_name):
    try:
        data = db.worksheet(sheet_name).get_all_values()
        if len(data) > 1: return pd.DataFrame(data[1:], columns=data[0])
        return pd.DataFrame(columns=DB_STRUCTURE[sheet_name])
    except: return pd.DataFrame(columns=DB_STRUCTURE[sheet_name])

def log_action(action, details=""):
    try: db.worksheet("Логи").append_row([datetime.now().strftime("%d.%m.%Y %H:%M:%S"), st.session_state.username, st.session_state.role, action, details], value_input_option='USER_ENTERED')
    except: pass

def append_row(sheet_name, data_dict):
    ws = db.worksheet(sheet_name)
    ws.append_row([data_dict.get(h, "") for h in ws.row_values(1)], value_input_option='USER_ENTERED')

def append_multiple_rows(sheet_name, list_of_dicts):
    ws = db.worksheet(sheet_name)
    headers = ws.row_values(1)
    ws.append_rows([[d.get(h, "") for h in headers] for d in list_of_dicts], value_input_option='USER_ENTERED')

def update_stock(product_name, qty_change):
    ws = db.worksheet("Товары")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    try: n_col, s_col = h.index("Наименование"), h.index("Остаток")
    except: return False
    for r_idx, row in enumerate(data[1:], 2):
        if row[n_col] == product_name:
            cur = float(row[s_col]) if row[s_col] else 0
            ws.update_cell(r_idx, s_col + 1, cur + qty_change)
            return True
    return False

def update_product_details_by_id(prod_id, new_name, cat, stock, cost, price, photo_url, desc):
    ws = db.worksheet("Товары")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    try: id_col = h.index("ID")
    except: return False
    cols = {c: h.index(c) for c in ["Наименование", "Категория", "Остаток", "Себестоимость", "Цена продажи", "URL фото", "Описание"] if c in h}
    for r_idx, row in enumerate(data[1:], 2):
        if str(row[id_col]) == str(prod_id):
            cells = [gspread.Cell(r_idx, cols[c]+1, val) for c, val in zip(["Наименование", "Категория", "Остаток", "Себестоимость", "Цена продажи", "URL фото", "Описание"], [new_name, cat, stock, cost, price, photo_url, desc]) if c in cols]
            ws.update_cells(cells); return True
    return False

def get_product_info(product_name):
    df = load_table("Товары")
    if df.empty: return 0, 0
    row = df[df["Наименование"] == product_name]
    if not row.empty: return float(row.iloc[0]["Себестоимость"] or 0), float(row.iloc[0]["Цена продажи"] or 0)
    return 0, 0

def get_settings(column_name):
    df = load_table("Настройки")
    if column_name in df.columns: return [x for x in df[column_name].tolist() if str(x).strip() != ""]
    return []

# --- Заказы API ---
def update_order_details(order_id, new_status, new_ttn):
    ws = db.worksheet("Продажи")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    try: id_col, st_col, ttn_col = h.index("ID Заказа"), h.index("Статус"), h.index("ТТН")
    except: return False
    cells = []
    for r, row in enumerate(data[1:], 2):
        if len(row) > id_col and str(row[id_col]) == str(order_id):
            cells.extend([gspread.Cell(r, st_col+1, new_status), gspread.Cell(r, ttn_col+1, new_ttn)])
    if cells: ws.update_cells(cells); return True
    return False

def update_single_sale_row(order_id, product_name, new_qty, new_price, new_discount):
    ws = db.worksheet("Продажи")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    try:
        id_c, pr_c, q_c, prc_c, s_c = h.index("ID Заказа"), h.index("Товар"), h.index("Кол-во"), h.index("Цена 1шт"), h.index("Сумма продажи")
        c_c, prof_c, d_c = h.index("Себестоимость (общ)"), h.index("Чистая прибыль"), h.index("Скидка")
    except: return False

    cost_1, _ = get_product_info(product_name)
    for r_idx, row in enumerate(data[1:], 2):
        if str(row[id_c]) == str(order_id) and str(row[pr_c]) == str(product_name):
            old_qty = float(row[q_c]) if row[q_c] else 0
            n_sum = (new_price * new_qty) - new_discount
            n_cost = cost_1 * new_qty
            cells = [gspread.Cell(r_idx, c+1, v) for c, v in zip([q_c, prc_c, s_c, c_c, prof_c, d_c], [new_qty, new_price, n_sum, n_cost, n_sum - n_cost, new_discount])]
            ws.update_cells(cells)
            update_stock(product_name, -(new_qty - old_qty))
            return True
    return False

def delete_single_sale_row(order_id, product_name):
    ws = db.worksheet("Продажи")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    try: id_c, pr_c, q_c = h.index("ID Заказа"), h.index("Товар"), h.index("Кол-во")
    except: return False
    for r, row in enumerate(data[1:], 2):
        if str(row[id_c]) == str(order_id) and str(row[pr_c]) == str(product_name):
            ws.delete_rows(r); update_stock(product_name, float(row[q_c]) if row[q_c] else 0); return True
    return False

def add_item_to_order(order_id, product_name, qty, price, discount):
    ws = db.worksheet("Продажи")
    data = ws.get_all_values()
    if len(data) <= 1: return False
    h = data[0]
    order_row = next((row for row in data[1:] if len(row) > h.index("ID Заказа") and str(row[h.index("ID Заказа")]) == str(order_id)), None)
    if not order_row: return False
    while len(order_row) < len(h): order_row.append("")
    d = dict(zip(h, order_row))
    cost_1, _ = get_product_info(product_name)
    ts = (price * qty) - discount; tc = cost_1 * qty
    d.update({"Товар": product_name, "Кол-во": qty, "Цена 1шт": price, "Сумма продажи": ts, "Себестоимость (общ)": tc, "Чистая прибыль": ts - tc, "Скидка": discount})
    append_row("Продажи", d); update_stock(product_name, -qty); return True

def get_image_uri(path_or_url):
    if not path_or_url or pd.isna(path_or_url): return ""
    p = str(path_or_url).strip()
    if p.startswith("http"): return p
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                mime = 'jpeg' if p.split('.')[-1].lower() in ['jpg', 'jpeg'] else 'png'
                return f"data:image/{mime};base64,{b64}"
        except: return ""
    return ""

def get_status_color(status):
    s = str(status).lower()
    if "нов" in s: return "🔵"
    if "обраб" in s or "сбор" in s: return "🟣"
    if "отправ" in s or "передан" in s: return "🟡"
    if "заверш" in s or "получ" in s: return "🟢"
    if "отказ" in s or "отмен" in s: return "🔴"
    return "⚪"

# ==========================================
# 4. БОКОВОЕ МЕНЮ (SIDEBAR)
# ==========================================
st.sidebar.title("💎 INÆR CRM PRO")
st.sidebar.markdown(f"👤 **{st.session_state.username}** \n\n _{st.session_state.role}_")
st.sidebar.markdown("---")

available_menus = []
if st.session_state.role in ["Админ", "Менеджер"]:
    available_menus.extend(["🛒 Корзина", "🚚 Заказы", "👥 Клиенты", "🖼️ Каталог"])
if st.session_state.role in ["Админ", "Закупщик"]:
    available_menus.extend(["📥 Закупки", "🗑️ Списание", "📦 Склад"])
if st.session_state.role == "Админ":
    available_menus.extend(["📊 Дашборд", "📈 Отчеты", "💸 Финансы", "📜 Логи", "⚙️ Настройки"])

menu = st.sidebar.radio("Навигация", available_menus, label_visibility="collapsed")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Обновить базу", use_container_width=True): 
    st.cache_data.clear(); st.rerun()

# ==========================================
# 5. ЛОГИКА РАЗДЕЛОВ
# ==========================================

# --- КОРЗИНА И ОФОРМЛЕНИЕ ---
if menu == "🛒 Корзина":
    st.markdown("<h3 style='color:#333;'>🛒 Оформление заказа</h3>", unsafe_allow_html=True)
    df_products = load_table("Товары")
    cats = ["Все"] + get_settings("Категории")
    
    with st.container():
        c1, c2, c3, c4, c5 = st.columns([1.5, 3, 1, 1.2, 1.5])
        with c1: sel_cat = st.selectbox("Фильтр", cats)
        f_prods = df_products[df_products["Категория"] == sel_cat] if sel_cat != "Все" else df_products
        with c2: sel_prod = st.selectbox("Выберите товар", [""] + (f_prods["Наименование"].tolist() if not f_prods.empty else []))
        with c3: sel_qty = st.number_input("Кол-во", min_value=1.0, step=1.0)
        with c4: sel_price = st.number_input("Цена (0=баз)", min_value=0.0)
        with c5:
            st.write(""); st.write("")
            if st.button("➕ В корзину", use_container_width=True) and sel_prod:
                cost, def_p = get_product_info(sel_prod)
                fp = sel_price if sel_price > 0 else def_p
                st.session_state.cart.append({"product": sel_prod, "qty": sel_qty, "price_1": fp, "cost_1": cost, "total_sum": fp * sel_qty, "total_cost": cost * sel_qty})
                st.rerun()

        if sel_prod:
            p_data = df_products[df_products["Наименование"] == sel_prod].iloc[0]
            st.markdown("<br>", unsafe_allow_html=True)
            ci, cd = st.columns([1, 8])
            with ci:
                img = get_image_uri(p_data.get("URL фото", ""))
                if img: st.image(img, use_container_width=True)
            with cd:
                st.markdown(f"**Остаток:** <span style='color:#3b82f6; font-weight:bold;'>{p_data.get('Остаток', 0)} шт</span> &nbsp;|&nbsp; **Цена:** {p_data.get('Цена продажи', 0)} ₴", unsafe_allow_html=True)
                st.caption(p_data.get("Описание", "Нет описания"))

    st.markdown("---")
    if st.session_state.cart:
        st.subheader("🛍️ Текущий чек")
        st.dataframe(pd.DataFrame(st.session_state.cart)[['product', 'qty', 'price_1', 'total_sum']].rename(columns={'product':'Товар','qty':'Кол-во','price_1':'Цена','total_sum':'Сумма'}), use_container_width=True)
        tot = sum(i['total_sum'] for i in st.session_state.cart)
        c_tot, c_clr = st.columns([4, 1])
        with c_tot: st.markdown(f"### Итого к оплате: <span style='color:#22c55e;'>{tot} ₴</span>", unsafe_allow_html=True)
        with c_clr:
            if st.button("🗑️ Очистить", use_container_width=True): st.session_state.cart = []; st.rerun()
        
        st.markdown("---")
        df_sales = load_table("Продажи")
        clients_db = {str(r.get("Телефон", "")).strip(): {"name": r.get("Клиент", ""), "del": r.get("Тип доставки", ""), "addr": r.get("Адрес", "")} for _, r in df_sales.iterrows() if str(r.get("Телефон", "")).strip()} if not df_sales.empty and "Телефон" in df_sales.columns else {}
        
        search_c = st.selectbox("🔍 Поиск клиента (Автозаполнение)", ["Новый клиент"] + list(clients_db.keys()))
        d_name, d_phone, d_del, d_addr = (clients_db[search_c]["name"], search_c, clients_db[search_c]["del"], clients_db[search_c]["addr"]) if search_c != "Новый клиент" else ("", "", get_settings("Доставка")[0] if get_settings("Доставка") else "", "")

        with st.form("checkout"):
            st.markdown("##### Данные доставки")
            cd1, cd2 = st.columns(2)
            with cd1:
                client = st.text_input("Имя клиента *", value=d_name)
                phone = st.text_input("Телефон *", value=d_phone)
                disc = st.number_input("Скидка на чек (₴)", min_value=0.0)
            with cd2:
                dels = get_settings("Доставка")
                delivery = st.selectbox("Доставка", dels, index=dels.index(d_del) if d_del in dels else 0)
                address = st.text_input("Адрес", value=d_addr)
                status = st.selectbox("Начальный статус", get_settings("Статусы заказов"))
                
            if st.form_submit_button("✅ ОФОРМИТЬ ЗАКАЗ", use_container_width=True):
                if client and phone:
                    oid = "ORD-" + str(uuid.uuid4())[:6].upper()
                    d_str = datetime.now().strftime("%d.%m.%Y %H:%M")
                    disc_item = disc / len(st.session_state.cart) if disc > 0 else 0
                    rows = [{"ID Заказа": oid, "Дата": d_str, "Статус": status, "ТТН": "", "Товар": i['product'], "Кол-во": i['qty'], "Цена 1шт": i['price_1'], "Сумма продажи": i['total_sum']-disc_item, "Себестоимость (общ)": i['total_cost'], "Чистая прибыль": (i['total_sum']-disc_item)-i['total_cost'], "Скидка": disc_item, "Клиент": client, "Телефон": phone, "Тип доставки": delivery, "Адрес": address, "Менеджер": st.session_state.username} for i in st.session_state.cart]
                    for i in st.session_state.cart: update_stock(i['product'], -i['qty'])
                    append_multiple_rows("Продажи", rows); log_action("Заказ", f"{oid} на {tot-disc}₴"); st.session_state.cart = []; st.cache_data.clear(); st.success(f"Оформлен {oid}"); time.sleep(1); st.rerun()
                else: st.error("Имя и Телефон обязательны.")

# --- УПРАВЛЕНИЕ ЗАКАЗАМИ СПИСКОМ ---
elif menu == "🚚 Заказы":
    st.markdown("<h3 style='color:#333;'>🚚 Обработка заказов</h3>", unsafe_allow_html=True)
    df_sales = load_table("Продажи")
    
    if not df_sales.empty and "ID Заказа" in df_sales.columns:
        df_orders = df_sales[df_sales["ID Заказа"] != ""]
        if not df_orders.empty:
            summary = []
            for oid, grp in df_orders.groupby("ID Заказа"):
                f = grp.iloc[0]
                summary.append({"Заказ №": oid, "Статус": f.get('Статус', ''), "Дата": f.get('Дата', ''), "Сумма": pd.to_numeric(grp['Сумма продажи'], errors='coerce').sum(), "Товары": ", ".join(grp['Товар'].tolist())[:50]+"...", "Клиент": f.get('Клиент', ''), "Телефон": f.get('Телефон', ''), "Доставка": f"{f.get('Тип доставки', '')} ({f.get('Адрес', '')})", "ТТН": f.get('ТТН', ''), "Менеджер": f.get('Менеджер', '')})
            
            df_sum = pd.DataFrame(summary).sort_values(by='Дата', ascending=False)
            
            c_left, c_right = st.columns([1.5, 6])
            
            with c_left:
                st.markdown("<div class='status-filter' style='background: white; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0;'>", unsafe_allow_html=True)
                st.markdown("<b style='color:#64748b;'>СТАТУСЫ ЗАКАЗОВ</b><br><br>", unsafe_allow_html=True)
                counts = df_sum['Статус'].value_counts().to_dict()
                options = [f"Все ({len(df_sum)})"] + [f"{get_status_color(s)} {s} ({counts.get(s,0)})" for s in get_settings("Статусы заказов")]
                sel_opt = st.radio("f", options, label_visibility="collapsed")
                sel_stat = sel_opt.split(" (")[0].split(" ", 1)[-1] if sel_opt.startswith("Все") == False else "Все"
                st.markdown("</div>", unsafe_allow_html=True)
                
            with c_right:
                filtered = df_sum[df_sum['Статус'] == sel_stat] if sel_stat != "Все" else df_sum
                
                if not filtered.empty:
                    # Вывод заказов интерактивными списками (Аккордеоны)
                    for _, r in filtered.iterrows():
                        oid = r['Заказ №']
                        icon = get_status_color(r['Статус'])
                        with st.expander(f"{icon} {oid} | {r['Дата']} | {r['Клиент']} | {r['Сумма']} ₴ | Статус: {r['Статус']}"):
                            o_items = df_orders[df_orders["ID Заказа"] == oid]
                            
                            st.write(f"**Доставка:** {r['Доставка']} | **Телефон:** {r['Телефон']} | **Менеджер:** {r['Менеджер']}")
                            st.dataframe(o_items[['Товар', 'Кол-во', 'Цена 1шт', 'Скидка', 'Сумма продажи']], use_container_width=True, hide_index=True)
                            
                            st.markdown("---")
                            c_st, c_tn, c_bt = st.columns([2, 2, 1])
                            with c_st: n_st = st.selectbox("Изменить статус", get_settings("Статусы заказов"), index=get_settings("Статусы заказов").index(r["Статус"]) if r["Статус"] in get_settings("Статусы заказов") else 0, key=f"st_{oid}")
                            with c_tn: n_ttn = st.text_input("ТТН", value=r["ТТН"], key=f"ttn_{oid}")
                            with c_bt:
                                st.write("")
                                if st.button("💾 Сохранить", key=f"sv_{oid}", use_container_width=True): 
                                    update_order_details(oid, n_st, n_ttn); log_action("Смена статуса", f"{oid} -> {n_st}"); st.cache_data.clear(); st.rerun()

                            ce, ca = st.columns(2)
                            with ce:
                                with st.popover("✏️ Редактировать / Удалить товар"):
                                    si = st.selectbox("Товар", o_items['Товар'].tolist(), key=f"si_{oid}")
                                    if si:
                                        i_d = o_items[o_items['Товар'] == si].iloc[0]
                                        with st.form(f"fe_{oid}"):
                                            eq = st.number_input("Кол-во", value=float(i_d['Кол-во']))
                                            ep = st.number_input("Цена 1шт", value=float(i_d['Цена 1шт']))
                                            ed = st.number_input("Скидка", value=float(i_d['Скидка']) if i_d['Скидка'] else 0.0)
                                            if st.form_submit_button("Обновить"): update_single_sale_row(oid, si, eq, ep, ed); log_action("Изменен товар", f"{oid} - {si}"); st.cache_data.clear(); st.rerun()
                                        if st.button("❌ Удалить из чека", key=f"del_{oid}", type="primary"): delete_single_sale_row(oid, si); log_action("Удален товар", f"{oid} - {si}"); st.cache_data.clear(); st.rerun()
                            with ca:
                                with st.popover("➕ Добавить товар"):
                                    da = load_table("Товары")
                                    ap = st.selectbox("Новый Товар", [""] + (da["Наименование"].tolist() if not da.empty else []), key=f"ap_{oid}")
                                    with st.form(f"fa_{oid}"):
                                        aq = st.number_input("Кол-во", min_value=1.0)
                                        apr = st.number_input("Цена (0=баз)", min_value=0.0)
                                        if st.form_submit_button("Добавить") and ap: _, dp = get_product_info(ap); add_item_to_order(oid, ap, aq, apr if apr>0 else dp, 0.0); log_action("Добавлен товар", f"{oid} + {ap}"); st.cache_data.clear(); st.rerun()
                else:
                    st.info(f"В статусе '{sel_stat}' нет заказов.")
        else: st.info("Нет оформленных заказов.")
    else: st.info("Загрузка данных или нет продаж...")

# --- КАТАЛОГ С ПОПАПАМИ ---
elif menu == "🖼️ Каталог":
    st.markdown("<h3 style='color:#333;'>🖼️ Визуальный каталог</h3>", unsafe_allow_html=True)
    df = load_table("Товары")
    if not df.empty:
        lst = df.to_dict('records')
        cols_n = 6 
        for i in range(0, len(lst), cols_n):
            cols = st.columns(cols_n)
            for j in range(cols_n):
                if i+j < len(lst):
                    p = lst[i+j]
                    with cols[j]:
                        st.markdown("<div style='background:white; padding:10px; border-radius:8px; border:1px solid #e2e8f0; text-align:center;'>", unsafe_allow_html=True)
                        img = get_image_uri(p.get("URL фото", ""))
                        if img: st.image(img, use_container_width=True)
                        else: st.markdown("<div style='height:100px; background:#f8fafc; display:flex; align-items:center; justify-content:center; color:#94a3b8; border-radius:4px;'>Нет фото</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size:12px; font-weight:bold; margin-top:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;' title='{p.get('Наименование')}'>{p.get('Наименование')}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='font-size:12px; color:#64748b;'>Цена: {p.get('Цена продажи',0)} ₴<br>Ост: <b style='color:#3b82f6'>{p.get('Остаток',0)}</b></div>", unsafe_allow_html=True)
                        
                        with st.popover("✏️ Ред."):
                            with st.form(key=f"e_{p.get('ID')}"):
                                en = st.text_input("Имя", value=p.get('Наименование', ''))
                                ec = st.selectbox("Категория", get_settings("Категории"), index=get_settings("Категории").index(p.get("Категория", "")) if p.get("Категория", "") in get_settings("Категории") else 0)
                                epr = st.number_input("Цена", value=float(pd.to_numeric(p.get("Цена продажи", 0), errors='coerce') or 0))
                                eco = st.number_input("Себест.", value=float(pd.to_numeric(p.get("Себестоимость", 0), errors='coerce') or 0))
                                est = st.number_input("Остаток", value=float(pd.to_numeric(p.get("Остаток", 0), errors='coerce') or 0))
                                eu = st.text_input("URL фото", value=p.get("URL фото", ""))
                                ed = st.text_area("Опис.", value=p.get("Описание", ""))
                                if st.form_submit_button("Сохранить"): update_product_details_by_id(p.get('ID'), en, ec, est, eco, epr, eu, ed); st.cache_data.clear(); st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)
            st.write("")

# --- БАЗА КЛИЕНТОВ ---
elif menu == "👥 Клиенты":
    st.markdown("<h3 style='color:#333;'>👥 База клиентов (LTV)</h3>", unsafe_allow_html=True)
    df_sales = load_table("Продажи")
    if not df_sales.empty and "Телефон" in df_sales.columns:
        df_clients = df_sales[df_sales["Телефон"].str.strip() != ""]
        df_clients['Сумма продажи'] = pd.to_numeric(df_clients['Сумма продажи'], errors='coerce').fillna(0)
        c_stats = df_clients.groupby('Телефон').agg(Имя=('Клиент', 'last'), Сумма=('Сумма продажи', 'sum'), Заказов=('ID Заказа', 'nunique')).reset_index().sort_values(by='Сумма', ascending=False)
        st.dataframe(c_stats, use_container_width=True, hide_index=True)

# --- ЗАКУПКИ И СПИСАНИЯ С ИСТОРИЕЙ ---
elif menu == "📥 Закупки":
    st.markdown("<h3 style='color:#333;'>📥 Приход товара</h3>", unsafe_allow_html=True)
    df_products = load_table("Товары")
    with st.form("purchase"):
        prod = st.selectbox("Товар", [""] + (df_products["Наименование"].tolist() if not df_products.empty else []))
        c1, c2, c3 = st.columns(3)
        with c1: qty = st.number_input("Количество", min_value=1.0)
        with c2: sum_uah = st.number_input("Сумма (грн)", min_value=0.0)
        with c3: prov = st.selectbox("Поставщик", get_settings("Поставщики"))
        if st.form_submit_button("Сохранить приход") and prod:
            cost_per = sum_uah / qty if qty > 0 else 0
            append_row("Закупки", {"Дата": datetime.now().strftime("%d.%m.%Y %H:%M"), "Товар": prod, "Кол-во": qty, "Сумма (грн)": sum_uah, "Себестоимость 1шт": cost_per, "Поставщик": prov, "Сотрудник": st.session_state.username})
            update_stock(prod, qty); log_action("Закупка", f"{prod}: {qty} шт"); st.cache_data.clear(); st.rerun()
    
    st.markdown("---")
    st.subheader("📜 История закупок")
    st.dataframe(load_table("Закупки").iloc[::-1], use_container_width=True, hide_index=True)

elif menu == "🗑️ Списание":
    st.markdown("<h3 style='color:#333;'>🗑️ Списание</h3>", unsafe_allow_html=True)
    df_products = load_table("Товары")
    with st.form("writeoff"):
        prod = st.selectbox("Товар", [""] + (df_products["Наименование"].tolist() if not df_products.empty else []))
        qty = st.number_input("Количество", min_value=1.0)
        reason = st.selectbox("Причина", get_settings("Причины списания"))
        if st.form_submit_button("Списать") and prod:
            c, _ = get_product_info(prod); append_row("Списания", {"Дата": datetime.now().strftime("%d.%m.%Y %H:%M"), "Товар": prod, "Кол-во": qty, "Сумма убытка": c * qty, "Причина": reason, "Сотрудник": st.session_state.username})
            update_stock(prod, -qty); log_action("Списание", f"{prod}: {qty} шт"); st.cache_data.clear(); st.rerun()
            
    st.markdown("---")
    st.subheader("📜 История списаний")
    st.dataframe(load_table("Списания").iloc[::-1], use_container_width=True, hide_index=True)

elif menu == "📦 Склад":
    st.markdown("<h3 style='color:#333;'>📦 Добавить товар</h3>", unsafe_allow_html=True)
    with st.form("add_product"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Наименование *")
            cat = st.selectbox("Категория", get_settings("Категории"))
            photo_file = st.file_uploader("Загрузить фото с ПК", type=["png", "jpg", "jpeg"])
        with c2:
            cost = st.number_input("Себестоимость (₴)", min_value=0.0)
            price = st.number_input("Цена продажи (₴)", min_value=0.0)
            stock = st.number_input("Остаток", min_value=0.0)
        if st.form_submit_button("Добавить в базу") and name:
            new_id = str(uuid.uuid4())[:6].upper()
            fp = ""
            if photo_file:
                os.makedirs("img_uploads", exist_ok=True); ext = photo_file.name.split('.')[-1]; fp = f"img_uploads/{new_id}.{ext}"
                with open(fp, "wb") as f: f.write(photo_file.getbuffer())
            append_row("Товары", {"ID": new_id, "Наименование": name, "Категория": cat, "Остаток": stock, "Себестоимость": cost, "Цена продажи": price, "URL фото": fp})
            st.cache_data.clear(); st.rerun()
            
    st.markdown("---")
    st.subheader("Полная таблица склада (Чтение)")
    st.dataframe(load_table("Товары"), use_container_width=True, hide_index=True)

# --- АДМИН ПАНЕЛЬ ---
elif menu == "📊 Дашборд":
    st.markdown("<h3 style='color:#333;'>📊 Дашборд</h3>", unsafe_allow_html=True)
    ds = load_table("Продажи"); ds['Сумма продажи'] = pd.to_numeric(ds['Сумма продажи'], errors='coerce').fillna(0); ds['Чистая прибыль'] = pd.to_numeric(ds['Чистая прибыль'], errors='coerce').fillna(0)
    c1, c2, c3 = st.columns(3)
    c1.metric("💳 Общая Выручка", f"{ds['Сумма продажи'].sum():,.0f} ₴")
    c2.metric("💰 Прибыль", f"{ds['Чистая прибыль'].sum():,.0f} ₴")
    c3.metric("📝 Заказов", ds['ID Заказа'].nunique() if "ID Заказа" in ds.columns else 0)
    
    st.subheader("Последние продажи")
    st.dataframe(ds[['Дата', 'Товар', 'Сумма продажи', 'Менеджер']].tail(10).iloc[::-1], use_container_width=True, hide_index=True)

elif menu == "📈 Отчеты":
    st.title("📈 Сводный отчет руководителя")
    
    st.markdown("### 📅 Выбор периода")
    col_d1, col_d2 = st.columns(2)
    with col_d1: start_date = st.date_input("От", pd.to_datetime("today") - pd.Timedelta(days=30))
    with col_d2: end_date = st.date_input("До", pd.to_datetime("today"))
        
    df_sales, df_purchases, df_finance, df_writeoffs, df_products = load_table("Продажи"), load_table("Закупки"), load_table("Финансы"), load_table("Списания"), load_table("Товары")
    
    def filter_by_date(df):
        if df.empty or 'Дата' not in df.columns: return pd.DataFrame()
        df['DateObj'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M', errors='coerce')
        return df.loc[(df['DateObj'].dt.date >= start_date) & (df['DateObj'].dt.date <= end_date)]

    ps, pp, pf, pw = filter_by_date(df_sales), filter_by_date(df_purchases), filter_by_date(df_finance), filter_by_date(df_writeoffs)
    
    rev, gross, orders = 0, 0, 0
    if not ps.empty:
        ps['Сумма продажи'] = pd.to_numeric(ps['Сумма продажи'], errors='coerce').fillna(0); ps['Чистая прибыль'] = pd.to_numeric(ps['Чистая прибыль'], errors='coerce').fillna(0)
        rev, gross = ps['Сумма продажи'].sum(), ps['Чистая прибыль'].sum()
        if "ID Заказа" in ps.columns: orders = ps[ps["ID Заказа"] != ""]["ID Заказа"].nunique()
    
    w_sum, w_qty = 0, 0
    if not pw.empty:
        pw['Сумма убытка'] = pd.to_numeric(pw['Сумма убытка'], errors='coerce').fillna(0); pw['Кол-во'] = pd.to_numeric(pw['Кол-во'], errors='coerce').fillna(0)
        w_sum, w_qty = pw['Сумма убытка'].sum(), pw['Кол-во'].sum()
        
    exp = pd.to_numeric(pf[pf['Тип операции'] == 'Расход']['Сумма (грн)'], errors='coerce').sum() if not pf.empty else 0
    net = gross - exp - w_sum
    
    st.markdown("---")
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("🔻 Списание", f"{w_sum:,.0f} ₴")
    k2.metric("📦 Заказы", f"{orders}")
    k3.metric("💳 Выручка", f"{rev:,.0f} ₴")
    k4.metric("💰 Маржа", f"{gross:,.0f} ₴")
    k5.metric("🧾 Расходы", f"{exp:,.0f} ₴")
    k6.metric("💎 ПРИБЫЛЬ", f"{net:,.0f} ₴")
    k7.metric("📈 Ср. чек", f"{(rev/orders if orders>0 else 0):,.0f} ₴")
    st.markdown("---")
    
    cl, cm, cr = st.columns([1.2, 1.2, 1])
    with cl:
        st.subheader("📊 Выручка по дням")
        if not ps.empty: st.bar_chart(ps.groupby(ps['DateObj'].dt.date)['Сумма продажи'].sum())
        st.subheader("👥 ТОП Клиентов")
        if not ps.empty: st.dataframe(ps.groupby('Клиент').agg(Сумма=('Сумма продажи', 'sum'), Заказов=('ID Заказа', 'nunique')).sort_values('Сумма', ascending=False).head(5).reset_index(), use_container_width=True, hide_index=True)
    with cm:
        st.subheader("🔥 ТОП Товаров")
        if not ps.empty:
            ps['Кол-во'] = pd.to_numeric(ps['Кол-во'], errors='coerce').fillna(0)
            t = ps.groupby('Товар').agg(Прибыль=('Чистая прибыль', 'sum'), Кол_во=('Кол-во', 'sum')).sort_values('Прибыль', ascending=False).reset_index()
            t['%'] = (t['Прибыль'] / gross * 100).round(1).astype(str) + "%" if gross > 0 else "0%"
            st.dataframe(t.head(10), use_container_width=True, hide_index=True)
        st.subheader("📉 Расходы")
        if not pf.empty:
            edf = pf[pf['Тип операции'] == 'Расход']
            if not edf.empty: st.dataframe(edf.groupby('Категория')['Сумма (грн)'].sum().sort_values(ascending=False).reset_index(), use_container_width=True, hide_index=True)
    with cr:
        st.subheader("🏷️ По Категориям")
        if not df_products.empty and not ps.empty:
            cmap = dict(zip(df_products['Наименование'], df_products['Категория']))
            ps['Кат'] = ps['Товар'].map(cmap).fillna("Без категории")
            scat = st.selectbox("Категория:", ["Все"] + list(ps['Кат'].unique()))
            csales = ps[ps['Кат'] == scat] if scat != "Все" else ps
            st.write(f"**Сумма:** {csales['Сумма продажи'].sum():,.0f} ₴")
            st.write(f"**Продано:** {csales['Кол-во'].sum():,.0f} шт")
        st.markdown("---")
        st.subheader("🛒 Закупки")
        if not pp.empty:
            pp['Сумма (грн)'] = pd.to_numeric(pp['Сумма (грн)'], errors='coerce').fillna(0); pp['Кол-во'] = pd.to_numeric(pp['Кол-во'], errors='coerce').fillna(0)
            st.write(f"**Штук:** {pp['Кол-во'].sum():,.0f}")
            st.write(f"**Сумма:** {pp['Сумма (грн)'].sum():,.0f} ₴")

elif menu == "💸 Финансы":
    st.markdown("<h3 style='color:#333;'>💸 Финансы</h3>", unsafe_allow_html=True)
    with st.form("ff"):
        c1, c2 = st.columns(2)
        with c1: tf = st.radio("Тип", ["Расход", "Приход"], horizontal=True); cf = st.selectbox("Кат", get_settings("Категории финансов"))
        with c2: sf = st.number_input("Сумма", min_value=1.0); cm = st.text_input("Коммент")
        if st.form_submit_button("Сохранить"): append_row("Финансы", {"Дата": datetime.now().strftime("%d.%m.%Y %H:%M"), "Тип операции": tf, "Категория": cf, "Сумма (грн)": sf, "Комментарий": cm, "Сотрудник": st.session_state.username}); st.cache_data.clear(); st.rerun()
    
    st.markdown("---")
    st.subheader("📜 История финансов")
    st.dataframe(load_table("Финансы").iloc[::-1], use_container_width=True, hide_index=True)

elif menu == "📜 Логи":
    st.markdown("<h3 style='color:#333;'>📜 Логи системы (Аудит)</h3>", unsafe_allow_html=True)
    st.dataframe(load_table("Логи").iloc[::-1], use_container_width=True, hide_index=True)

elif menu == "⚙️ Настройки":
    st.markdown("<h3 style='color:#333;'>⚙️ Настройки системы</h3>", unsafe_allow_html=True)
    st.info("Изменение паролей пользователей и ролей доступно в файле **users.json** в папке с программой.")
    
    def add_s(c, v):
        ws = db.worksheet("Настройки"); h = ws.row_values(1)
        if c in h: ws.update_cell(len(ws.col_values(h.index(c)+1)) + 1, h.index(c)+1, v)
        
    c1, c2 = st.columns(2)
    with c1:
        with st.form("fc"): 
            nc = st.text_input("Новая категория товара")
            if st.form_submit_button("Добавить") and nc: add_s("Категории", nc); st.cache_data.clear(); st.rerun()
        with st.form("fs"): 
            ns = st.text_input("Новый статус заказа")
            if st.form_submit_button("Добавить") and ns: add_s("Статусы заказов", ns); st.cache_data.clear(); st.rerun()
        with st.form("fd"): 
            nd = st.text_input("Новая служба доставки")
            if st.form_submit_button("Добавить") and nd: add_s("Доставка", nd); st.cache_data.clear(); st.rerun()
            
    with c2:
        with st.form("ffc"): 
            nf = st.text_input("Новая категория финансов (Расходы/Приходы)")
            if st.form_submit_button("Добавить") and nf: add_s("Категории финансов", nf); st.cache_data.clear(); st.rerun()
        with st.form("fp"): 
            np = st.text_input("Новый поставщик")
            if st.form_submit_button("Добавить") and np: add_s("Поставщики", np); st.cache_data.clear(); st.rerun()
        with st.form("fr"): 
            nr = st.text_input("Новая причина списания")
            if st.form_submit_button("Добавить") and nr: add_s("Причины списания", nr); st.cache_data.clear(); st.rerun()

    st.markdown("---")
    if st.button("🔧 Починить структуру таблиц (Обновить API)", type="primary"):
        with st.spinner("Синхронизация..."):
            verify_and_create_structure.clear(); verify_and_create_structure(); st.cache_data.clear()
        st.success("Структура обновлена!"); time.sleep(2); st.rerun()

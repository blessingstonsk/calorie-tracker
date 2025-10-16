# Calorie Tracker Web App (Streamlit) — Full Featured
# File: calorie_tracker_streamlit.py
# Run: pip install streamlit pandas matplotlib bcrypt sqlalchemy
# Then: streamlit run calorie_tracker_streamlit.py

"""
Features included:
- User accounts (register/login) stored locally with hashed passwords (bcrypt)
- Per-user data isolation (each user's foods and logs saved separately)
- Food database with macros (kcal, protein, carbs, fat per 100g)
- Add custom foods
- Log entries with meal category (Breakfast/Lunch/Dinner/Snack)
- Daily calorie goal & per-meal targets
- Cumulative daily view with macros breakdown
- Historical trends: 7/30/90 day charts for calories and macros
- Export CSV and simple data management (delete entries)

Notes:
- This app stores data in a local SQLite DB (calorie_tracker_full.db) in the same folder.
- For production or multi-device syncing, replace SQLite with a remote DB + authentication system.
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import bcrypt
import io

DB_PATH = "calorie_tracker.db"

# ----------------------
# Database & helpers
# ----------------------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    # users
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash BLOB
        )
    ''')
    # foods per user
    c.execute('''
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            kcal_per_100g REAL,
            protein_per_100g REAL,
            carbs_per_100g REAL,
            fat_per_100g REAL,
            UNIQUE(user_id, name)
        )
    ''')
    # logs per user
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            entry_date TEXT,
            time TEXT,
            food TEXT,
            weight_g REAL,
            kcal REAL,
            protein REAL,
            carbs REAL,
            fat REAL,
            meal TEXT
        )
    ''')
    # user settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER PRIMARY KEY,
            daily_goal REAL DEFAULT 2000,
            breakfast_target REAL DEFAULT 25,
            lunch_target REAL DEFAULT 35,
            dinner_target REAL DEFAULT 30,
            snack_target REAL DEFAULT 10
        )
    ''')
    conn.commit()
    conn.close()


# ----------------------
# Auth
# ----------------------

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())


def check_password(password: str, pw_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), pw_hash)
    except Exception:
        return False


def create_user(username: str, password: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    try:
        pw_hash = hash_password(password)
        c.execute("INSERT INTO users (username, password_hash) VALUES (?,?)", (username, pw_hash))
        conn.commit()
        user_id = c.lastrowid
        # create default settings row
        c.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def authenticate(username: str, password: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        user_id, pw_hash = row[0], row[1]
        if check_password(password, pw_hash):
            return user_id
    return None


# ----------------------
# Food & log operations
# ----------------------

def add_food(user_id, name, kcal, protein, carbs, fat):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR REPLACE INTO foods (user_id, name, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g) VALUES (?,?,?,?,?,?)",
            (user_id, name.lower(), kcal, protein, carbs, fat)
        )
        conn.commit()
    finally:
        conn.close()


def get_foods(user_id):
    conn = get_conn()
    df = pd.read_sql_query("SELECT name, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g FROM foods WHERE user_id = ? ORDER BY name",
                           conn, params=(user_id,))
    conn.close()
    return df


def log_food(user_id, entry_date, time_str, food, weight_g, kcal, protein, carbs, fat, meal):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, entry_date, time, food, weight_g, kcal, protein, carbs, fat, meal) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (user_id, entry_date, time_str, food.lower(), weight_g, kcal, protein, carbs, fat, meal))
    conn.commit()
    conn.close()


def get_logs_for_date(user_id, entry_date):
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, time, food, weight_g, kcal, protein, carbs, fat, meal FROM logs WHERE user_id = ? AND entry_date = ? ORDER BY id",
                           conn, params=(user_id, entry_date))
    conn.close()
    return df


def delete_log(user_id, log_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM logs WHERE user_id = ? AND id = ?", (user_id, log_id))
    conn.commit()
    conn.close()


def get_settings(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT daily_goal, breakfast_target, lunch_target, dinner_target, snack_target FROM settings WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        # insert default
        c.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
        conn.commit()
        c.execute("SELECT daily_goal, breakfast_target, lunch_target, dinner_target, snack_target FROM settings WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    conn.close()
    return {
        'daily_goal': row[0],
        'breakfast_target': row[1],
        'lunch_target': row[2],
        'dinner_target': row[3],
        'snack_target': row[4]
    }


def update_settings(user_id, daily_goal, breakfast_target, lunch_target, dinner_target, snack_target):
    conn = get_conn()
    c = conn.cursor()
    c.execute("REPLACE INTO settings (user_id, daily_goal, breakfast_target, lunch_target, dinner_target, snack_target) VALUES (?,?,?,?,?,?)",
              (user_id, daily_goal, breakfast_target, lunch_target, dinner_target, snack_target))
    conn.commit()
    conn.close()


# ----------------------
# Utility calculations
# ----------------------

def calc_from_food_row(row, weight_g):
    kcal = row['kcal_per_100g'] * weight_g / 100.0
    protein = row['protein_per_100g'] * weight_g / 100.0
    carbs = row['carbs_per_100g'] * weight_g / 100.0
    fat = row['fat_per_100g'] * weight_g / 100.0
    return kcal, protein, carbs, fat


# ----------------------
# Seed example foods for a user (used when user has no foods)
# ----------------------
def seed_example_foods_for_user(user_id):
    sample = [
        ("rice",130,2.7,28.0,0.3),
        ("roti",120,3.6,20.0,1.0),
        ("chicken",165,31.0,0.0,3.6),
        ("egg",155,13.0,1.1,11.0),
        ("milk",60,3.2,5.0,3.3),
        ("apple",52,0.3,14.0,0.2),
        ("banana",89,1.1,23.0,0.3),
        ("paneer",265,18.0,1.2,20.8),
        ("dal",116,9.0,20.0,1.0),
        ("oats",389,17.0,66.0,7.0)
    ]
    for name,kcal,protein,carbs,fat in sample:
        add_food(user_id, name, kcal, protein, carbs, fat)


# ----------------------
# Charts & history
# ----------------------

def get_history(user_id, days):
    today = date.today()
    start = today - timedelta(days=days-1)
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT entry_date, SUM(kcal) as kcal, SUM(protein) as protein, SUM(carbs) as carbs, SUM(fat) as fat FROM logs WHERE user_id = ? AND entry_date >= ? GROUP BY entry_date ORDER BY entry_date",
        conn, params=(user_id, start.isoformat())
    )
    conn.close()
    if df.empty:
        # fill with zeros for continuity
        idx = pd.date_range(start=start, end=today)
        df = pd.DataFrame({'entry_date': idx.strftime('%Y-%m-%d'), 'kcal':0, 'protein':0, 'carbs':0, 'fat':0})
    else:
        # ensure all days present
        idx = pd.date_range(start=start, end=today).strftime('%Y-%m-%d')
        df = df.set_index('entry_date').reindex(idx, fill_value=0).reset_index().rename(columns={'index':'entry_date'})
    return df


# ----------------------
# Streamlit UI
# ----------------------

st.set_page_config(page_title="Calorie Tracker — Full", layout="wide")
init_db()

if 'user_id' not in st.session_state:
    st.session_state.user_id = None

st.title("🍏 Calorie Tracker — Full Web App")

# --- Authentication ---
with st.sidebar:
    st.header("Account")
    auth_mode = st.radio("Choose", ['Login','Register','Logout' if st.session_state.user_id else 'Login'])
    if auth_mode == 'Register':
        new_user = st.text_input('Username (register)')
        new_pw = st.text_input('Password', type='password')
        if st.button('Create account'):
            if not new_user or not new_pw:
                st.error('Provide username and password')
            else:
                ok = create_user(new_user, new_pw)
                if ok:
                    st.success('Account created. Please login.')
                else:
                    st.error('Username already exists')
    elif auth_mode == 'Login':
        user = st.text_input('Username')
        pw = st.text_input('Password', type='password')
        if st.button('Login'):
            uid = authenticate(user, pw)
            if uid:
                st.session_state.user_id = uid
                st.rerun()
            else:
                st.error('Invalid credentials')
    else:  # Logout
        if st.session_state.user_id:
            if st.button('Logout'):
                st.session_state.user_id = None
                st.experimental_rerun()

# If not logged in, show a landing and exit
if not st.session_state.user_id:
    st.info('Please register or login from the sidebar to use the full app.')
    st.markdown('---')
    st.markdown('**Features available after login:** user-specific foods, logs, settings, historical charts, CSV export.')
    st.stop()

user_id = st.session_state.user_id
st.sidebar.success(f'Logged in as user id: {user_id}')

# Ensure user has some sample foods
foods_df = get_foods(user_id)
if foods_df.empty:
    seed_example_foods_for_user(user_id)
    foods_df = get_foods(user_id)

# Settings
st.sidebar.header('Settings & Targets')
settings = get_settings(user_id)
with st.sidebar.form('settings_form'):
    daily_goal = st.number_input('Daily calorie goal (kcal)', min_value=500, max_value=10000, value=int(settings['daily_goal']), step=50)
    st.markdown('Set per-meal % targets (should sum roughly to 100)')
    b_target = st.slider('Breakfast %', 0, 100, int(settings['breakfast_target']))
    l_target = st.slider('Lunch %', 0, 100, int(settings['lunch_target']))
    d_target = st.slider('Dinner %', 0, 100, int(settings['dinner_target']))
    s_target = st.slider('Snack %', 0, 100, int(settings['snack_target']))
    if st.form_submit_button('Save settings'):
        update_settings(user_id, daily_goal, b_target, l_target, d_target, s_target)
        st.sidebar.success('Settings saved')

# Main layout: left = log, right = history & DB
left, right = st.columns((2,1))

with left:
    st.header('Log a food entry')
    col1, col2 = st.columns([2,1])
    foods_df = get_foods(user_id)
    food_options = list(foods_df['name'])
    with col1:
        food_choice = st.selectbox('Choose food (or add custom below)', options=food_options)
    with col2:
        weight = st.number_input('Weight (g)', min_value=1.0, value=100.0, step=1.0)

    meal = st.selectbox('Meal', ['Breakfast','Lunch','Dinner','Snack'])

    if st.button('Add entry'):
        # lookup
        row = foods_df[foods_df['name'] == food_choice].iloc[0]
        kcal, protein, carbs, fat = calc_from_food_row(row, weight)
        log_food(user_id, date.today().isoformat(), datetime.now().strftime('%H:%M:%S'), food_choice, float(weight), float(kcal), float(protein), float(carbs), float(fat), meal)
        st.success(f'Logged {food_choice} — {weight}g — {kcal:.2f} kcal')
        st.rerun()

    st.markdown('---')
    st.subheader('Add / Edit custom food')
    with st.form('add_food'):
        name = st.text_input('Food name')
        kcal = st.number_input('kcal per 100g', min_value=0.0, value=100.0)
        protein = st.number_input('protein per 100g (g)', min_value=0.0, value=0.0)
        carbs = st.number_input('carbs per 100g (g)', min_value=0.0, value=0.0)
        fat = st.number_input('fat per 100g (g)', min_value=0.0, value=0.0)
        add_sub = st.form_submit_button('Add / Update food')
        if add_sub:
            if not name.strip():
                st.error('Food name cannot be empty')
            else:
                add_food(user_id, name.strip().lower(), float(kcal), float(protein), float(carbs), float(fat))
                st.success('Food added/updated')
                st.experimental_rerun()

    st.markdown('---')
    # Today's log and summary
    st.subheader(f"Today's log — {date.today().isoformat()}")
    logs_df = get_logs_for_date(user_id, date.today().isoformat())
    if logs_df.empty:
        st.info('No entries for today yet')
    else:
        st.dataframe(logs_df[['id','time','meal','food','weight_g','kcal','protein','carbs','fat']].rename(columns={'id':'ID','time':'Time','meal':'Meal','food':'Food','weight_g':'Weight(g)','kcal':'kcal','protein':'Protein(g)','carbs':'Carbs(g)','fat':'Fat(g)'}))
        # delete option
        st.write('Delete an entry:')
        del_id = st.number_input('Log ID to delete (enter ID from table)', min_value=0, value=0, step=1)
        if st.button('Delete entry'):
            if del_id > 0:
                delete_log(user_id, int(del_id))
                st.success('Deleted')
                st.experimental_rerun()

    # Summary
    total_kcal = logs_df['kcal'].sum() if not logs_df.empty else 0.0
    total_pro = logs_df['protein'].sum() if not logs_df.empty else 0.0
    total_carbs = logs_df['carbs'].sum() if not logs_df.empty else 0.0
    total_fat = logs_df['fat'].sum() if not logs_df.empty else 0.0

    st.metric('Total kcal today', f"{total_kcal:.2f}")
    st.metric('Protein (g)', f"{total_pro:.2f}")
    st.metric('Carbs (g)', f"{total_carbs:.2f}")
    st.metric('Fat (g)', f"{total_fat:.2f}")

    # progress bar
    settings = get_settings(user_id)
    remaining = settings['daily_goal'] - total_kcal
    st.write(f"Daily goal: {settings['daily_goal']} kcal — Remaining: {remaining:.2f} kcal")
    st.progress(min(max(total_kcal / max(settings['daily_goal'],1), 0.0), 1.0))

    # per-meal comparison
    st.markdown('---')
    st.subheader('Per meal breakdown (today)')
    if not logs_df.empty:
        meal_summary = logs_df.groupby('meal').agg({'kcal':'sum','protein':'sum','carbs':'sum','fat':'sum'}).reset_index()
        st.table(meal_summary.rename(columns={'kcal':'kcal','protein':'Protein','carbs':'Carbs','fat':'Fat'}))

    # export
    if not logs_df.empty:
        csv = logs_df.to_csv(index=False)
        st.download_button('Download today CSV', data=csv, file_name=f'calorie_log_{date.today().isoformat()}.csv')

with right:
    st.header('History & Trends')
    days = st.selectbox('History range (days)', [7,30,90], index=0)
    hist_df = get_history(user_id, days)

    st.line_chart(hist_df.set_index('entry_date')[['kcal']])
    st.write('Macros trend (g)')
    st.line_chart(hist_df.set_index('entry_date')[['protein','carbs','fat']])

    st.markdown('---')
    st.header('Food database')
    foods_df = get_foods(user_id)
    st.dataframe(foods_df.rename(columns={'name':'Food','kcal_per_100g':'kcal/100g','protein_per_100g':'Protein/100g','carbs_per_100g':'Carbs/100g','fat_per_100g':'Fat/100g'}))
    # export foods
    if not foods_df.empty:
        buf = io.StringIO()
        foods_df.to_csv(buf, index=False)
        st.download_button('Download foods CSV', data=buf.getvalue(), file_name=f'foods_user_{user_id}.csv')

# Footer
st.markdown("Made with ❤️ — track your calories easily!")



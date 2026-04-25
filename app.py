from dotenv import load_dotenv
load_dotenv()

import telebot
from flask import Flask, render_template, request, redirect
import sqlite3
import json
from datetime import datetime, timedelta
import requests
import os
from bot import bot, run_bot, notify_admin
from main import init_db, sync_images

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'glamping-secret-2026')

sync_images()
try:
    init_db()
except Exception as e:
    print(f"[DB] Ошибка инициализации БД: {e}")

chat_ids = list(map(str, (os.getenv('ADMIN_NICKNAME') or '').split(',')))

import uuid
from yookassa import Configuration, Payment

Configuration.account_id = os.getenv('SHOP_ID')
Configuration.secret_key = os.getenv('PAYMENT_TOKEN')


def get_holidays_path():
    if os.path.exists('/data'):
        return '/data/holidays.json'
    return 'data/holidays.json'


def load_holidays():
    path = get_holidays_path()
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []


def save_holidays(holidays):
    path = get_holidays_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(sorted(set(holidays)), f)


def get_special_dates():
    """Праздники из файла + выходные на 6 месяцев вперёд, без дублей"""
    try:
        special = set(load_holidays())
        today = datetime.today()
        end = today + timedelta(days=180)
        cur = today
        while cur <= end:
            if cur.weekday() >= 5:
                special.add(cur.strftime('%Y-%m-%d'))
            cur += timedelta(days=1)
        return sorted(special)
    except Exception as e:
        print(f"[get_special_dates] Ошибка: {e}")
        return []


def get_img_base():
    if os.path.exists('/data'):
        return '/data/img'
    return 'static/img'


def get_db_connection():
    if os.path.exists('/data'):
        db_path = '/data/glamping.db'
    else:
        db_path = 'data/glamping.db'
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/create_payment', methods=['POST'])
def create_payment():
    house_id = request.form.get('house_id')
    name = request.form.get('client_name')
    phone = request.form.get('client_phone')
    dates = request.form.get('booking_dates').strip()
    total_price = request.form.get('total_price')

    selected_service_ids = request.form.getlist('selected_services')
    if selected_service_ids:
        conn = get_db_connection()
        placeholders = ','.join(['?'] * len(selected_service_ids))
        rows = conn.execute(f'SELECT name FROM services WHERE id IN ({placeholders})', selected_service_ids).fetchall()
        conn.close()
        services_str = ", ".join(r['name'] for r in rows)
    else:
        services_str = ""

    idempotency_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {
            "value": f"{int(float(total_price))}.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": request.host_url + "thanks"
        },
        "capture": True,
        "description": f"Бронь дома №{house_id} ({name})",
        "metadata": {
            "house_id": house_id,
            "name": name,
            "phone": phone,
            "dates": dates,
            "services": services_str
        }
    }, idempotency_key)

    from flask import session
    session['payment_id'] = payment.id
    return redirect(payment.confirmation.confirmation_url)


@app.route('/thanks')
def thanks():
    from flask import session
    payment_id = session.pop('payment_id', None)
    if payment_id:
        try:
            payment = Payment.find_one(payment_id)
            if payment.status != 'succeeded':
                return redirect('/')
        except Exception as e:
            print(f"[PAYMENT CHECK] Ошибка: {e}")
            return redirect('/')
    else:
        return redirect('/')
    return render_template('thanks.html')


@app.route('/yookassa_webhook', methods=['POST'])
def yookassa_webhook():
    print("--- [DEBUG] Webhook от ЮKassa ---")
    event_json = request.json
    print(f"--- [DEBUG] {event_json} ---")

    if event_json.get('event') == 'payment.succeeded':
        payment_object = event_json.get('object')
        meta = payment_object.get('metadata')

        if meta:
            house_id = meta.get('house_id')
            client_name = meta.get('name')
            client_phone = meta.get('phone')
            dates = meta.get('dates')
            if ' — ' in dates:
                check_in, check_out = [d.strip() for d in dates.split(' — ')]
                check_in = datetime.strptime(check_in, '%d.%m.%Y').strftime('%Y-%m-%d')
                check_out = datetime.strptime(check_out, '%d.%m.%Y').strftime('%Y-%m-%d')
            elif 'to' in dates:
                check_in, check_out = [d.strip() for d in dates.split('to')]
            else:
                check_in = check_out = dates.strip()
            services = meta.get('services')
            amount = payment_object.get('amount', {}).get('value')

            print(f"[PAYMENT SUCCESS] Дом: {house_id} | Гость: {client_name} | Сумма: {amount} ₽")

            try:
                conn = get_db_connection()
                conn.execute('''
                    INSERT INTO bookings (house_id, client_name, client_phone, check_in, check_out, services, total_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (house_id, client_name, client_phone, check_in, check_out, services, amount))
                conn.commit()
                conn.close()
                print(f"--- [SUCCESS] Бронь для {client_name} сохранена ---")
            except Exception as e:
                print(f"--- [ERROR] Ошибка БД: {e} ---")

            try:
                sstr = f"Дом №{house_id}"
                if services:
                    sstr += ' + ' + services
                amount_display = int(float(amount))
                msg = (
                    f"💰 <b>НОВАЯ ОПЛАТА!</b>\n\n"
                    f"🏠 Бронь: {sstr}\n"
                    f"👤 Гость: {client_name}\n"
                    f"📞 Тел: <code>+7 {client_phone}</code>\n"
                    f"📅 Даты: {dates}\n"
                    f"💵 Сумма: {amount_display} ₽"
                )
                notify_admin(msg)
            except Exception as e:
                print(f"--- [ERROR] Уведомление: {e} ---")

    return 'OK', 200


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/oferta')
def oferta():
    return render_template('oferta.html')


@app.route('/')
def index():
    conn = get_db_connection()
    houses = conn.execute('SELECT * FROM houses').fetchall()
    conn.close()
    return render_template('index.html', houses=houses)


@app.route('/house/<int:house_id>')
def house_page(house_id):
    conn = get_db_connection()
    house = conn.execute('SELECT * FROM houses WHERE id = ?', (house_id,)).fetchone()
    booked_dates = conn.execute('SELECT check_in as "from", check_out as "to" FROM bookings WHERE house_id = ?',
                                (house_id,)).fetchall()
    all_services = conn.execute('SELECT * FROM services').fetchall()
    conn.close()

    if house is None:
        return "Домик не найден", 404

    folder_path = f'static/img/houses/house{house_id}'
    additional_images = []
    if os.path.exists(folder_path):
        files = os.listdir(folder_path)
        additional_images = sorted([
            f for f in files
            if f.startswith('image') and f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ])

    return render_template('house.html',
                           house=house,
                           images=additional_images,
                           booked_dates=[dict(ix) for ix in booked_dates],
                           holidays=get_special_dates(),
                           all_services=all_services)


def days_between(date1_str, date2_str):
    d1 = datetime.strptime(date1_str, "%Y-%m-%d")
    d2 = datetime.strptime(date2_str, "%Y-%m-%d")
    return abs((d2 - d1).days)


@app.route('/book/<int:house_id>', methods=['POST'])
def book_house(house_id):
    name = request.form.get('client_name')
    phone = request.form.get('client_phone')
    dates_raw = request.form.get('booking_dates')

    try:
        if " — " in dates_raw:
            start_str, end_str = dates_raw.split(" — ")
            check_in = datetime.strptime(start_str.strip(), '%d.%m.%Y').strftime('%Y-%m-%d')
            check_out = datetime.strptime(end_str.strip(), '%d.%m.%Y').strftime('%Y-%m-%d')
        else:
            check_in = check_out = datetime.strptime(dates_raw.strip(), '%d.%m.%Y').strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return "Ошибка формата дат", 400

    services_ids = request.form.getlist('selected_services')
    services_string = ",".join(services_ids) if services_ids else None

    conn = get_db_connection()
    house = conn.execute('SELECT price_per_night FROM houses WHERE id = ?', (house_id,)).fetchone()
    total_price = house['price_per_night'] * days_between(check_in, check_out)

    selected_ids = request.form.getlist('selected_services')
    if selected_ids:
        placeholders = ','.join(['?'] * len(selected_ids))
        services_data = conn.execute(f'SELECT price FROM services WHERE id IN ({placeholders})', selected_ids).fetchall()
        for s in services_data:
            total_price += s['price']

    conn.execute('''
        INSERT INTO bookings (house_id, client_name, client_phone, check_in, check_out, services, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (house_id, name, phone, check_in, check_out, ",".join(selected_ids), total_price))

    house = conn.execute('SELECT name FROM houses WHERE id = ?', (house_id,)).fetchone()
    services_data = conn.execute('SELECT id, name FROM services').fetchall()
    services_dict = {service['id']: service['name'] for service in services_data}

    ss = ''
    if services_string:
        servs = list(map(int, services_string.split(',')))
        for i in servs:
            ss += ' + ' + services_dict[i]

    conn.commit()
    conn.close()

    msg = (
        f"🌲 Новая бронь!\n"
        f"Сумма: {total_price} руб\n"
        f"🏠 {house['name']}{ss}\n"
        f"👤 {name}\n"
        f"📞 +7 {phone}\n"
        f"📅 {dates_raw}"
    )
    try:
        notify_admin(msg)
    except Exception as e:
        print(f"Бот не смог отправить уведомление: {e}")

    return "OK", 200


@app.route('/booking')
def booking_page():
    dates = request.args.get('dates')
    available_houses = []

    if not dates or " — " not in dates:
        return render_template('booking.html', houses=[], selected_dates=None)

    try:
        start_str, end_str = dates.split(" — ")
        conn = get_db_connection()
        all_houses = conn.execute('SELECT * FROM houses').fetchall()

        for house in all_houses:
            overlap = conn.execute('''
                SELECT id FROM bookings
                WHERE house_id = ? AND check_in < ? AND check_out > ?
            ''', (house['id'], end_str, start_str)).fetchone()
            if not overlap:
                available_houses.append(house)

        conn.close()
    except Exception as e:
        print(f"Ошибка фильтрации: {e}")

    return render_template('booking.html', houses=available_houses, selected_dates=dates)


@app.route('/houses')
def all_houses():
    conn = get_db_connection()
    houses = conn.execute('SELECT * FROM houses').fetchall()
    conn.close()
    return render_template('all_houses.html', houses=houses)


@app.route('/services')
def services():
    conn = get_db_connection()
    services_data = conn.execute('SELECT * FROM services').fetchall()
    conn.close()
    return render_template('services.html', services=services_data)


@app.route('/ping')
def ping():
    return "PONG", 200


@app.route('/debug_holidays')
def debug_holidays():
    path = get_holidays_path()
    return f"path={path}, exists={os.path.exists(path)}, data={load_holidays()}", 200


import threading
_bot_thread = threading.Thread(target=run_bot, daemon=True)
_bot_thread.start()
print("--- [BOT] Поток бота запущен ---")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 8080))
    print(f"--- [SERVER] Запуск на порту {port} ---")
    app.run(host='0.0.0.0', port=port)

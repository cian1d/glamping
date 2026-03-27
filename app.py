import telebot
from dotenv import load_dotenv
from flask import Flask, render_template, request
import sqlite3
from datetime import datetime
import requests
import os
from bot import bot, run_bot, notify_admin

app = Flask(__name__)

# Загружаем переменные из .env в окружение системы
load_dotenv()

# Читаем ID админа (или ник)
chat_id = os.getenv('ADMIN_NICKNAME')


# Функция-помощник для связи с базой
def get_db_connection():
    conn = sqlite3.connect('glamping.db')
    conn.row_factory = sqlite3.Row  # Это позволяет обращаться к колонкам по именам: house['name']
    return conn

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/oferta')
def oferta():
    return render_template('oferta.html')

# Главная страница
@app.route('/')
def index():
    conn = get_db_connection()
    # Получаем все домики из базы
    houses = conn.execute('SELECT * FROM houses').fetchall()
    conn.close()
    return render_template('index.html', houses=houses)


# Страница конкретного домика
@app.route('/house/<int:house_id>')
def house_page(house_id):
    conn = get_db_connection()
    house = conn.execute('SELECT * FROM houses WHERE id = ?', (house_id,)).fetchone()
    # Получаем уже существующие брони для календаря
    booked_dates = conn.execute('SELECT check_in as "from", check_out as "to" FROM bookings WHERE house_id = ?',
                                (house_id,)).fetchall()
    all_services = conn.execute('SELECT * FROM services').fetchall()
    conn.close()

    if house is None:
        return "Домик не найден", 404

    # --- ЛОГИКА ГАЛЕРЕИ ---
    folder_path = f'static/img/houses/house{house_id}'
    additional_images = []

    if os.path.exists(folder_path):
        # Читаем все файлы в папке
        files = os.listdir(folder_path)
        # Берем только те, что начинаются на 'image' и являются картинками
        additional_images = [f for f in files if f.startswith('image') and f.endswith(('.jpg', '.jpeg', '.png', '.JPG'))]
        additional_images.sort()  # Чтобы порядок был 1, 2, 3...

    return render_template('house.html',
                           house=house,
                           images=additional_images,
                           booked_dates=[dict(ix) for ix in booked_dates],
                           all_services=all_services)

def days_between(date1_str, date2_str):
    # Превращаем строки в объекты даты
    date_format = "%Y-%m-%d"
    d1 = datetime.strptime(date1_str, date_format)
    d2 = datetime.strptime(date2_str, date_format)

    # Вычитаем и берем модуль (abs), чтобы не важен был порядок дат
    delta = abs(d2 - d1)
    return delta.days

@app.route('/book/<int:house_id>', methods=['POST'])
def book_house(house_id):
    # 1. Вытаскиваем данные из полей формы
    name = request.form.get('client_name')
    phone = request.form.get('client_phone')
    dates_raw = request.form.get('booking_dates')  # "25.03.2026 to 28.03.2026"

    # 2. Магия парсинга дат
    # Нам нужно превратить их из "ДД.ММ.ГГГГ" в "ГГГГ-ММ-ДД" для SQL
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

    # Превращаем в строку "1,3"
    services_string = ",".join(services_ids) if services_ids else None

    # 3. Сохраняем в базу данных
    conn = get_db_connection()

    house = conn.execute('SELECT price_per_night FROM houses WHERE id = ?', (house_id,)).fetchone()

    total_price = house['price_per_night'] * days_between(check_in, check_out)

    # Получаем список ID выбранных услуг
    selected_ids = request.form.getlist('selected_services')

    if selected_ids:
        # Считаем сумму услуг из базы
        placeholders = ','.join(['?'] * len(selected_ids))
        services_data = conn.execute(f'SELECT price FROM services WHERE id IN ({placeholders})',
                                     selected_ids).fetchall()
        for s in services_data:
            total_price += s['price']


    conn.execute('''
        INSERT INTO bookings (house_id, client_name, client_phone, check_in, check_out, services, total_price) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (house_id, name, phone, check_in, check_out, ",".join(selected_ids), total_price))

    # Получаем название домика для Telegram, пока соединение открыто
    house = conn.execute('SELECT name FROM houses WHERE id = ?', (house_id,)).fetchone()

    services_data = conn.execute('SELECT id, name FROM services').fetchall()
    services_dict = {service['id']: service['name'] for service in services_data}

    servs = list(map(int, services_string.split(',')))
    ss = ''
    for i in servs:
        ss += ' + ' + services_dict[i]

    conn.commit()
    conn.close()

    # 4. Отправляем уведомление (эту функцию мы обсуждали раньше)
    msg = (
        f"🌲 Новая бронь!\n"
        f"Сумма: {total_price} руб\n"
        f"🏠 {house['name']}{ss}\n"
        f"👤 {name}\n"
        f"📞 +7 {phone}\n"
        f"📅 {dates_raw}"
    )
    print(msg)

    # Просто вызываем функцию из другого файла
    try:
        notify_admin(msg)
    except Exception as e:
        print(f"Бот не смог отправить уведомление: {e}")


    # 5. Возвращаем пользователя на страницу успеха или главную
    return "OK", 200


@app.route('/booking')
def booking_page():
    dates = request.args.get('dates')
    available_houses = []

    # Если пользователь еще не выбрал даты, возвращаем пустую страницу с календарем
    if not dates or " — " not in dates:
        return render_template('booking.html', houses=[], selected_dates=None)

    try:
        start_str, end_str = dates.split(" — ")
        conn = get_db_connection()

        # Получаем вообще все домики из базы
        all_houses = conn.execute('SELECT * FROM houses').fetchall()

        for house in all_houses:
            # Для каждого домика проверяем: есть ли хоть одна бронь, которая ПЕРЕСЕКАЕТСЯ с запросом
            # Логика та же, что при бронировании: (Заезд < Конец_поиска) И (Выезд > Начало_поиска)
            overlap = conn.execute('''
                SELECT id FROM bookings 
                WHERE house_id = ? 
                AND check_in < ? 
                AND check_out > ?
            ''', (house['id'], end_str, start_str)).fetchone()

            # Если пересечений (overlap) НЕТ, значит домик свободен — добавляем в список
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


# if __name__ == '__main__':
#     app.run(debug=True, port=8000)

import threading

if __name__ == '__main__':
    # Эта проверка — стальной щит от 409 ошибки во Flask
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        print("--- [DEBUG] Запуск бота в дочернем процессе Flask ---")
        import threading

        # Используем daemon=True, чтобы поток закрывался вместе с сервером
        t = threading.Thread(target=run_bot, daemon=True)
        t.start()

    app.run(debug=True, port=8000)


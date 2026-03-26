import telebot  # Рекомендую установить: pip install pyTelegramBotAPI
import sqlite3
from telebot import types
import os
import shutil
import time
from threading import Timer # Чтобы подождать, пока все фото из альбома дойдут
# Кто сейчас загружает фото? {chat_id: house_id}
user_upload_state = {}
# Хранилище для медиа: {media_group_id: [file_ids]}
album_data = {}

# {chat_id: {'service_id': 1, 'field': 'name'}}
edit_service_state = {}

TOKEN = str(open('static/token.txt').readline())
bot = telebot.TeleBot(TOKEN)

chat_id = str(open('static/nickname.txt').readline())

def get_db_connection():
    conn = sqlite3.connect('glamping.db')
    conn.row_factory = sqlite3.Row
    return conn


# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📋 Все бронирования")
    btn2 = types.KeyboardButton("🏠 Все домики")  # Новая кнопка
    btn3 = types.KeyboardButton("✨ Все доп. услуги")  # Новая кнопка
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, "Привет! Я бот-администратор.", reply_markup=markup)


# Обработка текстовых кнопок
@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    state = edit_service_state.get(chat_id)

    # --- ЛОГИКА ДОБАВЛЕНИЯ И РЕДАКТИРОВАНИЯ ---
    if state:
        # Если мы на этапе пошагового добавления новой услуги
        if 'step' in state:
            step = state['step']

            if step == 'name':
                state['name'] = message.text
                state['step'] = 'description'
                bot.send_message(chat_id, "Введите <b>описание</b> новой услуги:", parse_mode='HTML')

            elif step == 'description':
                state['description'] = message.text
                state['step'] = 'price'
                bot.send_message(chat_id, "Введите <b>стоимость</b> услуги (только число):", parse_mode='HTML')

            elif step == 'price':
                if not message.text.isdigit():
                    bot.send_message(chat_id, "❌ Ошибка! Введите цену цифрами:")
                    return
                state['price'] = int(message.text)
                state['step'] = 'photo'
                bot.send_message(chat_id, "Теперь отправьте <b>фотографию</b> для этой услуги:", parse_mode='HTML')
            return  # Выходим, чтобы не срабатывали проверки кнопок ниже

        # Если мы в режиме редактирования конкретного поля (твой старый код)
        elif 'field' in state:
            field = state['field']
            service_id = state['service_id']
            new_value = message.text

            if field == 'price':
                if not new_value.isdigit():
                    bot.send_message(chat_id, "❌ Цена должна быть числом:")
                    return
                new_value = int(new_value)

            conn = get_db_connection()
            conn.execute(f'UPDATE services SET {field} = ? WHERE id = ?', (new_value, service_id))
            conn.commit()
            conn.close()

            del edit_service_state[chat_id]
            bot.send_message(chat_id, "✅ Данные успешно обновлены!")
            show_services(message)
            return

    # --- ОБЫЧНЫЕ КНОПКИ МЕНЮ ---
    if message.text == "📋 Все бронирования":
        show_bookings(message)
    elif message.text == "🏠 Все домики":
        show_houses(message)
    elif message.text == "✨ Все доп. услуги":
        show_services(message)


def show_services(message):
    conn = get_db_connection()
    # Получаем все услуги из таблицы services
    services = conn.execute('SELECT id, name FROM services').fetchall()
    conn.close()

    if not services:
        bot.send_message(message.chat.id, "Список дополнительных услуг пока пуст.")
        return

    # Формируем текстовый список
    services_text = "<b>✨ Дополнительные услуги глэмпинга:</b>\n\n"
    markup = types.InlineKeyboardMarkup()

    for idx, service in enumerate(services, 1):
        services_text += f"{idx}. {service['name']}\n"

        # Создаем кнопку для каждой услуги
        # Пока оставляем callback_data='none', чтобы они были "мертвыми"
        btn = types.InlineKeyboardButton(
            text=f"⚙️ {service['name']}",
            callback_data=f"service_detail_{service['id']}"
        )
        markup.add(btn)
    # В конце функции show_services, перед отправкой сообщения:
    btn_add = types.InlineKeyboardButton("➕ Добавить новую услугу", callback_data="add_service_start")
    markup.add(btn_add)

    bot.send_message(
        message.chat.id,
        services_text,
        parse_mode='HTML',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "add_service_start")
def add_service_start(call):
    edit_service_state[call.message.chat.id] = {'step': 'name'}
    bot.send_message(call.message.chat.id, "Введите название новой услуги:")



@bot.callback_query_handler(func=lambda call: call.data.startswith('service_detail_'))
def callback_service_detail(call):
    # Извлекаем ID услуги из callback_data (например, "service_detail_1" -> 1)
    service_id = int(call.data.split('_')[2])

    conn = get_db_connection()
    service = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    conn.close()

    if service:
        # Формируем путь к картинке.
        # На сайте они лежат в static/img/services/, используем тот же путь для бота
        image_path = os.path.join('static', 'img', 'services', service['image_filename'])

        caption = (
            f"✨ <b>{service['name']}</b>\n\n"
            f"📝 {service['description']}\n\n"
            f"💰 <b>Стоимость:</b> {service['price']} ₽"
        )

        markup = types.InlineKeyboardMarkup()
        # Кнопка возврата к общему списку услуг
        btn_back = types.InlineKeyboardButton("⬅️ Назад к услугам", callback_data="show_all_services")
        btn_edit = types.InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_service_{service['id']}")
        markup.add(btn_back, btn_edit)

        # Проверяем, существует ли файл, прежде чем отправлять
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                bot.send_photo(
                    call.message.chat.id,
                    photo,
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=markup
                )
        else:
            # Если фото нет, отправляем просто текст
            bot.send_message(
                call.message.chat.id,
                caption + "\n\n<i>(Изображение не найдено)</i>",
                parse_mode='HTML',
                reply_markup=markup
            )

        # Удаляем старое сообщение со списком, чтобы не засорять чат (опционально)
        bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "show_all_services")
def callback_back_to_services(call):
    # 1. Удаляем сообщение с деталями услуги (фото + описание)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

    # 2. Вызываем функцию показа всех услуг
    # Мы передаем call.message, так как show_services ожидает объект сообщения
    show_services(call.message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_service_'))
def callback_edit_service_choice(call):
    service_id = int(call.data.split('_')[2])

    markup = types.InlineKeyboardMarkup()
    # В функции callback_edit_service_choice добавь:
    btn_photo = types.InlineKeyboardButton("Фотографию", callback_data=f"edit_field_{service_id}_image_filename")
    btn_name = types.InlineKeyboardButton("Название", callback_data=f"edit_field_{service_id}_name")
    btn_desc = types.InlineKeyboardButton("Описание", callback_data=f"edit_field_{service_id}_description")
    btn_price = types.InlineKeyboardButton("Цена", callback_data=f"edit_field_{service_id}_price")
    btn_back = types.InlineKeyboardButton("⬅️ Отмена", callback_data=f"service_detail_{service_id}")

    markup.add(btn_photo, btn_name, btn_desc)
    markup.add(btn_price)
    markup.add(btn_back)

    btn_delete = types.InlineKeyboardButton("🗑 Удалить услугу", callback_data=f"delete_service_{service_id}")
    markup.add(btn_delete)

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="<b>Что именно вы хотите изменить?</b>",
        parse_mode='HTML',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_service_'))
def callback_delete_service(call):
    service_id = int(call.data.split('_')[2])

    conn = get_db_connection()
    # Сначала узнаем имя для уведомления и имя файла картинки для удаления
    service = conn.execute('SELECT name, image_filename FROM services WHERE id = ?', (service_id,)).fetchone()

    if service:
        # Удаляем запись из базы
        conn.execute('DELETE FROM services WHERE id = ?', (service_id,))
        conn.commit()

        # Удаляем физический файл картинки, если он есть
        if service['image_filename']:
            path = os.path.join('static', 'img', 'services', service['image_filename'])
            if os.path.exists(path):
                os.remove(path)

        bot.answer_callback_query(call.id, f"Услуга '{service['name']}' удалена")

    conn.close()

    # Возвращаемся к списку
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_services(call.message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_field_'))
def callback_field_selected(call):
    data = call.data.split('_')
    service_id = int(data[2])
    field = call.data[13:]

    edit_service_state[call.message.chat.id] = {'service_id': service_id, 'field': field}

    if field == 'image_filename':
        bot.send_message(call.message.chat.id, "Отправьте новое фото для услуги:")
    else:
        field_names = {'name': 'новое название', 'description': 'новое описание', 'price': 'новую цену'}
        bot.send_message(call.message.chat.id, f"Введите {field_names[field]} для услуги:")


@bot.message_handler(content_types=['photo'])
def handle_service_photo(message):
    chat_id = message.chat.id
    state = edit_service_state.get(chat_id)

    if not state:
        bot.send_message(chat_id, "Чтобы изменить фото, сначала выберите услугу и нажмите 'Редактировать'.")
        return

    # --- СЦЕНАРИЙ 1: ДОБАВЛЕНИЕ НОВОЙ УСЛУГИ (шаг 'photo') ---
    if state.get('step') == 'photo':
        try:
            # Сначала создаем запись в БД, чтобы получить ID
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO services (name, description, price, image_filename) 
                VALUES (?, ?, ?, ?)
            ''', (state['name'], state['description'], state['price'], 'temp.jpg'))

            new_id = cursor.lastrowid  # Получаем ID новой услуги

            # Формируем имя servN.jpg
            filename = f"serv{new_id}.jpg"
            path = os.path.join('static', 'img', 'services', filename)

            # Скачиваем фото
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            with open(path, 'wb') as f:
                f.write(downloaded_file)

            # Обновляем имя файла в базе
            cursor.execute('UPDATE services SET image_filename = ? WHERE id = ?', (filename, new_id))
            conn.commit()
            conn.close()

            del edit_service_state[chat_id]
            bot.send_message(chat_id, f"✅ Услуга №{new_id} успешно создана!")
            show_services(message)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка при создании: {e}")

    # --- СЦЕНАРИЙ 2: РЕДАКТИРОВАНИЕ ФОТО СУЩЕСТВУЮЩЕЙ УСЛУГИ ---
    elif state.get('field') == 'image_filename':
        service_id = state['service_id']
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # Имя остается таким же (service_N.jpg), файл просто перезапишется
            filename = f"service_{service_id}.jpg"
            save_path = os.path.join('static', 'img', 'services', filename)

            with open(save_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            # На всякий случай обновляем путь в базе (если вдруг раньше там было другое имя)
            conn = get_db_connection()
            conn.execute('UPDATE services SET image_filename = ? WHERE id = ?', (filename, service_id))
            conn.commit()
            conn.close()

            del edit_service_state[chat_id]
            bot.send_message(chat_id, "✅ Фотография услуги обновлена!")
            show_services(message)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка при редактировании: {e}")


def show_houses(message):
    conn = get_db_connection()
    houses = conn.execute('SELECT id, name FROM houses').fetchall()
    conn.close()

    if not houses:
        bot.send_message(message.chat.id, "В базе пока нет домиков.")
        return

    text = "🏠 <b>Список всех домиков:</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)  # Кнопки будут по 2 в ряд

    house_buttons = []
    for house in houses:
        text += f"• {house['name']}\n"
        # Создаем кнопку. Пока оставляем callback_data пустой или формальной
        btn = types.InlineKeyboardButton(text=house['name'], callback_data=f"house_info_{house['id']}")
        house_buttons.append(btn)

    markup.add(*house_buttons)
    markup.add(types.InlineKeyboardButton("➕ Добавить новый домик", callback_data="add_house_start"))

    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('house_info_'))
def show_house_details(call):
    house_id = call.data.split('_')[2]

    conn = get_db_connection()
    house = conn.execute('SELECT * FROM houses WHERE id = ?', (house_id,)).fetchone()
    conn.close()

    if not house:
        bot.answer_callback_query(call.id, "Домик не найден")
        return

    # Формируем текст описания
    caption = (
        f"🏠 <b>{house['name']}</b>\n\n"
        f"🖋️ {house['short_description']}\n\n"
        f"📝 {house['description']}\n\n"
        f"🎯 {house['features']}\n\n"
        f"💰 <b>Цена:</b> {house['price_per_night']} руб/ночь"
    )

    # Создаем кнопку редактирования
    markup = types.InlineKeyboardMarkup()
    btn_edit = types.InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_house_{house_id}")
    btn_back = types.InlineKeyboardButton("⬅️ К списку домиков", callback_data="back_to_houses")
    # Метод .row() гарантирует, что кнопки будут стоять в одну линию
    markup.row(btn_edit, btn_back)

    house_folder = f"static/img/houses/house{house_id}"
    media = []

    try:
        if os.path.exists(house_folder):
            images = [f for f in os.listdir(house_folder) if f.endswith(('.jpg', '.jpeg', '.png'))]
            for i, img_name in enumerate(images[:10]):
                photo_path = os.path.join(house_folder, img_name)
                with open(photo_path, 'rb') as f:
                    if i == 0:
                        # Привязываем кнопки к первому сообщению с альбомом
                        media.append(types.InputMediaPhoto(f.read(), caption=caption, parse_mode='HTML'))
                    else:
                        media.append(types.InputMediaPhoto(f.read()))

        if media:
            bot.send_media_group(call.message.chat.id, media)
            # Так как к media_group нельзя прикрепить клавиатуру,
            # отправляем её отдельным сообщением сразу после альбома
            bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode='HTML', reply_markup=markup)

    except Exception as e:
        print(f"Ошибка: {e}")
        bot.send_message(call.message.chat.id, "Ошибка при загрузке данных домика.")

    bot.answer_callback_query(call.id)

# Не забудь добавить этот обработчик для кнопки "Назад", если его еще нет
@bot.callback_query_handler(func=lambda call: call.data == "back_to_houses")
def callback_back_to_houses(call):
    # Удаляем или редактируем старое сообщение, чтобы не плодить мусор, и показываем список
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_houses(call.message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_house_'))
def choose_edit_field(call):
    house_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup(row_width=1)
    # Добавь это в список кнопок в choose_edit_field
    markup.add(types.InlineKeyboardButton("🖼 Изменить все фото", callback_data=f"edit_images_{house_id}"))

    # ПРОВЕРЬ ЭТОТ СПИСОК: второе значение должно совпадать с именем колонки в БД
    fields = [
        ("Название", "name"),
        ("Короткое описание", "short_description"),
        ("Полное описание", "description"),
        ("Особенности (features)", "features"),
        ("Цена за ночь", "price_per_night")  # Было "price", стало "price_per_night"
    ]

    for text, db_column in fields:
        markup.add(types.InlineKeyboardButton(text, callback_data=f"editf_{db_column}_{house_id}"))
    # Добавь эту кнопку в список или сразу после цикла в функции choose_edit_field
    markup.add(types.InlineKeyboardButton("🗑 УДАЛИТЬ ДОМИК", callback_data=f"delete_confirm_{house_id}"))

    markup.add(types.InlineKeyboardButton("⬅️ Назад к домику", callback_data=f"house_info_{house_id}"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="<b>Что именно вы хотите изменить?</b>",
        parse_mode='HTML',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('editf_'))
def request_new_value(call):

    parts = call.data.split('_')
    house_id = parts[-1]
    column = "_".join(parts[1:-1])

    msg = bot.send_message(call.message.chat.id, f"Введите новое значение:")
    bot.register_next_step_handler(msg, save_value, column, house_id)
    bot.answer_callback_query(call.id)


def save_value(message, column, house_id):
    new_value = message.text

    val_to_save = new_value

    if column == "price_per_night":
        if new_value.isdigit():
            val_to_save = int(new_value)
        else:
            bot.send_message(message.chat.id, "❌ Цена должна быть числом!")
            return

    try:
        conn = get_db_connection()

        # Печатаем финальный запрос для проверки
        query = f"UPDATE houses SET {column} = ? WHERE id = ?"

        cursor = conn.execute(query, (val_to_save, house_id))
        conn.commit()

        # Проверяем, сколько строк реально изменилось
        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected == 0:
            bot.send_message(message.chat.id,
                             "⚠ База не выдала ошибку, но запись не обновилась (возможно, неверный ID).")
        else:
            bot.send_message(message.chat.id, f"✅ Сохранено! {column} теперь: {val_to_save}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


import os
import shutil


@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_images_'))
def request_new_images(call):
    house_id = call.data.split('_')[2]
    # Включаем режим ожидания фото для этого пользователя
    user_upload_state[call.message.chat.id] = house_id

    bot.send_message(call.message.chat.id,
                     "📷 <b>Режим загрузки фото включен.</b>\n\n"
                     "Пришлите альбом с фотографиями прямо сейчас.\n"
                     "Первое фото станет обложкой.",
                     parse_mode='HTML')
    bot.answer_callback_query(call.id)


# Этот обработчик теперь ловит ВСЕ фото, если пользователь в режиме загрузки
# Теперь слушаем и фото, и документы (файлы)
@bot.message_handler(content_types=['photo', 'document'])
def handle_media_upload(message):
    chat_id = message.chat.id
    if chat_id not in user_upload_state:
        return

    # Определяем, откуда брать file_id
    file_id = None
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
    elif message.content_type == 'document':
        # Проверяем, что это картинка (опционально)
        if message.document.mime_type and message.document.mime_type.startswith('image/'):
            file_id = message.document.file_id
        else:
            bot.send_message(chat_id, "❌ Этот файл не похож на изображение. Пропускаю его.")
            return

    house_id = user_upload_state[chat_id]
    m_group_id = message.media_group_id if message.media_group_id else f"single_{message.message_id}"

    if m_group_id not in album_data:
        album_data[m_group_id] = []
        # Таймер на 2 секунды, чтобы собрать все части альбома
        Timer(2.0, finalize_images_upload, args=[m_group_id, chat_id, house_id]).start()

    # Сохраняем данные для сортировки
    album_data[m_group_id].append({
        'message_id': message.message_id,
        'file_id': file_id
    })
    print(f"[LOG] Получен {message.content_type} (msg_id: {message.message_id})")


def finalize_images_upload(m_group_id, chat_id, house_id):
    try:
        photos = album_data.get(m_group_id)
        if not photos: return

        # КЛЮЧЕВОЙ МОМЕНТ: Сортируем список по message_id
        # Теперь первая выбранная тобой фотка гарантированно будет под индексом 0
        photos.sort(key=lambda x: x['message_id'])

        if chat_id in user_upload_state:
            del user_upload_state[chat_id]

        target_dir = f"static/img/houses/house{house_id}"
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(target_dir)

        print(f"[LOG] Сохраняю {len(photos)} фото в строгом порядке для дома {house_id}")

        for i, photo in enumerate(photos):
            file_info = bot.get_file(photo['file_id'])
            downloaded_file = bot.download_file(file_info.file_path)

            # Теперь index 0 — это точно первая отправленная картинка
            filename = "cover.jpg" if i == 0 else f"image{i}.jpg"

            with open(os.path.join(target_dir, filename), 'wb') as f:
                f.write(downloaded_file)
            print(f"[LOG] Сохранен {filename} (msg_id: {photo['message_id']})")

        bot.send_message(chat_id, f"✅ Фотографии сохранены в правильном порядке! (Всего: {len(photos)})")
        del album_data[m_group_id]

    except Exception as e:
        print(f"[LOG] Ошибка: {e}")
        bot.send_message(chat_id, "❌ Ошибка при сохранении.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_confirm_'))
def delete_confirm(call):
    house_id = call.data.split('_')[2]
    markup = types.InlineKeyboardMarkup()
    btn_yes = types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_yes_{house_id}")
    btn_no = types.InlineKeyboardButton("❌ Нет, оставить", callback_data=f"house_info_{house_id}")
    markup.row(btn_yes, btn_no)

    bot.edit_message_text("⚠️ <b>Вы уверены?</b>\nЭто удалит все данные о домике и его фотографии навсегда!",
                          chat_id=call.message.chat.id, message_id=call.message.message_id,
                          parse_mode='HTML', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_yes_'))
def delete_house_final(call):
    house_id = call.data.split('_')[2]
    try:
        # 1. Удаляем из БД
        conn = get_db_connection()
        conn.execute('DELETE FROM houses WHERE id = ?', (house_id,))
        conn.commit()
        conn.close()

        # 2. Удаляем папку с фото
        target_dir = f"static/img/houses/house{house_id}"
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        bot.answer_callback_query(call.id, "Домик успешно удален")
        bot.edit_message_text(f"✅ Домик №{house_id} полностью удален из системы.",
                              chat_id=call.message.chat.id, message_id=call.message.message_id)

        # Показываем обновленный список
        show_houses(call.message)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при удалении: {e}")


# Добавь кнопку в функцию show_houses (в самый низ клавиатуры)
@bot.callback_query_handler(func=lambda call: call.data == "add_house_start")
def add_house_start(call):
    msg = bot.send_message(call.message.chat.id, "Введите название нового домика:", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_add_name)


def process_add_name(message):
    house_data = {'name': message.text}
    msg = bot.send_message(message.chat.id, "Введите цену за ночь:", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_add_price, house_data)


def process_add_price(message, house_data):
    if not message.text.isdigit():
        msg = bot.send_message(message.chat.id, "❌ Ошибка! Введите цену цифрами:")
        bot.register_next_step_handler(msg, process_add_price, house_data)
        return

    house_data['price'] = int(message.text)
    msg = bot.send_message(message.chat.id, "Введите короткое описание:", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_add_short_desc, house_data)


def process_add_short_desc(message, house_data):
    house_data['short_description'] = message.text
    # Финальный шаг — сохранение в базу
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO houses (name, price_per_night, short_description, description, features)
            VALUES (?, ?, ?, ?, ?)
        ''', (house_data['name'], house_data['price'], house_data['short_description'], "Описание скоро будет...",
              "Особенности скоро будут..."))
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Создаем пустую папку для фото
        os.makedirs(f"static/img/houses/house{new_id}", exist_ok=True)

        bot.send_message(message.chat.id, f"✅ Домик «{house_data['name']}» создан (ID: {new_id})!\n\n"
                                          f"Теперь выберите его в списке, чтобы добавить полное описание и фотографии.")
        show_houses(message)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка БД: {e}")

# Эту функцию мы будем вызывать из app.py
def notify_admin(msg):
    global chat_id
    bot.send_message(chat_id, msg, parse_mode='HTML')


# Константа для количества элементов на странице /////////////////////////////////////////////////////////////////
ITEMS_PER_PAGE = 6


def get_bookings_markup(page=0):
    conn = get_db_connection()
    total_count = conn.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]

    offset = page * ITEMS_PER_PAGE
    bookings = conn.execute(f'''
        SELECT b.*, h.name as house_name 
        FROM bookings b 
        JOIN houses h ON b.house_id = h.id 
        ORDER BY b.check_in ASC 
        LIMIT {ITEMS_PER_PAGE} OFFSET {offset}
    ''').fetchall()
    conn.close()

    if not bookings:
        return "Бронирований пока нет.", None

    text = f"📋 <b>Список броней (Стр. {page + 1}):</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=3)  # Делаем кнопки по 3 в ряд

    # Список кнопок для выбора конкретной брони
    detail_buttons = []

    for b in bookings:
        text += f"🆔 <b>Бронь №{b['id']}</b> — {b['house_name']}\n"
        text += f"📅 {b['check_in']} - {b['check_out']}\n\n"

        # Создаем кнопку для каждой брони
        detail_buttons.append(types.InlineKeyboardButton(
            text=f"№{b['id']}",
            callback_data=f"detail_{b['id']}_{page}"  # Сохраняем ID и страницу, чтобы вернуться
        ))

    # Добавляем кнопки с номерами (по 3 в ряд)
    markup.add(*detail_buttons)

    # Кнопки навигации (Вперед/Назад)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page - 1}"))
    if offset + ITEMS_PER_PAGE < total_count:
        nav_buttons.append(types.InlineKeyboardButton("Вперед ➡️", callback_data=f"page_{page + 1}"))

    if nav_buttons:
        markup.row(*nav_buttons)

    return text, markup

# Изменяем декоратор, чтобы он ловил нажатие на конкретную бронь (например, "detail_5")
@bot.callback_query_handler(func=lambda call: call.data.startswith('detail_'))
def callback_detail_booking(call):
    # Достаем ID из строки "detail_12" -> 12
    booking_id = int(call.data.split('_')[1])

    # Теперь вызываем функцию, передавая ей этот ID
    show_detail_booking(call, booking_id)


def show_detail_booking(call, booking_id):
    conn = get_db_connection()
    # Запрос теперь должен вытягивать и поле services
    booking = conn.execute('''
        SELECT b.*, h.name as house_name 
        FROM bookings b 
        JOIN houses h ON b.house_id = h.id 
        WHERE b.id = ?
    ''', (booking_id,)).fetchone()

    if booking:
        # --- ЛОГИКА ПРЕОБРАЗОВАНИЯ УСЛУГ ---
        services_ids_str = booking['services']
        readable_services = ""

        if services_ids_str:
            services_data = conn.execute('SELECT id, name FROM services').fetchall()
            services_lookup = {service['id']: service['name'] for service in services_data}
            # Разбиваем "1,2" -> [1, 2]
            conn.close()
            try:
                selected_ids = [int(s_id) for s_id in services_ids_str.split(',') if s_id.strip()]
                # Ищем названия в словаре
                names_list = [services_lookup[s_id] for s_id in selected_ids if s_id in services_lookup]
                if names_list:
                    readable_services = " + " + " + ".join(names_list)
            except ValueError:
                # На случай, если в базе старые текстовые данные
                readable_services = f" + {services_ids_str}"

        # Формируем итоговую строку названия (Дом + Услуги)
        full_title = f"{booking['house_name']}{readable_services}"

        text = (
            f"<b>📍 Детали бронирования №{booking['id']}</b>\n\n"
            f"🏠 <b>Объект:</b> {full_title}\n"
            f"👤 <b>Гость:</b> {booking['client_name']}\n"
            f"📞 <b>Телефон:</b> +7 {booking['client_phone']}\n"
            f"📅 <b>Заезд:</b> {booking['check_in']}\n"
            f"🚪 <b>Выезд:</b> {booking['check_out']}\n"
        )

        markup = types.InlineKeyboardMarkup()
        btn_delete = types.InlineKeyboardButton("🗑 Удалить бронь", callback_data=f"delete_{booking['id']}")
        btn_back = types.InlineKeyboardButton("⬅️ Назад к списку", callback_data="page_0")
        markup.add(btn_delete)
        markup.add(btn_back)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='HTML',
            reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def confirm_delete(call):
    booking_id = call.data.split('_')[1]

    markup = types.InlineKeyboardMarkup()
    # Передаем ID брони в callback_data для финального удаления
    yes_btn = types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"conf_del_{booking_id}")
    # Кнопка отмены просто вернет нас к деталям этой же брони
    no_btn = types.InlineKeyboardButton("❌ Отмена", callback_data=f"detail_{booking_id}_0")

    markup.add(yes_btn, no_btn)

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"⚠️ <b>Вы уверены, что хотите удалить бронь №{booking_id}?</b>\nЭто действие нельзя будет отменить.",
        parse_mode='HTML',
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('conf_del_'))
def final_delete(call):
    booking_id = call.data.split('_')[2]

    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
        conn.commit()
        conn.close()

        # Показываем всплывающее уведомление в Telegram
        bot.answer_callback_query(call.id, "Бронирование удалено")

        # Возвращаемся к общему списку (на первую страницу)
        text, markup = get_bookings_markup(page=0)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ <b>Бронирование успешно удалено.</b>\n\n" + text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при удалении: {e}")

# Обработка основной кнопки "📋 Все бронирования"
@bot.message_handler(func=lambda message: message.text == "📋 Все бронирования")
def show_bookings(message):
    text, markup = get_bookings_markup(page=0)
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)


# Обработка нажатий на инлайн-кнопки (Callback)
@bot.callback_query_handler(func=lambda call: call.data.startswith('page_'))
def callback_page(call):
    # Достаем номер страницы из callback_data (например, из "page_1" достаем 1)
    page = int(call.data.split('_')[1])
    text, markup = get_bookings_markup(page=page)

    # Редактируем текущее сообщение вместо отправки нового
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except Exception as e:
        # Если текст не изменился (например, нажали "Назад" на 1 странице),
        # Telegram выдаст ошибку, ее можно просто проигнорировать
        pass

if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)
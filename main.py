import os
import sqlite3

def init_db():
    # Соединяемся с файлом базы данных (если его нет, он создастся)
    if os.path.exists('/data'):
        db_path = 'glamping.db'
    else:
        db_path = 'glamping.db'  # Оставляем так для локальной разработки

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Удаляем таблицы полностью, чтобы сбросить счетчики ID
    cursor.execute('DROP TABLE IF EXISTS bookings')
    cursor.execute('DROP TABLE IF EXISTS houses')
    cursor.execute('DROP TABLE IF EXISTS services')

    # 1. Создаем таблицу домиков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS houses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            short_description TEXT,
            price_per_night INTEGER,
            features TEXT,
            image_url TEXT
        )
    ''')

    # 2. Создаем таблицу бронирований (с учетом времени заезда/выезда)
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                house_id INTEGER NOT NULL,
                client_name TEXT NOT NULL,
                client_phone TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                services TEXT,
                total_price INTEGER
            )
        ''')

    # Создаем таблицу для услуг
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER,
                image_filename TEXT
            )
        ''')

    # 3. Наполняем базу нашими тремя домиками
    houses_data = [
        (
            'А-фрейм',
            'Уютный треугольный домик с панорамными окнами. Идеально для пары или небольшой семьи.',
            'Панорамные окна и вид на озеро',
            7000,
            'Wi-Fi, Мангал',
            '/static/img/houses/house1/cover.jpg'
        ),
        (
            'Барнхаус',
            'Одноэтажный дом с футуристичным дизайном. Наслаждайтесь видом в любой точке дома.',
            'Наблюдайте за пейзажом из кровати',
            7000,
            'Отличный вид, Кондиционер',
            '/static/img/houses/house2/cover.jpg'
        ),
        (
            'Большой дом',
            'Прсторный дом для большой семьи или компании. Идеально для большого количества человек',
            'Отличное местечко в самой чаще леса',
            7000,
            'Тишина, Костровая зона',
            '/static/img/houses/house3/cover.jpg'
        )
    ]

    # (Опционально) Добавим несколько тестовых услуг, чтобы страница не была пустой
    sample_services = [
        ('Баня', 'Расслабляющая баня в лесной черте.', 3500, 'serv1.jpg'),
        ('Чан', 'Ароматный горячий чан.', 3500, 'serv2.jpg'),
        ('Бассейн', 'Освежитесь на открытом воздухе (только летом).', 0, 'serv3.jpg')
    ]

    # Очистим таблицу перед заполнением (чтобы не дублировать при повторном запуске)
    cursor.execute('DELETE FROM houses')
    cursor.execute('DELETE FROM bookings')
    cursor.execute('DELETE FROM services')

    cursor.executemany('''
            INSERT INTO houses (name, description, short_description, price_per_night, features, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', houses_data)

    # Проверяем, пустая ли таблица, прежде чем добавлять тестовые данные
    cursor.execute('SELECT COUNT(*) FROM services')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('''
                INSERT INTO services (name, description, price, image_filename)
                VALUES (?, ?, ?, ?)
            ''', sample_services)

    conn.commit()
    conn.close()
    print("База данных успешно создана и заполнена!")

def get_house(house_id):
    conn = sqlite3.connect('glamping.db')
    # Позволяет обращаться к полям по именам, а не по индексам
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM houses WHERE id = ?", (house_id,))
    house = cursor.fetchone()
    conn.close()
    return house

if __name__ == '__main__':
    init_db()
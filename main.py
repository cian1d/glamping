import sqlite3

def init_db():
    # Соединяемся с файлом базы данных (если его нет, он создастся)
    conn = sqlite3.connect('glamping.db')
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
            'А-фрейм «Сканди»',
            'Уютный треугольный домик с панорамными окнами. Идеально для пары или небольшой семьи.',
            'Панорамные окна и вид на озеро',
            7500,
            'Wi-Fi, Мангал, Проектор, Купель',
            '/static/img/houses/house1/cover.jpg'
        ),
        (
            'Купольная Сфера',
            'Прозрачный купол для наблюдения за звездами. Футуристичный дизайн и полный комфорт.',
            'Наблюдайте за звездами из кровати',
            9500,
            'Звездное небо, Кондиционер, Джакузи',
            '/static/img/houses/house2/cover.jpg'
        ),
        (
            'Тайни-хаус «Мох»',
            'Миниатюрный домик в скандинавском стиле, спрятанный в самой чаще леса.',
            'Уютное гнездышко в самой чаще леса',
            5500,
            'Тишина, Гамак, Костровая зона',
            '/static/img/houses/house3/cover.jpg'
        )
    ]

    # (Опционально) Добавим несколько тестовых услуг, чтобы страница не была пустой
    sample_services = [
        ('Горячая купель', 'Расслабляющая кедровая бочка под открытым небом.', 3500, 'serv1.jpg'),
        ('Аренда велосипедов', 'Прогулка по лесным тропам на горных байках.', 800, 'serv2.jpg'),
        ('Завтрак в домик', 'Свежая выпечка, фермерский творог и ароматный кофе.', 1200, 'serv3.jpg')
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
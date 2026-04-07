import os
import sqlite3

def get_db_path():
    if os.path.exists('/data'):
        return '/data/glamping.db'
    return 'data/glamping.db'

def get_img_base():
    """Базовая папка для хранения загружаемых фото"""
    if os.path.exists('/data'):
        return '/data/img'
    return 'static/img'


def sync_images():
    """
    Синхронизация фото между static/img и /data/img.
    - Если /data/img пустой — копируем исходники из static/img в /data/img
    - Затем всегда копируем из /data/img в static/img (чтобы загруженные через бота фото были доступны сайту)
    """
    if not os.path.exists('/data'):
        return

    import shutil

    data_img = '/data/img'
    static_img = 'static/img'

    # Первый запуск: /data/img пустой — копируем туда исходники из репозитория
    if not os.path.exists(data_img) or not os.listdir(data_img):
        print("[IMG] /data/img пустой, копируем исходники из static/img...")
        shutil.copytree(static_img, data_img, dirs_exist_ok=True)

    # Всегда синхронизируем из /data/img → static/img
    for root, dirs, files in os.walk(data_img):
        rel = os.path.relpath(root, data_img)
        target_dir = os.path.join(static_img, rel)
        os.makedirs(target_dir, exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target_dir, f))
    print("[IMG] Фото синхронизированы из /data/img в static/img")
    if os.path.exists('/data'):
        return '/data/glamping.db'
    return 'data/glamping.db'

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Создаём таблицы только если их нет — данные не трогаем
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER,
            image_filename TEXT
        )
    ''')

    # Заполняем домики только если таблица пустая
    cursor.execute('SELECT COUNT(*) FROM houses')
    if cursor.fetchone()[0] == 0:
        houses_data = [
            ('А-фрейм', 'Уютный треугольный домик с панорамными окнами. Идеально для пары или небольшой семьи.', 'Панорамные окна и вид на озеро', 7000, 'Wi-Fi, Мангал', '/static/img/houses/house1/cover.jpg'),
            ('Барнхаус', 'Одноэтажный дом с футуристичным дизайном. Наслаждайтесь видом в любой точке дома.', 'Наблюдайте за пейзажом из кровати', 7000, 'Отличный вид, Кондиционер', '/static/img/houses/house2/cover.jpg'),
            ('Большой дом', 'Просторный дом для большой семьи или компании. Идеально для большого количества человек', 'Отличное местечко в самой чаще леса', 7000, 'Тишина, Костровая зона', '/static/img/houses/house3/cover.jpg'),
        ]
        cursor.executemany('''
            INSERT INTO houses (name, description, short_description, price_per_night, features, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', houses_data)

    # Заполняем услуги только если таблица пустая
    cursor.execute('SELECT COUNT(*) FROM services')
    if cursor.fetchone()[0] == 0:
        sample_services = [
            ('Баня', 'Расслабляющая баня в лесной черте.', 3500, 'serv1.jpg'),
            ('Чан', 'Ароматный горячий чан.', 3500, 'serv2.jpg'),
            ('Бассейн', 'Освежитесь на открытом воздухе (только летом).', 0, 'serv3.jpg'),
        ]
        cursor.executemany('''
            INSERT INTO services (name, description, price, image_filename)
            VALUES (?, ?, ?, ?)
        ''', sample_services)

    conn.commit()
    conn.close()
    print(f"[DB] База данных готова: {db_path}")

def get_house(house_id):
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM houses WHERE id = ?", (house_id,))
    house = cursor.fetchone()
    conn.close()
    return house

if __name__ == '__main__':
    init_db()

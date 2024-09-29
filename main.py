import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Process
import mimetypes
import json
import urllib.parse
import pathlib
import socket
import logging
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Конфігурація MongoDB
uri = "mongodb://mongodb_service:27017"
# Порти для HTTP та сокет-сервера
HTTPServer_Port = 3000
UDP_IP = '127.0.0.1'
UDP_PORT = 5000

class HttpGetHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Обробка POST-запиту для форми на сторінці message.html.
        
        Зчитує дані з запиту, обробляє їх і надсилає на сокет-сервер. 
        Перенаправляє користувача назад на головну сторінку після успішної обробки.
        """
        data = self.rfile.read(int(self.headers['Content-Length']))
        data_parse = urllib.parse.unquote_plus(data.decode())
        data_dict = {key: value for key, value in [el.split('=') for el in data_parse.split('&')]}

        # Надсилаємо дані сокет-серверу
        send_data_to_socket(data_dict)

        # Відправляємо користувача назад на головну сторінку після успішної обробки
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

    def do_GET(self):
        """Обробка GET-запитів та статичних файлів.
        
        Визначає, який файл або ресурс слід повернути у відповідь на GET-запит.
        Повертає HTML-файли або статичні файли в залежності від запиту.
        """
        pr_url = urllib.parse.urlparse(self.path)
        if pr_url.path == '/':
            self.send_html_file('index.html')
        elif pr_url.path == '/message':
            self.send_html_file('message.html')
        else:
            if pathlib.Path().joinpath(f'front-init{pr_url.path}').exists():
                self.send_static()
            else:
                self.send_html_file('error.html', 404)

    def send_html_file(self, filename, status=200):
        """Надсилання HTML-файлів.
        
        Відправляє зазначений HTML-файл у відповіді на HTTP-запит.
        
        Аргументи:
        filename -- ім'я HTML-файлу, який потрібно надіслати
        status -- HTTP статус, за замовчуванням 200
        """
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # Вказуємо правильний шлях до HTML-файлів у папці front-init
        file_path = f'front-init/{filename}'
        with open(file_path, 'rb') as fd:
            self.wfile.write(fd.read())

    def send_static(self):
        """Відправка статичних файлів.
        
        Визначає тип файлу та відправляє його в залежності від запиту.
        Якщо файл не знайдено, повертає 404 Not Found.
        """
        mt = mimetypes.guess_type(self.path)
        if mt:
            self.send_response(200)
            self.send_header("Content-type", mt[0])
        else:
            self.send_response(200)
            self.send_header("Content-type", 'text/plain')

        self.end_headers()  # Завершити заголовки перед відправкою тіла

        # Вказуємо правильний шлях до статичних файлів у папці front-init
        file_path = f'front-init{self.path}'  # [1:] видаляє перший символ '/'
        
        try:
            # Перевіряємо наявність файлу перед відкриттям
            if pathlib.Path(file_path).exists():
                with open(file_path, 'rb') as file:
                    self.wfile.write(file.read())
            else:
                raise FileNotFoundError  # Викликаємо помилку, якщо файл не знайдено
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'404 Not Found')
            logging.error("Файл не знайдено: %s", self.path)

def run_http_server(server_class=HTTPServer, handler_class=HttpGetHandler):
    """Запуск HTTP-сервера.
    
    Ініціалізує HTTP-сервер на вказаному адресі та порту.
    Обробляє запити, доки сервер не буде зупинено.
    
    Аргументи:
    server_class -- клас сервера, за замовчуванням HTTPServer
    handler_class -- клас обробника запитів, за замовчуванням HttpGetHandler
    """
    server_address = ('0.0.0.0', HTTPServer_Port)
    http = server_class(server_address, handler_class)
    try:
        logging.info("HTTP сервер запущено на порті %d", HTTPServer_Port)
        http.serve_forever()
    except KeyboardInterrupt:
        logging.info("Зупинка HTTP-сервера")
        http.server_close()

def send_data_to_socket(data_dict):
    """Відправка даних на сокет-сервер.
    
    Перетворює словник даних у формат JSON та надсилає його на вказану IP-адресу та порт UDP.
    
    Аргументи:
    data_dict -- словник даних, які потрібно надіслати
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (UDP_IP, UDP_PORT)
    message = json.dumps(data_dict).encode('utf-8')  # Словник перетворюємо у JSON перед відправкою
    sock.sendto(message, server_address)
    logging.info("Відправлено дані на сокет-сервер: %s", data_dict)
    sock.close()

def save_data(data_dict):
    """Збереження даних у MongoDB з відповідною структурою.
    
    Зберігає отримані дані у вказану колекцію MongoDB з метою подальшого використання.
    
    Аргументи:
    data_dict -- словник даних, які потрібно зберегти
    """
    client = MongoClient(uri, server_api=ServerApi("1"))
    db = client['data_db']  # Назва бази даних
    collection = db['chat']  # Назва колекції

    # Структура документа для MongoDB
    document = {
        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),  # Поточна дата і час
        "username": data_dict.get("username"),  # Ім'я користувача
        "message": data_dict.get("message")     # Повідомлення
    }

    # Збереження документа в колекцію MongoDB
    collection.insert_one(document)
    logging.info("Дані збережено в MongoDB: %s", document)

def run_socket_server():
    """Запуск UDP сокет-сервера для прийому даних та збереження їх у MongoDB.
    
    Слухає на вказаній IP-адресі та порту, приймає дані, обробляє їх і зберігає у MongoDB.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (UDP_IP, UDP_PORT)
    sock.bind(server_address)

    logging.info("Сокет-сервер запущено на %s:%d", UDP_IP, UDP_PORT)
    try:
        while True:
            data, address = sock.recvfrom(1024)
            data_dict = json.loads(data.decode('utf-8'))  # Декодуємо отримані дані
            logging.info("Отримано дані: %s від: %s", data_dict, address)

            # Збереження даних у MongoDB
            save_data(data_dict)

            # Відправляємо підтвердження назад на клієнт
            sock.sendto(data, address)
    except KeyboardInterrupt:
        logging.info("Зупинка сокет-сервера")
    finally:
        sock.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(threadName)s %(message)s')

    # Виводимо версію Python
    logging.error("Python version: %s", sys.version)

    # Запуск HTTP та сокет-сервера у різних процесах
    http_server_process = Process(target=run_http_server)
    http_server_process.start()

    socket_server_process = Process(target=run_socket_server)
    socket_server_process.start()

    http_server_process.join()
    socket_server_process.join()

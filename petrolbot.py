import os
import logging
from logging.handlers import RotatingFileHandler
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Bot, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import sqlite3
from datetime import datetime

load_dotenv()

# Получение абсолютного пути к рабочей директории
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

secret_token = os.getenv('TOKEN')

# Настройка ротации логов
handler = RotatingFileHandler(os.path.join(BASE_DIR, 'bot.log'), maxBytes=50000000, backupCount=2)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Настройка общего логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[handler]
)

class HTTPRequestsFilter(logging.Filter):
    def filter(self, record):
        return 'HTTP Request' not in record.getMessage()

# Настройка логирования для библиотеки httpx
http_logger = logging.getLogger("httpx")
http_logger.setLevel(logging.ERROR)
http_logger.addFilter(HTTPRequestsFilter())

class PriceBot:
    def __init__(self, token, db_path=None):
        self.bot = Bot(token=token)
        self.application = Application.builder().token(token).build()
        self.current_price = None
        self.db_path = (os.path.join(BASE_DIR, 'subscribers.db')
                        if db_path is None else db_path)
        self.init_db()
        self.init_handlers()
        logging.info('Бот инициализирован')

    def init_db(self):
        """Инициализация базы данных и таблицы подписчиков"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                first_name TEXT,
                subscribed_date TEXT
            )
        ''')
        self.conn.commit()
        logging.info('База данных инициализирована')

    def add_subscriber(self, chat_id, first_name, subscribed_date):
        """Добавление новой записи в базу данных подписчиков"""
        date = datetime.fromisoformat(subscribed_date).strftime("%d %B %Y")
    
        #Проверка, существует ли подписчик в базе данных
        self.cursor.execute('SELECT * FROM subscribers WHERE chat_id = ?', (chat_id,))
        if not self.cursor.fetchone():
            self.cursor.execute('''
                INSERT INTO subscribers (chat_id, first_name, subscribed_date)
                VALUES (?, ?, ?)
            ''', (chat_id, first_name, date))
            self.conn.commit()
            logging.info(f'Подписчик добавлен: {first_name} ({chat_id}) на дату {date}')

    def process_update(self, update):
        """Обработка данных из обновления"""
        chat = update.effective_chat
        name = update.message.chat.first_name if update.message.chat.first_name else "Unknown"
        chat_id = chat.id
        subscribed_date = update.message.date.isoformat() if update.message.date else "Unknown"
        self.add_subscriber(chat_id, name, subscribed_date)
        logging.info(f'Обновление обработано: {name} ({chat_id})')
        return chat_id, name

    def get_price(self):
        """Получение текущей цены на топливо с сайта"""
        try:
            header = {'User-Agent': 'PetrolBot/1.0'}
            url = 'https://www.petrolplus.ru/fuelindex/gorod-sankt-peterburg/'
            response = requests.get(url, headers=header, timeout=(5, 15))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for table in soup.find_all('table'):
                headers = [cell.get_text(strip=True)
                           for cell in table.find_all('th')]
                if 'Регион' not in headers or 'АИ-95' not in headers:
                    continue
                region_column = headers.index('Регион')
                price_column = headers.index('АИ-95')
                for row in table.find_all('tr'):
                    cells = row.find_all('td', recursive=False)
                    if len(cells) <= max(region_column, price_column):
                        continue
                    region = ' '.join(cells[region_column].stripped_strings)
                    if region != 'г. Санкт-Петербург':
                        continue
                    value = cells[price_column].get_text(strip=True)
                    price = float(value.replace(',', '.'))
                    if not 0 < price < float('inf'):
                        raise ValueError('Некорректная цена АИ-95')
                    logging.info(f'Цена получена: {price} р.')
                    return price
            raise ValueError('Цена АИ-95 для Санкт-Петербурга не найдена')
        except Exception as e:
            logging.error(f"Ошибка при получении цены: {e}")
            return None

    async def check_price_change(self, context):
        """Проверка изменения цены и отправка уведомлений подписчикам"""
        new_price = self.get_price()
        if new_price is not None and self.current_price is not None:
            diff_price = abs(new_price - self.current_price)
            diff_price = round(diff_price, 2)
            if diff_price >= 0.01:
                self.current_price = new_price
                self.cursor.execute('SELECT chat_id FROM subscribers')
                subscribers = self.cursor.fetchall()
                for (chat_id,) in subscribers:
                    await context.bot.send_message(
                        chat_id=chat_id, text=f'Средняя цена на бензин АИ-95 изменилась на {diff_price} и составляет {new_price} р.')
        elif self.current_price is None:
            self.current_price = new_price

    async def send_price(self, update, context):
        """Отправка текущей цены пользователю"""
        chat_id = update.effective_chat.id
        price = self.get_price()
        if price is not None:
            await context.bot.send_message(
                chat_id=chat_id, text=f'Актуальная средняя цена на бензин АИ-95 в Санкт-Петербурге составляет: {price} р.')
        else:
            await context.bot.send_message(
                chat_id=chat_id, text='Не удалось получить цену.')

    async def start(self, update, context):
        """Обработка команды /start, добавление подписчика и отправка приветственного сообщения"""
        chat_id, name = self.process_update(update)
        
        button = ReplyKeyboardMarkup([['Узнать актуальную цену']], resize_keyboard=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f'Спасибо, что вы включили меня, {name}!',
            reply_markup=button
        )

    async def handle_message(self, update, context):
        """Обработка текстовых сообщений и отправка соответствующего ответа"""
        text = update.message.text
        if text == 'Узнать актуальную цену':
            self.process_update(update)
            await self.send_price(update, context)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text='Нажмите кнопку "Узнать актуальную цену" для получения актуальной цены.')

    def init_handlers(self):
        """Инициализация обработчиков команд и сообщений"""
        job_queue = self.application.job_queue

        # Запуск задания на проверку изменения цены каждые 60 минут
        job_queue.run_repeating(self.check_price_change,
                                interval=3600, first=0)

        # Обработчик команды /start
        self.application.add_handler(CommandHandler('start', self.start))
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_message))

    def run(self):
        """Запуск бота"""
        self.application.run_polling()
        self.conn.close()

if __name__ == '__main__':
    bot = PriceBot(secret_token)
    bot.run()

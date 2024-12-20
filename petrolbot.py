import os
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Bot, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import sqlite3

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение токена бота из переменных окружения
secret_token = os.getenv('TOKEN')

class PriceBot:
    def __init__(self, token):
        self.bot = Bot(token=token)  # Инициализация бота
        self.application = Application.builder().token(
            token).build()  # Инициализация Application
        self.current_price = None  # Текущая цена
        self.init_db()  # Инициализация базы данных
        self.init_handlers()  # Инициализация обработчиков

    def init_db(self):
        """Инициализация базы данных и таблицы подписчиков"""
        self.conn = sqlite3.connect('subscribers.db')
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                first_name TEXT,
                subscribed_date TEXT
            )
        ''')
        self.conn.commit()

    def add_subscriber(self, chat_id, first_name, subscribed_date):
        """Добавление новой записи в базу данных подписчиков"""
        self.cursor.execute('''
            INSERT OR IGNORE INTO subscribers (chat_id, first_name, subscribed_date)
            VALUES (?, ?, ?)
        ''', (chat_id, first_name, subscribed_date))
        self.conn.commit()

    def process_update(self, update):
        """Обработка данных из обновления"""
        chat = update.effective_chat
        name = update.message.chat.first_name if update.message.chat.first_name else "Unknown"
        chat_id = chat.id
        subscribed_date = update.message.date.isoformat() if update.message.date else "Unknown"
        self.add_subscriber(chat_id, name, subscribed_date)
        return chat_id, name

    def get_price(self):
        """Получение текущей цены на топливо с сайта"""
        try:
            header = {'User-Agent': 'BMW'}
            url = 'https://fuelprices.ru/szfo/speterburg'
            response = requests.get(url, headers=header)
            response.raise_for_status()  # Проверка на ошибки HTTP
            soup = BeautifulSoup(response.text, 'lxml')
            ai_95_block = soup.find('div', class_='fuel-card border-ai92')
            price = float(ai_95_block.find(
                'span', itemprop='price').text.replace(',', '.'))
            return price
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

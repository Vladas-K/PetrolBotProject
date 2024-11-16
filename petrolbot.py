import os
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Bot, ReplyKeyboardMarkup
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение токена бота из переменных окружения
secret_token = os.getenv('TOKEN')


class PriceBot:
    def __init__(self, token):
        self.bot = Bot(token=token)  # Инициализация бота
        # Инициализация Updater
        self.updater = Updater(token=token, use_context=True)
        self.current_price = None  # Текущая цена
        self.subscribers = set()  # Множество для хранения chat_id подписчиков
        self.init_handlers()  # Инициализация обработчиков

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

    def check_price_change(self, context):
        """Проверка изменения цены и отправка уведомлений подписчикам"""
        new_price = self.get_price()
        diff_price = abs(new_price - self.current_price)
        # if new_price is not None and self.current_price is not None and abs(new_price - self.current_price) >= 1:
        if new_price is not None and self.current_price is not None and diff_price >= 0.01:
            self.current_price = new_price
            for chat_id in self.subscribers:
                context.bot.send_message(
                    chat_id=chat_id, text=f'Средняя цена на бензин АИ-95 изменилась на {diff_price} и составляет {new_price}')
        elif self.current_price is None:
            self.current_price = new_price

    def send_price(self, update, context):
        """Отправка текущей цены пользователю"""
        chat_id = update.effective_chat.id  # Сохраняем chat_id
        price = self.get_price()
        if price is not None:
            context.bot.send_message(
                chat_id=chat_id, text=f'Актуальная средняя цена на бензин АИ-95 в Санкт-Петербурге составляет: {price}')
        else:
            context.bot.send_message(
                chat_id=chat_id, text='Не удалось получить цену.')

    def start(self, update, context):
        """Обработка команды /start, добавление подписчика и отправка приветственного сообщения"""
        chat = update.effective_chat
        name = update.message.chat.first_name
        self.subscribers.add(chat.id)  # Добавляем chat_id в список подписчиков
        button = ReplyKeyboardMarkup(
            [['Узнать актуальную цену']], resize_keyboard=True)
        context.bot.send_message(
            chat_id=chat.id,
            text=f'Спасибо, что вы включили меня, {name}!',
            reply_markup=button
        )

    def handle_message(self, update, context):
        """Обработка текстовых сообщений и отправка соответствующего ответа"""
        text = update.message.text
        if text == 'Узнать актуальную цену':
            self.send_price(update, context)
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text='Нажмите кнопку "Узнать актуальную цену" для получения актуальной цены.')

    def init_handlers(self):
        """Инициализация обработчиков команд и сообщений"""
        dispatcher = self.updater.dispatcher
        job_queue = self.updater.job_queue

        # Запуск задания на проверку изменения цены каждые 60 минут
        job_queue.run_repeating(self.check_price_change,
                                interval=3600, first=0)

        # Обработчик команды /start
        dispatcher.add_handler(CommandHandler('start', self.start))
        # Обработчик текстовых сообщений
        dispatcher.add_handler(MessageHandler(
            Filters.text & ~Filters.command, self.handle_message))

    def run(self):
        """Запуск бота"""
        self.updater.start_polling()
        self.updater.idle()


if __name__ == '__main__':
    bot = PriceBot(secret_token)
    bot.run()

"""Локальный запуск: venv/bin/python run_test_bot.py"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import dotenv_values
from telegram import Bot


async def get_username(token):
    async with Bot(token) as bot:
        return (await bot.get_me()).username


def main():
    root = Path(__file__).resolve().parent
    token = dotenv_values(root / '.env.test').get('TOKEN')
    production_token = dotenv_values(root / '.env').get('TOKEN')
    if not token or token == production_token:
        raise SystemExit('Укажите отдельный тестовый TOKEN в .env.test.')

    # Переменная окружения имеет приоритет над рабочим .env в petrolbot.py.
    os.environ['TOKEN'] = token
    logging.basicConfig(level=logging.WARNING)
    try:
        username = asyncio.run(get_username(token))
    except Exception as error:
        # Не выводим URL запроса: он может содержать токен.
        raise SystemExit(
            f'Не удалось подключиться к тестовому боту ({type(error).__name__}).'
        ) from None

    from petrolbot import PriceBot

    # asyncio.run() закрыл цикл проверки; run_polling() нужен новый цикл.
    asyncio.set_event_loop(asyncio.new_event_loop())
    print(f'Тестовый бот: https://t.me/{username}', flush=True)
    print('Отправьте /start и нажмите «Узнать актуальную цену».', flush=True)
    print('База: subscribers.test.db. Остановка: Ctrl+C.', flush=True)
    bot = PriceBot(token, db_path=str(root / 'subscribers.test.db'))
    bot.run()


if __name__ == '__main__':
    main()

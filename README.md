# PetrolBotProject
Бот-парсер средней цены на 95 бензин в Санкт-Петербурге

## Локальная проверка

Создайте отдельного тестового бота через @BotFather и сохраните его токен
в `.env.test` в формате `TOKEN=...`. Рабочий `.env` менять не нужно.

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m unittest discover -s tests -v
venv/bin/python run_test_bot.py
```

Откройте ссылку, которую выведет программа, отправьте `/start` и нажмите
«Узнать актуальную цену». Остановить бота можно сочетанием Ctrl+C.
Тестовый запуск использует отдельную базу `subscribers.test.db` и проверяет,
что тестовый токен отличается от рабочего. Токен и тестовая база исключены из Git.

Рабочий запуск на сервере остаётся прежним: `python petrolbot.py`.

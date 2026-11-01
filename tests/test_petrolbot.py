import os
import unittest
from unittest.mock import Mock, patch

import requests

from petrolbot import BASE_DIR, PriceBot


class GetPriceTests(unittest.TestCase):
    def setUp(self):
        # Не создаём Application и не открываем базу подписчиков.
        self.bot = PriceBot.__new__(PriceBot)

    def fetch(self, html, city='Санкт-Петербурге'):
        html = f'<h1>Цены на бензин в {city} сегодня</h1>' + html
        response = Mock(text=html)
        with patch('petrolbot.requests.get', return_value=response) as get:
            result = self.bot.get_price()
        get.assert_called_once_with(
            'https://benzinstatus.ru/sankt-peterburg/ceny/',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=(5, 15))
        response.raise_for_status.assert_called_once_with()
        return result

    def test_selects_ai95_average_instead_of_median_or_other_fuel(self):
        html = '''<table>
            <thead><tr><th>Топливо</th><th>Медиана</th><th>Средняя</th></tr></thead>
            <tbody>
            <tr><td><b>АИ-92</b></td><td>67,20 ₽</td><td>67,14 ₽</td></tr>
            <tr><td><b>АИ-95+</b></td><td>75,00 ₽</td><td>75,10 ₽</td></tr>
            <tr><td><b>АИ-95</b></td><td><b>72,30 ₽</b></td><td>72,60 ₽</td></tr>
            </tbody>
        </table>'''
        self.assertEqual(self.fetch(html), 72.6)

    def test_reordered_columns_and_nonbreaking_spaces(self):
        html = '''<table>
            <tr><th>Средняя</th><th>Топливо</th><th>Медиана</th></tr>
            <tr><td><span>72.60</span>&nbsp;₽</td><td>АИ-95</td><td>72,30 ₽</td></tr>
        </table>'''
        self.assertEqual(self.fetch(html), 72.6)

    def test_other_city_is_rejected(self):
        html = '''<table><tr><th>Топливо</th><th>Средняя</th></tr>
            <tr><td>АИ-95</td><td>75,00 ₽</td></tr></table>'''
        with self.assertLogs(level='ERROR'):
            self.assertIsNone(self.fetch(html, city='Москве'))

    def test_missing_or_changed_markup_returns_none(self):
        for html in ('<html>Service unavailable</html>', '''<table>
                <tr><th>Топливо</th><th>Медиана</th></tr>
                <tr><td>АИ-95</td><td>72,30 ₽</td></tr>
                </table>''', '''<table>
                <tr><th>Топливо</th><th>Средняя</th></tr>
                <tr><td>АИ-95+</td><td>75,00 ₽</td></tr>
                <tr><td>АИ-95</td></tr>
                </table>'''):
            with self.subTest(html=html), self.assertLogs(level='ERROR'):
                self.assertIsNone(self.fetch(html))

    def test_invalid_price_returns_none(self):
        for value in ('0', '-1', 'nan', 'inf', '—'):
            html = f'''<table><tr><th>Топливо</th><th>Средняя</th></tr>
                <tr><td>АИ-95</td><td>{value} ₽</td></tr></table>'''
            with self.subTest(value=value), self.assertLogs(level='ERROR'):
                self.assertIsNone(self.fetch(html))

    def test_network_timeout_returns_none(self):
        with patch('petrolbot.requests.get', side_effect=requests.Timeout), \
                self.assertLogs(level='ERROR'):
            self.assertIsNone(self.bot.get_price())

    def test_http_error_returns_none(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError('503')
        with patch('petrolbot.requests.get', return_value=response), \
                self.assertLogs(level='ERROR'):
            self.assertIsNone(self.bot.get_price())


class DatabasePathTests(unittest.TestCase):
    def create_bot(self, **kwargs):
        with patch('petrolbot.Bot'), patch('petrolbot.Application'), \
                patch.object(PriceBot, 'init_handlers'), \
                patch('petrolbot.sqlite3.connect') as connect:
            bot = PriceBot('test-token', **kwargs)
        connect.assert_called_once_with(bot.db_path)
        return bot

    def test_production_database_stays_in_project_directory(self):
        bot = self.create_bot()
        self.assertEqual(bot.db_path, os.path.join(BASE_DIR, 'subscribers.db'))

    def test_test_database_can_be_selected_separately(self):
        bot = self.create_bot(db_path='subscribers.test.db')
        self.assertEqual(bot.db_path, 'subscribers.test.db')


if __name__ == '__main__':
    unittest.main()

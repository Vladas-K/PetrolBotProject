import os
import unittest
from unittest.mock import Mock, patch

import requests

from petrolbot import BASE_DIR, PriceBot


class GetPriceTests(unittest.TestCase):
    def setUp(self):
        # Не создаём Application и не открываем базу подписчиков.
        self.bot = PriceBot.__new__(PriceBot)

    def fetch(self, html):
        response = Mock(text=html)
        with patch('petrolbot.requests.get', return_value=response) as get:
            result = self.bot.get_price()
        get.assert_called_once_with(
            'https://www.petrolplus.ru/fuelindex/gorod-sankt-peterburg/',
            headers={'User-Agent': 'PetrolBot/1.0'}, timeout=(5, 15))
        response.raise_for_status.assert_called_once_with()
        return result

    def test_selects_city_and_fuel_by_header(self):
        html = '''<table>
            <tr><th>Регион</th><th>АИ-92</th><th>АИ-95</th><th>ДТ</th></tr>
            <tr><td>Ленинградская область</td><td>66</td><td>71</td><td>81</td></tr>
            <tr><td><span>г. Санкт-Петербург</span></td>
                <td>65.47</td><td><div>70.6</div></td><td>80.57</td></tr>
        </table>'''
        self.assertEqual(self.fetch(html), 70.6)

    def test_reordered_columns_and_decimal_comma(self):
        html = '''<table>
            <tr><th>АИ-95</th><th>Регион</th><th>АИ-92</th></tr>
            <tr><td>70,60</td><td>г. Санкт-Петербург</td><td>65.47</td></tr>
        </table>'''
        self.assertEqual(self.fetch(html), 70.6)

    def test_missing_or_changed_markup_returns_none(self):
        for html in ('<html>Service unavailable</html>', '''<table>
                <tr><th>Регион</th><th>АИ-95</th></tr>
                <tr><td>Ленинградская область</td><td>71</td></tr>
                </table>'''):
            with self.subTest(html=html), self.assertLogs(level='ERROR'):
                self.assertIsNone(self.fetch(html))

    def test_invalid_price_returns_none(self):
        for value in ('0', '-1', 'nan', 'inf', '—'):
            html = f'''<table><tr><th>Регион</th><th>АИ-95</th></tr>
                <tr><td>г. Санкт-Петербург</td><td>{value}</td></tr></table>'''
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

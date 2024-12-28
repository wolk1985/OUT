import requests
import time
import hmac
import base64
import hashlib
import json
import csv
import logging
from datetime import datetime, timezone

# Налаштування логування
logging.basicConfig(filename='withdrawal_log.txt', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Функція для читання ключів API з файлу CSV
def read_keys(file_path):
    try:
        with open(file_path, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                return row['api_key'], row['secret_key'], row['passphrase'], row['withdrawal_password']
    except FileNotFoundError:
        logging.error(f"Файл {file_path} не знайдено")
        print(f"Помилка: Файл {file_path} не знайдено")
        raise
    except KeyError as e:
        logging.error(f"Неправильний формат файлу {file_path}: {e}")
        print(f"Помилка: Неправильний формат файлу {file_path}: {e}")
        raise

# Функція для читання адрес гаманців з файлу CSV
def read_wallets(file_path):
    wallets = []
    try:
        with open(file_path, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                wallets.append(row['address'])
        return wallets
    except FileNotFoundError:
        logging.error(f"Файл {file_path} не знайдено")
        print(f"Помилка: Файл {file_path} не знайдено")
        raise

# Функція для читання конфігурації з файлу JSON
def read_config(file_path):
    try:
        with open(file_path, mode='r') as file:
            return json.load(file)
    except FileNotFoundError:
        logging.error(f"Файл {file_path} не знайдено")
        print(f"Помилка: Файл {file_path} не знайдено")
        raise

# OKX API ключі (зчитуються з файлу)
try:
    API_KEY, SECRET_KEY, PASSPHRASE, WITHDRAWAL_PASSWORD = read_keys('keys.csv')
    if not API_KEY or not SECRET_KEY or not PASSPHRASE or not WITHDRAWAL_PASSWORD:
        raise ValueError("API ключі, секретний ключ, парольна фраза або пароль на виведення не можуть бути пустими")
    logging.info("API ключі зчитано успішно")
except Exception as e:
    logging.error(f"Помилка зчитування API ключів: {e}")
    print(f"Помилка зчитування API ключів: {e}")
    raise

# URL для виконання запитів до OKX API
BASE_URL = 'https://www.okx.com'

# Функція для генерації заголовків автентифікації
def generate_headers(api_key, secret_key, passphrase, method, request_path, body=''):
    # Поточний час в UTC з мілісекундами
    timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace("+00:00", "Z")
    message = timestamp + method + request_path + body
    hmac_key = base64.b64decode(secret_key.encode('utf-8'))
    signature = hmac.new(hmac_key, message.encode('utf-8'), digestmod=hashlib.sha256).digest()
    signature = base64.b64encode(signature).decode()
    return {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'Content-Type': 'application/json'
    }

# Отримання доступних балансів
def get_balances():
    endpoint = '/api/v5/account/balance'
    headers = generate_headers(API_KEY, SECRET_KEY, PASSPHRASE, 'GET', endpoint)
    response = requests.get(BASE_URL + endpoint, headers=headers)
    if response.status_code == 200:
        logging.info("Баланс зчитано успішно")
        return response.json()
    else:
        logging.error("Помилка зчитування балансу: %s", response.text)
        return None

# Виведення інформації про баланс у консоль
def display_balance(currency):
    balances = get_balances()
    if balances and 'data' in balances:
        for balance in balances['data'][0]['details']:
            if balance['ccy'] == currency:
                print(f"Баланс {currency}: {balance['availBal']}")
                return
    print(f"Не вдалося отримати баланс для {currency}")
    logging.error(f"Не вдалося отримати баланс для {currency}")
    if balances:
        logging.error(f"Отримані дані: {json.dumps(balances)}")

# Отримання комісії на виведення для обраного токена і мережі
def get_withdrawal_fee(currency, chain):
    endpoint = f'/api/v5/asset/currencies'
    headers = generate_headers(API_KEY, SECRET_KEY, PASSPHRASE, 'GET', endpoint)
    response = requests.get(BASE_URL + endpoint, headers=headers)
    if response.status_code == 200:
        data = response.json()
        for item in data['data']:
            if item['ccy'] == currency:
                for chain_item in item['chains']:
                    if chain_item['chain'] == chain:
                        print(f"Комісія на виведення для {currency} в мережі {chain}: {chain_item['wdFee']}")
                        return chain_item['wdFee']
    print(f"Не вдалося отримати комісію для {currency} в мережі {chain}")
    logging.error(f"Не вдалося отримати комісію для {currency} в мережі {chain}")
    return None

# Виведення токенів на вказаний гаманець
def withdraw_token(currency, amount, to_address, chain, max_fee, withdrawal_password):
    fee = get_withdrawal_fee(currency, chain)
    if fee is None:
        return {'error': 'Не вдалося отримати комісію для транзакції'}
    if float(fee) > float(max_fee):
        logging.error(f"Комісія {fee} перевищує максимальну допустиму {max_fee}. Транзакція відмінена.")
        return {'error': 'Комісія перевищує допустиму межу'}
    
    endpoint = '/api/v5/asset/withdrawal'
    body = json.dumps({
        'ccy': currency,
        'amt': amount,
        'dest': '4',  # 4 означає, що це адреса іншого гаманця
        'toAddr': to_address,
        'chain': chain,
        'fee': fee,
        'pwd': withdrawal_password
    })
    headers = generate_headers(API_KEY, SECRET_KEY, PASSPHRASE, 'POST', endpoint, body)
    response = requests.post(BASE_URL + endpoint, headers=headers, data=body)
    if response.status_code == 200:
        logging.info("Виведення на %s успішне: %s", to_address, response.json())
    else:
        logging.error("Помилка виведення на %s: %s", to_address, response.text)
    return response.json()

# Перевірка балансу перед виведенням
def check_balance(currency, amount):
    balances = get_balances()
    if balances and 'data' in balances:
        for balance in balances['data'][0]['details']:
            if balance['ccy'] == currency and float(balance['availBal']) >= float(amount):
                return True
    return False

# Основний блок виконання скрипта
try:
    # Зчитування адрес гаманців з файлу
    wallets = read_wallets('wallets.csv')
    logging.info("Адреси гаманців зчитано успішно")

    # Зчитування конфігурації з файлу
    config = read_config('config.json')
    currency = config['currency']
    amount_per_wallet = config['amount']
    chain = config['chain']
    max_fee = config['max_fee']
    wallet_indexes = config['wallet_indexes']
    logging.info("Конфігурацію зчитано успішно")

    # Відображення балансу перед початком виведення
    display_balance(currency)

    if check_balance(currency, float(amount_per_wallet) * len(wallet_indexes)):
        for index in wallet_indexes:
            if index < len(wallets):
                wallet = wallets[index]
                result = withdraw_token(currency, amount_per_wallet, wallet, chain, max_fee, WITHDRAWAL_PASSWORD)
                print(f"Виведення на {wallet}: {result}")
                time.sleep(1)  # Затримка між запитами для уникнення перевантаження API
            else:
                logging.error(f"Індекс гаманця {index} виходить за межі списку гаманців")
    else:
        logging.error("Недостатньо коштів для виконання всіх транзакцій")
        print("Недостатньо коштів для виконання всіх транзакцій")

except Exception as e:
    logging.error(f"Невідома помилка: {e}")
    print(f"Невідома помилка: {e}")
    input("Натисніть Enter, щоб закрити...")  # Щоб користувач зміг побачити повідомлення перед закриттям консолі
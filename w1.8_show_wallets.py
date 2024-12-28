import json
import csv
import time
import logging
import requests
import hmac
import hashlib
import base64
from datetime import datetime, timezone

# Налаштування логування
logging.basicConfig(filename='log.txt', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s')

# Читання конфігураційного файлу
try:
    with open('config.json', 'r') as file:
        config = json.load(file)
except Exception as e:
    logging.error(f"Помилка при читанні config.json: {str(e)}")
    raise

# Читання API ключів
try:
    with open('api_keys.json', 'r') as file:
        api_keys = json.load(file)
except Exception as e:
    logging.error(f"Помилка при читанні api_keys.json: {str(e)}")
    raise

# Читання адрес із файлу CSV
try:
    with open('wallets.csv', 'r') as file:
        reader = csv.reader(file)
        wallet_addresses = [row[0] for row in reader]
except Exception as e:
    logging.error(f"Помилка при читанні wallets.csv: {str(e)}")
    raise

# Функція для створення підпису
def generate_signature(timestamp, method, request_path, body, secret_key):
    body_str = json.dumps(body) if body else ''
    message = timestamp + method + request_path + body_str
    mac = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode('utf-8')

# Функція для перевірки балансу
def check_balance():
    url = '/api/v5/account/balance'
    base_url = 'https://www.okx.com'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = 'GET'
    body = ''

    signature = generate_signature(timestamp, method, url, body, api_keys['secret_key'])
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': api_keys["passphrase"]
    }
    try:
        response = requests.get(base_url + url, headers=headers)
        response.raise_for_status()
        balance_data = response.json()
        return balance_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при перевірці балансу: {str(e)}")
        return None

# Функція для фільтрації та виведення основної інформації про баланс
def filter_balance_data(balance_data):
    filtered_data = []
    for detail in balance_data['data'][0]['details']:
        if float(detail['eqUsd']) > 1:
            filtered_data.append({
                'Currency': detail['ccy'],
                'Available Balance': round(float(detail['availBal']), 2),
                'Equivalent in USD': round(float(detail['eqUsd']), 2)
            })
    return filtered_data

# Функція для перевірки комісії
def check_fee(currency, chain):
    url = f'/api/v5/asset/currencies/{currency}'
    base_url = 'https://www.okx.com'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = 'GET'
    body = ''

    signature = generate_signature(timestamp, method, url, body, api_keys['secret_key'])
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': api_keys["passphrase"]
    }
    try:
        response = requests.get(base_url + url, headers=headers)
        response.raise_for_status()
        fee_data = response.json()
        for item in fee_data['data']:
            if item['ccy'] == currency and item['chain'] == chain:
                return round(float(item['withdrawal_min_fee']), 2)
        logging.error(f"Валюта {currency} у мережі {chain} не знайдена в отриманих даних.")
        return None
    except requests.exceptions.RequestException as e:
        if e.response.status_code == 404:
            logging.error(f"Помилка при перевірці комісії: Валюта не знайдена (404)")
        else:
            logging.error(f"Помилка при перевірці комісії: {str(e)}")
        return None

# Функція для виведення коштів
def withdraw(amount, address):
    url = '/api/v5/asset/withdrawal'
    base_url = 'https://www.okx.com'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = 'POST'
    body = {
        'currency': config["currency"],
        'amount': amount,
        'destination': '4',  # 4 - адреса гаманця
        'toAddress': address,
        'chain': config["chain"],
        'fee': config["max_fee"],
        'pwd': api_keys["withdrawal_password"]
    }

    signature = generate_signature(timestamp, method, url, body, api_keys['secret_key'])
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': api_keys["passphrase"],
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(base_url + url, headers=headers, json=body)
        response.raise_for_status()
        logging.info(f"Успішне виведення {amount} {config['currency']} на адресу {address}")
        print(f"Успішне виведення {amount} {config['currency']} на адресу {address}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при виведенні: {str(e)}")
        print(f"Помилка при виведенні: {str(e)}")

# Функція для отримання поточного значення GWEI через API Etherscan
def get_current_gwei():
    url = f'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey={api_keys["etherscan_api_key"]}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] == '1':
            return round(float(data['result']['ProposeGasPrice']), 2)
        else:
            logging.error(f"Помилка при запиті до Etherscan: {data['message']}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при запиті до Etherscan: {str(e)}")
        return None

# Функція для перевірки значення max_gwei
def check_gwei():
    gwei = get_current_gwei()
    if gwei is not None:
        config_max_gwei = config.get('max_gwei', 5)  # Використовується 5 як значення за замовчуванням, якщо max_gwei відсутній

        if gwei < config_max_gwei:
            logging.info(f"Поточне значення GWEI ({gwei}) менше {config_max_gwei}, виконання зняття коштів дозволено.")
            return True
        else:
            logging.warning(f"Поточне значення GWEI ({gwei}) більше {config_max_gwei}, виведення коштів заборонено.")
    else:
        logging.error("Не вдалося отримати поточне значення GWEI")
    return False

# Функція для друку параметрів конфігурації
def print_config():
    print(json.dumps(config, indent=4))

# Функція для обробки діапазонів індексів гаманців
def process_wallet_indexes(indexes):
    expanded_indexes = []
    for index in indexes:
        if isinstance(index, str) and '-' in index:
            start, end = map(int, index.split('-'))
            expanded_indexes.extend(range(start, end + 1))
        else:
            expanded_indexes.append(int(index))
    return expanded_indexes

# Основна логіка
def main():
    while True:
        print_config()
        
        # Вивід адрес гаманців з файлу wallets.csv за порядковими номерами з config.json
        if "wallet_indexes" in config:
            print("Адреси гаманців вибрані з wallets.csv:")
            selected_addresses = []
            processed_indexes = process_wallet_indexes(config["wallet_indexes"])
            for index in processed_indexes:
                if index <= len(wallet_addresses):
                    address = wallet_addresses[index - 1]
                    selected_addresses.append(address)
                    print(f"{index}: {address}")
                else:
                    logging.error(f"Індекс {index} перевищує кількість адрес у файлі")
        else:
            print("Порядкові номери гаманців не знайдено в конфігурації")
        
        if check_gwei():
            balance = check_balance()
            if balance:
                filtered_balance = filter_balance_data(balance)
                for entry in filtered_balance:
                    print(f"Currency: {entry['Currency']}, Available Balance: {entry['Available Balance']}, Equivalent in USD: {entry['Equivalent in USD']}")
                total_eq_usd = round(float(balance['data'][0]['totalEq']), 2)
                print(f"Total Equivalent in USD: {total_eq_usd}")

                eth_balance = next((item for item in balance['data'][0]['details'] if item['ccy'] == 'ETH'), None)
                if eth_balance and float(eth_balance['availBal']) >= float(config["amount"]):
                    # Перевірка комісії
                    fee = check_fee(config["currency"], config["chain"])
                    if fee:
                        print(f"Комісія на виведення {config['currency']} у мережі {config['chain']}: {fee}")
                        for address in selected_addresses:
                            withdraw(config["amount"], address)
                    else:
                        print("Не вдалося отримати дані про комісію")
                else:
                    print("Недостатньо коштів на балансі")
            else:
                print("Не вдалося отримати баланс")
        else:
            print("Виведення коштів заборонено через високе значення GWEI")

        # Оновлення кожні 60 секунд
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Непередбачена помилка: {str(e)}")
        print(f"Непередбачена помилка: {str(e)}")

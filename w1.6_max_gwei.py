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
                    format='%(asctime)s %(levelname)s:%(message)s')

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
                'Available Balance': detail['availBal'],
                'Equivalent in USD': detail['eqUsd']
            })
    return filtered_data

# Функція для перевірки комісії
def check_fee(currency, chain):
    url = f'/api/v5/asset/currencies/{currency}'
    base_url = 'https://www.okx.com'
    timestamp = datetime.now(timezone.utc).strftime('%Y-%м-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = 'GET'
    body = ''

    signature = generate_signature(timestamp, method, url, body, api_keys['secret_key'])
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASСПHRASE': api_keys["passphrase"]
    }
    try:
        response = requests.get(base_url + url, headers=headers)
        response.raise_for_status()
        fee_data = response.json()
        for item in fee_data['data']:
            if item['ccy'] == currency and item['chain'] == chain:
                return item['withdrawal_min_fee']
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
    timestamp = datetime.now(timezone.utc).strftime('%Y-%м-%дT%H:%M:%S.%f')[:-3] + 'Z'
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
    url = f'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey={config["etherscan_api_key"]}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] == '1':
            return data['result']['ProposeGasPrice']
        else:
            logging.error(f"Помилка при запиті до Etherscan: {data['message']}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Помилка при запиті до Etherscan: {str(e)}")
        return None

# Функція для перевірки значення max_gwei і оновлення config.json
def check_and_update_max_gwei():
    gwei = get_current_gwei()
    if gwei is not None:
        max_gwei = float(gwei)
        if max_gwei < 5:
            config['max_gwei'] = max_gwei
            with open('config.json', 'w') as file:
                json.dump(config, file, indent=4)
            return True
        else:
            logging.warning(f"Поточне значення GWEI ({max_gwei}) більше 5, виведення коштів заборонено.")
    else:
        logging.error("Не вдалося отримати поточне значення GWEI")
    return False

# Основна логіка
def main():
    # Перевірка та оновлення max_gwei
    if check_and_update_max_gwei():
        balance = check_balance()
        if balance:
            filtered_balance = filter_balance_data(balance)
            for entry in filtered_balance:
                print(f"Currency: {entry['Currency']}, Available Balance: {entry['Available Balance']}, Equivalent in USD: {entry['Equivalent in USD']}")
            print(f"Total Equivalent in USD: {balance['data'][0]['totalEq']}")

            eth_balance = next((item for item in balance['data'][0]['details'] if item['ccy'] == 'ETH'), None)
            if eth_balance and float(eth_balance['availBal']) >= float(config["amount"]):
                # Перевірка комісії
                fee = check_fee(config["currency"], config["chain"])
                if fee:
                    print(f"Комісія на виведення {config['currency']} у мережі {config['chain']}: {fee}")
                    for index in config["wallet_indexes"]:
                        if index <= len(wallet_addresses):
                            address = wallet_addresses[index - 1]
                            withdraw(config["amount"], address)
                        else:
                            logging.error(f"Індекс {index} перевищує кількість адрес у файлі")
                else:
                    print("Не вдалося отримати дані про комісію")
            else:
                print("Недостатньо коштів на балансі")
        else:
            print("Не вдалося отримати баланс")
    else:
        print("Виведення коштів заборонено через високе значення GWEI")

    # Щоб скрипт не закривався після виконання
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()

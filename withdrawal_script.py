import json
import csv
import time
import logging
import requests

# Налаштування логування
logging.basicConfig(filename='log.txt', level=logging.INFO, 
                    format='%(asctime)s %(levelname)s:%(message)s')

# Читання конфігураційного файлу
with open('config.json', 'r') as file:
    config = json.load(file)

# Читання API ключів
with open('api_keys.json', 'r') as file:
    api_keys = json.load(file)

# Читання адрес із файлу CSV
with open('wallets.csv', 'r') as file:
    reader = csv.reader(file)
    wallet_addresses = [row[0] for row in reader]

# Функція для перевірки балансу
def check_balance():
    url = 'https://www.okx.com/api/v5/account/balance'
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': '',  # Потрібно сформувати підпис
        'OK-ACCESS-TIMESTAMP': '',  # Потрібно сформувати часовий штамп
        'OK-ACCESS-PASSPHRASE': api_keys["passphrase"]
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        balance_data = response.json()
        return balance_data
    else:
        logging.error(f"Помилка при перевірці балансу: {response.text}")
        return None

# Функція для перевірки комісії
def check_fee():
    # Логіка для перевірки комісії
    pass

# Функція для виведення коштів
def withdraw(amount, address):
    url = 'https://www.okx.com/api/v5/asset/withdrawal'
    headers = {
        'OK-ACCESS-KEY': api_keys["api_key"],
        'OK-ACCESS-SIGN': '',  # Потрібно сформувати підпис
        'OK-ACCESS-TIMESTAMP': '',  # Потрібно сформувати часовий штамп
        'OK-ACCESS-PASSPHRASE': api_keys["passphrase"]
    }
    data = {
        'currency': config["currency"],
        'amount': amount,
        'destination': '4',  # 4 - адреса гаманця
        'toAddress': address,
        'chain': config["chain"],
        'fee': config["max_fee"],
        'pwd': api_keys["withdrawal_password"]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        logging.info(f"Успішне виведення {amount} {config['currency']} на адресу {address}")
        print(f"Успішне виведення {amount} {config['currency']} на адресу {address}")
    else:
        logging.error(f"Помилка при виведенні: {response.text}")
        print(f"Помилка при виведенні: {response.text}")

# Основна логіка
def main():
    balance = check_balance()
    if balance:
        print(f"Баланс: {balance}")
        # Перевірка комісії
        if check_fee():
            for index in config["wallet_indexes"]:
                if index <= len(wallet_addresses):
                    address = wallet_addresses[index - 1]
                    withdraw(config["amount"], address)
                else:
                    logging.error(f"Індекс {index} перевищує кількість адрес у файлі")
        else:
            print("Комісія перевищує максимальне обмеження")
    else:
        print("Не вдалося отримати баланс")

    # Щоб скрипт не закривався після виконання
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()

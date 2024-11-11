import os
import signal
import requests
import telebot
import time
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN');
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID');
TELEGRAM_THREAD_ID = os.environ.get('TELEGRAM_THREAD_ID');
VK_API_VERSION = os.environ.get('VK_API_VERSION');
VK_ACCESS_TOKEN = os.environ.get('VK_ACCESS_TOKEN');
VK_GROUP_ID = os.environ.get('VK_GROUP_ID');

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Трэк начала работы бота
bot_start_time = datetime.now()

# Функция для получения Long Poll информации с ВК Группы
def get_longpoll_server():
    response = requests.get('https://api.vk.com/method/groups.getLongPollServer', params={
        'group_id': VK_GROUP_ID,
        'access_token': VK_ACCESS_TOKEN,
        'v': VK_API_VERSION
    })

    data = response.json()
    if 'response' in data:
        return data['response']
    else:
        print(f"Error fetching Long Poll server info: {data}")
        return None

# Функция для чека Long Poll ивентов и нотификации в Телеграмм
def check_longpoll(server_info):
    try:
        response = requests.get(server_info['server'], params={
            'act': 'a_check',
            'key': server_info['key'],
            'ts': server_info['ts'],
            'wait': 25  # Время ожидания в секундах (может быть изменено, если нужно)
        })

        data = response.json()
        if 'updates' in data:
            for update in data['updates']:
                # Проверка если апдейт это новый ивент с постом (wall_post_new)
                if update['type'] == 'wall_post_new':
                    post_id = update['object']['id']
                    send_telegram_message(post_id)
            # Обновление server_info 'ts' параметра для нового запроса
            server_info['ts'] = data['ts']
        else:
            # Хендлер неудачного ответа
            handle_failed_response(server_info, data)
    except Exception as e:
        print(f"Exception during Long Poll check: {e}")

# Функция для форматирования и отправки сообщения в Телеграмм чат и прикрепления ссылки
def send_telegram_message(post_id):
    try:
        post_link = f"https://vk.com/wall-{VK_GROUP_ID}_{post_id}"
        message = f"📢 **Новый пост в нашей группе!**\n\n[Лайкать здесь]({post_link})"

        # Отправляет сообщение в указанный Телеграмм чат и тему
        bot.send_message(TELEGRAM_CHAT_ID, message, parse_mode='Markdown', disable_web_page_preview=False, message_thread_id=TELEGRAM_THREAD_ID)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

# Функция для обработки ошибочных ответов с Long Poll
def handle_failed_response(server_info, data):
    if 'failed' in data:
        if data['failed'] == 1:
            # Ошибка 1: устаревшее значение 'ts'
            print(f"Outdated 'ts' value, updating: {data}")
            server_info['ts'] = data['ts']
        elif data['failed'] == 2:
            # Ошибка 2: устаревший 'ключ'
            print(f"Expired 'key', fetching new Long Poll server info.")
            new_server_info = get_longpoll_server()
            if new_server_info:
                server_info.update(new_server_info)
        elif data['failed'] == 3:
            # Ошибка 3: неправильное значение 'ts', получите новый 'ts' с сервера
            print(f"Invalid 'ts' value, getting new Long Poll server info.")
            new_server_info = get_longpoll_server()
            if new_server_info:
                server_info.update(new_server_info)
        else:
            print(f"Unknown 'failed' error: {data}")

# Команд хендлер для проверки аптайма бота
@bot.message_handler(commands=['uptime'])
def uptime(message):
    # Проверяем, что команда была вызвана в групповом чате или супергруппе
    if message.chat.type not in ["group", "supergroup"]:
        # Если команда вызвана не в группе, игнорируем её
        bot.send_message(message.chat.id, "Эта команда доступна только в групповом чате.")
        return
    
    # Получаем продолжительность работы бота
    uptime_duration = datetime.now() - bot_start_time

    # Разбиваем продолжительность на дни, часы, минуты и секунды
    days, remainder = divmod(uptime_duration.total_seconds(), 86400)  # 86400 секунд в день
    hours, remainder = divmod(remainder, 3600)  # 3600 секунд в часе
    minutes, seconds = divmod(remainder, 60)  # 60 секунд в минуте

    # Форматируем аптайм для отправки
    formatted_uptime = f"{int(days)} дней, {int(hours)} часов, {int(minutes)} минут, {int(seconds)} секунд"

    try:
        # Отправка сообщения об аптайме
        bot.send_message(TELEGRAM_CHAT_ID, f"🤖 Я работаю уже: {formatted_uptime}",
                     parse_mode='Markdown',
                     disable_web_page_preview=False,
                     message_thread_id=TELEGRAM_THREAD_ID) # Выбор конкретной темы
        
    except Exception as e:
        print(f"Ошибка отправки сообщения об аптайме: {e}")

should_run = True
def signal_handler(sig, frame):
    should_run = False

# Основная функция для старта бота и мониторинга ВК постов
def start_bot():
    print("Starting...")
    server_info = get_longpoll_server()
    if server_info:
        print(f"Long Poll server info obtained: {server_info}")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)
        signal.signal(signal.SIGABRT, signal_handler)

        while should_run:
            check_longpoll(server_info)

            # Небольшая задержка чтобы предотвратить чрезмерную загрузку (может быть изменено, если нужно)
            time.sleep(1)

        print("Finished.")
    else:
        print("Failed to obtain Long Poll server info. Exiting...")

if __name__ == "__main__":
    # Старт проверки на Телеграмм команды
    from threading import Thread
    Thread(target=bot.polling, daemon=True).start()

    # Начало ВК Long Poll чекинга
    start_bot()
import os
import signal
import time
from datetime import datetime, timedelta
from threading import Thread, Lock

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_THREAD_ID = os.getenv('TELEGRAM_THREAD_ID')
VK_API_VERSION = os.getenv('VK_API_VERSION')
VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')

# Инициализация глобальных переменных и блокировок
bot = None
bot_start_time = datetime.now()
should_run = True
should_run_lock = Lock()  # Блокировка для переменной `should_run`

def lazy_telebot():
    global bot
    if bot is None:
        import telebot
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    return bot

# Ленивая загрузка для библиотеки requests
def lazy_requests():
    import requests
    return requests

# Функция для получения Long Poll информации с ВК Группы
def get_longpoll_server():
    requests = lazy_requests()
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

# Функция для проверки Long Poll ивентов и нотификации в Телеграм
def check_longpoll(server_info):
    try:
        requests = lazy_requests()
        response = requests.get(server_info['server'], params={
            'act': 'a_check',
            'key': server_info['key'],
            'ts': server_info['ts'],
            'wait': 25  # Время ожидания в секундах (можно изменить)
        })

        data = response.json()
        if 'updates' in data:
            for update in data['updates']:
                if update['type'] == 'wall_post_new':
                    post_id = update['object']['id']
                    send_telegram_message(post_id)
            server_info['ts'] = data['ts']
        else:
            handle_failed_response(server_info, data)
    except Exception as e:
        print(f"Exception during Long Poll check: {e}")

# Функция для отправки сообщения в Телеграмм с информацией о посте
def send_telegram_message(post_id):
    try:
        post_link = f"https://vk.com/wall-{VK_GROUP_ID}_{post_id}"
        message = f"📢 **Новый пост в нашей группе!**\n\n[Лайкать здесь]({post_link})"
        
        bot = lazy_telebot()
        bot.send_message(
            TELEGRAM_CHAT_ID, 
            message, 
            parse_mode='Markdown', 
            disable_web_page_preview=False, 
            message_thread_id=TELEGRAM_THREAD_ID
        )
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

# Функция для обработки ошибок при Long Poll
def handle_failed_response(server_info, data):
    if 'failed' in data:
        if data['failed'] == 1:
            server_info['ts'] = data['ts']
        elif data['failed'] == 2:
            new_server_info = get_longpoll_server()
            if new_server_info:
                server_info.update(new_server_info)
        elif data['failed'] == 3:
            new_server_info = get_longpoll_server()
            if new_server_info:
                server_info.update(new_server_info)
        else:
            print(f"Unknown 'failed' error: {data}")

# Команда /uptime для Телеграм
def uptime_command(message):
    if message.chat.type not in ["group", "supergroup"]:
        lazy_telebot().send_message(message.chat.id, "Эта команда доступна только в групповом чате.")
        return

    uptime_duration = datetime.now() - bot_start_time
    days, remainder = divmod(uptime_duration.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    formatted_uptime = f"{int(days)} дней, {int(hours)} часов, {int(minutes)} минут, {int(seconds)} секунд"

    try:
        lazy_telebot().send_message(
            TELEGRAM_CHAT_ID, 
            f"🤖 Я работаю уже: {formatted_uptime}",
            parse_mode='Markdown',
            disable_web_page_preview=False,
            message_thread_id=TELEGRAM_THREAD_ID
        )
    except Exception as e:
        print(f"Ошибка отправки сообщения об аптайме: {e}")

# Обработка сигнала завершения
def signal_handler(sig, frame):
    global should_run
    with should_run_lock:
        should_run = False

# Основная функция запуска
def start_bot():
    print("Starting...")
    server_info = get_longpoll_server()
    if server_info:
        print(f"Long Poll server info obtained: {server_info}")
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            with should_run_lock:
                if not should_run:
                    break
            check_longpoll(server_info)
            time.sleep(1)
        print("Finished.")
    else:
        print("Failed to obtain Long Poll server info. Exiting...")

# Запуск программы
if __name__ == "__main__":
    bot_instance = lazy_telebot()
    bot_instance.message_handler(commands=['uptime'])(uptime_command)

    Thread(target=lambda: bot_instance.polling(none_stop=True), daemon=True).start()
    start_bot()

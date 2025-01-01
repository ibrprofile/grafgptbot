import os
import telebot
import sqlite3
import logging
from PIL import Image
import numpy as np
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import openai


logging.basicConfig(level=logging.INFO)


BOT_TOKEN = "" # токен бота 
GPT_API_KEY = "" # токен gpt 
bot = telebot.TeleBot(BOT_TOKEN)
openai.api_key = GPT_API_KEY

# база данных 
conn = sqlite3.connect("bot_users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute(""" 
CREATE TABLE IF NOT EXISTS users ( 
    user_id INTEGER PRIMARY KEY, 
    username TEXT, 
    full_name TEXT, 
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
) 
""")
conn.commit()

# загрузка фоток
IMG_FOLDER = "imgs"
os.makedirs(IMG_FOLDER, exist_ok=True)

def register_user(user_id, username, full_name):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)", 
                   (user_id, username, full_name))
    conn.commit()


# анализ графа
def analyze_graph(image_path):
    try:
        image = Image.open(image_path).convert('L')
        image = image.resize((100, 100))  
        data = np.array(image)
        
        top_half = data[:50, :].mean()
        bottom_half = data[50:, :].mean()

        if top_half < bottom_half:
            trend = "вверх"
            probability = (bottom_half - top_half) / bottom_half * 100
        else:
            trend = "вниз"
            probability = (top_half - bottom_half) / top_half * 100

        return trend, round(probability, 2)
    except Exception as e:
        logging.error(f"Ошибка анализа графика: {e}")
        return None, "Ошибка анализа графика."

# анализ от gpt
def gpt_analysis(trend_result, probability):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты финансовый аналитик, предоставляющий прогнозы на основе трендов и вероятностей."},
                {"role": "user", "content": f"На основании текущего тренда {trend_result} с вероятностью {probability:.2f}%, предоставь прогноз на ближайшие 5 минут в формате:\n"
                                             "1. Вероятность небольшого роста: [значение]\n"
                                             "2. Вероятность стабильности: [значение]\n"
                                             "3. Вероятность небольшого снижения: [значение]\n"
                                             "Также укажи возможные изменения:\n"
                                             "- Если произойдет рост, то значение может увеличиться на [значение]%\n"
                                             "- Если сохранится стабильность, значение останется на текущем уровне.\n"
                                             "- Если будет снижение, значение может уменьшиться на [значение]%. \n"
                                             "Пожалуйста, сформируй ответ в четком и понятном виде."}
            ]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        logging.error(f"Ошибка GPT анализа: {e}")
        return "Ошибка в GPT анализе."


# команда /start
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    username = message.from_user.username
    full_name = f"{message.from_user.first_name} {message.from_user.last_name}"
    register_user(user_id, username, full_name)
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! 👋\n"
        "Отправь мне фотографию графика, и я сделаю прогноз! 📈"
    )

# обработка фотки
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        bot.send_message(message.chat.id, "Анализируем ваш график... 🕵️‍♂️")
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_path = os.path.join(IMG_FOLDER, f"{message.chat.id}_latest_chart.png")

        with open(image_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        trend, probability = analyze_graph(image_path)
        if trend is None:  
            bot.send_message(message.chat.id, probability)  
            return

        bot.send_message(
            message.chat.id,
            f"🔍 Анализ завершен!\n\nНа ближайшие 5 минут прогноз: *{trend}*.\n🎯 Вероятность: {probability:.2f}%.",
            parse_mode="Markdown"
        )

        markup = InlineKeyboardMarkup()
        
        markup.add(InlineKeyboardButton("Получить полный анализ 📝", callback_data=f"analyze_{trend}_{probability}"))
        bot.send_message(message.chat.id, "Нажмите кнопку, чтобы получить полный анализ.", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при обработке изображения: {e}")
        logging.error(f"Ошибка при обработке изображения: {e}")

# ответ + полный анализ
@bot.callback_query_handler(func=lambda call: call.data.startswith("analyze_"))
def full_analysis(call):
    trend_result, probability = call.data.split("_")[1:3]  
    probability = float(probability)  
    gpt_result = gpt_analysis(trend_result, probability)
    
    bot.send_message(
        call.message.chat.id,
        f"📊 *Полный анализ*:\n\n{gpt_result}",
        parse_mode="Markdown"
    )

# Запуск бота
bot.polling(none_stop=True)
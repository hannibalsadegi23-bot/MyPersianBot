import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی جمینی (با مدل PRO) ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    model = None

# ... (بخش لاگ و وب‌سرور مثل قبل است) ...
# ...

# --- تابع ترجمه (با دستورالعمل فوق پیشرفته) ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "خطا: مدل هوش مصنوعی به درستی تنظیم نشده است."
    try:
        # --- تغییر اصلی اینجاست ---
        # این دستورالعمل به هوش مصنوعی یاد می‌دهد که چگونه ترجمه کند
        prompt = f"""
        You are an expert literary translator. Your task is to translate the following English text into a natural, modern, and emotional Persian.
        Do not perform a literal, word-for-word translation. Instead, capture the deep meaning, sentiment, and tone of the original text.
        Use colloquial and common Persian words (e.g., use 'آدما' instead of 'مردم' or 'انسان ها').
        The final output must be only the Persian translation, without any additional text or explanations.

        Here is an example of a good translation:
        English: "Sometimes you just have to accept that some people are meant to stay in your heart, not in your life."
        Persian: "گاهی اوقات مجبوریم بپذیریم که بعضی آدما فقط میتونن توی قلبمون بمونن نه توی زندگیمون ."

        Now, translate the following text with the same high quality:
        English Text: "{text_to_translate}"
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return "خطا در هنگام ترجمه با هوش مصنوعی."

# ... (تمام توابع دیگر ربات مثل قبل باقی می‌مانند) ...
# (start_command, handle_channel_post, button_callback_handler, main)
# ...

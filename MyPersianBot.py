import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# --- خواندن اطلاعات از متغیرهای محیطی ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی جمینی (با مدل FLASH برای سرعت و سهمیه بیشتر) ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest') # <--- تغییر به مدل Flash
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    model = None

# --- ساخت حافظه پنهان (Cache) برای ترجمه‌ها ---
translation_cache = {}

# ... (بخش لاگ، وب‌سرور و توابع دیگر مثل قبل است) ...
# ...

# --- تابع کلیک روی دکمه (مجهز به حافظه پنهان) ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            
            # ۱. ابتدا در حافظه پنهان جستجو کن
            if original_text in translation_cache:
                translated_text = translation_cache[original_text]
                logger.info("Translation found in cache!")
            else:
                # ۲. اگر در حافظه نبود، از هوش مصنوعی ترجمه را بگیر
                translated_text = translate_with_gemini(original_text)
                # ۳. نتیجه را در حافظه ذخیره کن برای استفاده‌های بعدی
                if translated_text and "خطا" not in translated_text:
                    translation_cache[original_text] = translated_text
                    logger.info("Translation fetched from Gemini and cached.")

            if translated_text and len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            # ... (بقیه منطق نمایش خطا یا پیام بلند مثل قبل است)

        except Exception as e:
            # ... (بخش مدیریت خطا مثل قبل است)

# ... (تمام توابع دیگر ربات مثل قبل باقی می‌مانند) ...

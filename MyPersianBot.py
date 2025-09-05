import logging
import os
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest

# --- خواندن اطلاعات از متغیرهای محیطی Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی جمینی ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # اضافه کردن تنظیمات ایمنی برای کاهش سخت‌گیری
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    model = genai.GenerativeModel('gemini-1.5-flash', safety_settings=safety_settings)
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    model = None

# بقیه کد... (بخش لاگ، وب‌سرور، استارت و پیام کانال مثل قبل است)
# ...

# --- تابع ترجمه با هوش مصنوعی جمینی (با لاگ اضافه شده) ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "خطا: مدل هوش مصنوعی به درستی تنظیم نشده است."
    try:
        logger.info(f"Sending to Gemini for translation: '{text_to_translate}'")
        prompt = f"Translate the following English text to Persian. Provide only the Persian translation, without any additional explanations or introductory phrases. The text is:\n\n\"{text_to_translate}\""
        response = model.generate_content(prompt)
        
        # --- بخش جدید اشکال‌زدایی ---
        # ما پاسخ خام جمینی را در لاگ چاپ می‌کنیم
        logger.info(f"Received from Gemini: '{response.text}'")
        # ---------------------------
        
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini translation failed: {e}")
        return "خطا در هنگام ترجمه با هوش مصنوعی."

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            translated_text = translate_with_gemini(original_text)
            
            if translated_text: # اگر پاسخ خالی نبود
                if len(translated_text) <= 200:
                    await query.answer(text=translated_text, show_alert=True)
                else:
                    await query.answer(text="ترجمه طولانی است و به صورت خصوصی ارسال شد.", show_alert=True)
                    await context.bot.send_message(chat_id=query.from_user.id, text=f"-- ترجمه با هوش مصنوعی --\n\n{translated_text}")
            else: # اگر پاسخ خالی بود
                await query.answer(text="هوش مصنوعی پاسخی برای این متن ارائه نکرد.", show_alert=True)

        except Exception as e:
            logger.error(f"Callback handler failed: {e}", exc_info=True)
            await query.answer(text="خطا در ترجمه!", show_alert=True)

# تابع main و بقیه کدها مثل قبل است...
# ...

import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CallbackQueryHandler, MessageHandler, Filters
from googletrans import Translator

TOKEN = os.environ.get('BOT_TOKEN')
app = Flask(__name__)

@app.route('/')
def home():
    return "ربات تلگرام در حال اجراست!"

@app.route('/health')
def health():
    return "OK", 200

def translate_text(text, dest='fa'):
    try:
        translator = Translator()
        translation = translator.translate(text, dest=dest)
        return translation.text
    except Exception as e:
        print(f"ترجمه خطا: {e}")
        return "خطا در ترجمه"

def handle_message(update: Update, context: CallbackContext):
    if update.channel_post:
        message = update.channel_post
        if message.text:
            keyboard = [[InlineKeyboardButton("Translate", callback_data="trans")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                context.bot.send_message(
                    chat_id=message.chat_id,
                    text="👇 ترجمه فارسی",
                    reply_to_message_id=message.message_id,
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"خطا در ارسال پیام: {e}")

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    original_message = query.message.reply_to_message
    
    if original_message and original_message.text:
        translated_text = translate_text(original_message.text)
        query.answer(translated_text, show_alert=True)

def run_bot():
    print("🚀 در حال راه‌اندازی ربات...")
    try:
        updater = Updater(TOKEN)
        dp = updater.dispatcher
        
        dp.add_handler(MessageHandler(Filters.TEXT & Filters.CHAT_TYPE_CHANNEL, handle_message))
        dp.add_handler(CallbackQueryHandler(button_click))
        
        updater.start_polling()
        print("✅ ربات با موفقیت راه‌اندازی شد!")
        updater.idle()
    except Exception as e:
        print(f"❌ خطای ربات: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ خطا: متغیر محیطی BOT_TOKEN تنظیم نشده است!")
        exit(1)
    
    print("🎯 شروع برنامه...")
    
    # اجرای ربات در thread جداگانه
    bot_thread = Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # اجرای Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

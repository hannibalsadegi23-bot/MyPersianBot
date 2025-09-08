import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from googletrans import Translator

TOKEN = os.environ.get('BOT_TOKEN')
app = Flask(__name__)

@app.route('/')
def home():
    return "ربات تلگرام در حال اجراست!"

def translate_text(text):
    try:
        return Translator().translate(text, dest='fa').text
    except:
        return "خطا در ترجمه"

def handle_message(update: Update, context: CallbackContext):
    if update.channel_post and update.channel_post.text:
        keyboard = [[InlineKeyboardButton("Translate", callback_data="trans")]]
        context.bot.send_message(
            chat_id=update.channel_post.chat_id,
            text="👇 ترجمه فارسی",
            reply_to_message_id=update.channel_post.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    if query.message.reply_to_message and query.message.reply_to_message.text:
        translated = translate_text(query.message.reply_to_message.text)
        query.answer(translated, show_alert=True)

def run_bot():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(filters.TEXT & filters.CHAT_TYPE_CHANNEL, handle_message))
    dp.add_handler(CallbackQueryHandler(button_click))
    updater.start_polling()
    print("✅ ربات فعال شد!")
    updater.idle()

if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN تنظیم نشده!")
        exit(1)
    
    bot_thread = Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

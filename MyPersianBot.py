import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CallbackQueryHandler, MessageHandler, Filters
from googletrans import Translator

TOKEN = os.environ.get('BOT_TOKEN')

def translate_text(text):
    translator = Translator()
    return translator.translate(text, dest='fa').text

def handle_message(update: Update, context: CallbackContext):
    if update.channel_post:
        message = update.channel_post
        if message.text:
            keyboard = [[InlineKeyboardButton("Translate", callback_data="trans")]]
            context.bot.send_message(
                chat_id=message.chat_id,
                text="👇 ترجمه فارسی",
                reply_to_message_id=message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    original_message = query.message.reply_to_message
    if original_message.text:
        translated = translate_text(original_message.text)
        query.answer(translated, show_alert=True)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.channel, handle_message))
    dp.add_handler(CallbackQueryHandler(button_click))
    updater.start_polling()
    print("✅ ربات فعال شد!")
    updater.idle()

if __name__ == "__main__":
    main()

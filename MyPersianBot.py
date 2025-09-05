import logging
import os # اضافه کردن این کتابخانه
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from deep_translator import GoogleTranslator

# --- خواندن اطلاعات از متغیرهای محیطی ---
TOKEN = os.environ.get("8458479260:AAHlcMSYBTK7MS7iGhKvOad1yEfxLFXyE-M")
CHANNEL_ID = int(os.environ.get(" -1001257817278"))
USERNAME = os.environ.get("HaMaGhT")
CHANNEL_LINK = os.environ.get("iTsAnarchy")

translator = GoogleTranslator(source='auto', target='fa')
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Contact", url=f"https.me/{USERNAME}"), InlineKeyboardButton("Channel", url=f"https.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(rf"سلام {user.mention_html()} عزیز،\nاین ربات برای استفاده های غریبه نیست.", reply_markup=reply_markup)

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if message and message.chat.id == CHANNEL_ID and message.text:
        try:
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_to_fa')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Could not add button: {e}")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            translated_text = translator.translate(query.message.text)
            if len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            else:
                await query.answer(text="ترجمه طولانی است و به صورت خصوصی ارسال شد.")
                await context.bot.send_message(chat_id=query.from_user.id, text=f"-- ترجمه متن طولانی --\n\n{translated_text}")
        except Exception as e:
            logger.error(f"Translation failed: {e}", exc_info=True)
            await query.answer(text="خطا در ترجمه!", show_alert=True)

def main() -> None:
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    application = Application.builder().token(TOKEN).request(request).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    print("Bot is running on Render...")
    application.run_polling()

if __name__ == '__main__':
    main()

# وارد کردن کتابخانه‌های مورد نیاز
import logging
import os
import threading
from flask import Flask
import google.generativeai as genai  # <-- این خط در نسخه قبلی شما اشتباه تایپی داشت و اینجا اصلاح شده است
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

# --- خواندن اطلاعات محرمانه از متغیرهای محیطی سایت Render ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_ID = int(os.environ.get("YOUR_CHANNEL_ID"))
USERNAME = os.environ.get("YOUR_USERNAME")
CHANNEL_LINK = os.environ.get("YOUR_CHANNEL_LINK")

# --- راه‌اندازی هوش مصنوعی جمینی با مدل پیشرفته Pro ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception as e:
    print(f"خطا در هنگام راه‌اندازی جمینی: {e}")
    model = None

# --- تنظیمات لاگ برای خطایابی ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- بخش وب‌سرور برای بیدار نگه داشتن ربات در Render ---
app = Flask(__name__)
@app.route('/')
def index():
    return "ربات بیدار و فعال است!"
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

# --- تابع اصلی برای ترجمه با هوش مصنوعی جمینی ---
def translate_with_gemini(text_to_translate):
    if not model:
        return "خطا: مدل هوش مصنوعی به درستی تنظیم نشده است."
    try:
        # دستورالعمل حرفه‌ای برای دریافت ترجمه طبیعی و روان
        prompt = f"""
        Your task is to translate the following English text into elegant and natural-sounding Persian.
        Pay close attention to the original tone, style, and nuance.
        The translation should be fluent and poetic, not a literal word-for-word translation.
        Provide only the final Persian translation without any extra comments or introductory phrases.

        English Text:
        "{text_to_translate}"
        """
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"ترجمه با جمینی ناموفق بود: {e}")
        return "خطا در هنگام ترجمه با هوش مصنوعی."

# --- توابع مربوط به دستورات ربات ---
# تابع برای دستور /start در چت خصوصی
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Contact", url=f"https://t.me/{USERNAME}"), InlineKeyboardButton("Channel", url=f"https://t.me/{CHANNEL_LINK}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_html(rf"سلام {user.mention_html()} عزیز،\nاین ربات برای استفاده های غریبه نیست.", reply_markup=reply_markup)

# تابع برای مدیریت پیام‌های جدید در کانال
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post
    if message and message.chat.id == CHANNEL_ID and message.text:
        try:
            keyboard = [[InlineKeyboardButton("Translate", callback_data='translate_to_fa')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"امکان اضافه کردن دکمه وجود نداشت: {e}")

# تابع برای مدیریت کلیک روی دکمه ترجمه
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == 'translate_to_fa':
        try:
            original_text = query.message.text
            translated_text = translate_with_gemini(original_text)

            if translated_text and len(translated_text) <= 200:
                await query.answer(text=translated_text, show_alert=True)
            elif translated_text:
                await query.answer(text="خطا: متن ترجمه شده برای نمایش در پاپ-آپ بیش از حد طولانی است.", show_alert=True)
            else:
                await query.answer(text="هوش مصنوعی پاسخی برای این متن ارائه نکرد.", show_alert=True)

        except Exception as e:
            logger.error(f"مدیریت کلیک ناموفق بود: {e}", exc_info=True)
            try:
                await query.answer(text="خطا در ترجمه! ممکن است پاسخ هوش مصنوعی طول کشیده باشد.", show_alert=True)
            except BadRequest:
                logger.error("امکان ارسال پاپ‌آپ خطا وجود نداشت چون درخواست قدیمی شده بود.")

# --- تابع اصلی برای اجرای ربات ---
def main() -> None:
    # اجرای وب‌سرور در پس‌زمینه
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # تنظیمات شبکه ربات
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)
    
    # ساخت و راه‌اندازی ربات
    application = Application.builder().token(TOKEN).request(request).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    print("ربات مترجم با هوش مصنوعی (حالت حرفه‌ای - فقط پاپ‌آپ) در حال اجراست...")
    application.run_polling()

# این خط به پایتون می‌گوید که برنامه را از تابع main شروع کند
if __name__ == '__main__':
    main()

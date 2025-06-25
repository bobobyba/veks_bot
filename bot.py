import platform
import socket
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    CallbackContext,
    filters
)

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ЗАЩИТА ОТ ДУБЛИРОВАНИЯ ====================
if platform.system() != "Windows":
    try:
        lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        lock_socket.bind('\0' + 'VeKs_bot_lock')
        logger.info("🔒 Бот запущен в единственном экземпляре")
    except socket.error:
        logger.error("⚠️ Ошибка: уже запущена другая копия бота!")
        exit(1)
else:
    logger.warning("⚠️ Защита через сокеты отключена для Windows")

# ==================== КОНСТАНТЫ И НАСТРОЙКИ ====================
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("❌ Токен бота не найден! Убедитесь, что переменная TELEGRAM_TOKEN установлена")
    exit(1)

materials = {
    'банер': 300,
    'пленка': 500,
    'холст': 700
}

MIN_SIZE = 0.1
MAX_SIZE = 50.0
MIN_QUANTITY = 1
MAX_QUANTITY = 1000

STEP_MATERIAL = 1
STEP_WIDTH = 2
STEP_HEIGHT = 3
STEP_QUANTITY = 4
STEP_COMPLETED = 5

user_data = {}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def format_price(price: float) -> str:
    """Форматирует цену с пробелами между тысячами"""
    return "{:,.2f}".format(price).replace(",", " ").replace(".", ",")

def calculate_cost(material: str, height: float, width: float, quantity: int) -> str:
    """Рассчитывает стоимость заказа"""
    if material not in materials:
        return "❌ Ошибка: материал не найден"
    
    material_cost = materials[material]
    area = height * width
    cost_per_item = area * material_cost
    total_cost = cost_per_item * quantity
    
    return (
        f"📊 <b>Итоговый расчет</b>\n\n"
        f"🖨️ Материал: {material}\n"
        f"📐 Размер: {width}м × {height}м\n"
        f"🔢 Количество: {quantity} шт.\n\n"
        f"💵 <b>Стоимость: {format_price(total_cost)} руб.</b>"
    )

def parse_number(text: str) -> float:
    """Преобразует строку в число, заменяя запятые на точки"""
    try:
        return float(text.replace(',', '.'))
    except ValueError:
        raise ValueError("Некорректное число")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    
    # Сбрасываем данные пользователя
    if user_id in user_data:
        del user_data[user_id]
    
    keyboard = [
        [InlineKeyboardButton("Банер", callback_data="банер")],
        [InlineKeyboardButton("Пленка", callback_data="пленка")],
        [InlineKeyboardButton("Холст", callback_data="холст")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = "👋 <b>Привет! Я помогу рассчитать стоимость заказа.</b>\n\nВыберите материал:"
    
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

async def material_selection(update: Update, context: CallbackContext) -> None:
    """Обработчик выбора материала"""
    query = update.callback_query
    await query.answer()
    
    material = query.data
    user_data[query.from_user.id] = {'material': material, 'step': STEP_WIDTH}
    
    await query.edit_message_text(
        text=f"🖌️ <b>Выбран материал:</b> {material}\n\nВведите ширину в метрах:",
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Обработчик текстовых сообщений"""
    user_id = update.message.from_user.id
    text = update.message.text

    # Если расчет завершен
    if user_id in user_data and user_data[user_id].get('step') == STEP_COMPLETED:
        await update.message.reply_text(
            "📌 Расчет завершен. Начните новый расчет командой /start",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Новый расчет", callback_data="restart")]
            ]),
            parse_mode='HTML'
        )
        return

    if user_id not in user_data:
        await update.message.reply_text("ℹ️ Пожалуйста, начните с команды /start")
        return

    try:
        current_step = user_data[user_id]['step']

        if current_step == STEP_WIDTH:
            width = parse_number(text)
            if not (MIN_SIZE <= width <= MAX_SIZE):
                raise ValueError(f"Ширина должна быть от {MIN_SIZE} до {MAX_SIZE} м")
            user_data[user_id]['width'] = width
            user_data[user_id]['step'] = STEP_HEIGHT
            await update.message.reply_text("📏 Введите высоту в метрах:")

        elif current_step == STEP_HEIGHT:
            height = parse_number(text)
            if not (MIN_SIZE <= height <= MAX_SIZE):
                raise ValueError(f"Высота должна быть от {MIN_SIZE} до {MAX_SIZE} м")
            user_data[user_id]['height'] = height
            user_data[user_id]['step'] = STEP_QUANTITY
            await update.message.reply_text("🔢 Введите количество:")

        elif current_step == STEP_QUANTITY:
            quantity = int(text)
            if not (MIN_QUANTITY <= quantity <= MAX_QUANTITY):
                raise ValueError(f"Количество должно быть от {MIN_QUANTITY} до {MAX_QUANTITY} шт.")
            
            material = user_data[user_id]['material']
            width = user_data[user_id]['width']
            height = user_data[user_id]['height']
            
            result = calculate_cost(material, height, width, quantity)
            user_data[user_id]['step'] = STEP_COMPLETED
            
            keyboard = [[InlineKeyboardButton("🔄 Новый расчет", callback_data="restart")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(result, reply_markup=reply_markup, parse_mode='HTML')

    except ValueError as e:
        logger.error(f"Ошибка ввода: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка! {str(e)}")

async def restart(update: Update, context: CallbackContext) -> None:
    """Обработчик кнопки 'Новый расчет'"""
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ==================== ЗАПУСК БОТА ====================
def main() -> None:
    """Запуск приложения"""
    try:
        application = Application.builder().token(TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(material_selection, pattern="^(банер|пленка|холст)$"))
        application.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("🤖 Бот запускается...")
        application.run_polling()

    except Exception as e:
        logger.error(f"🚨 Ошибка при запуске бота: {str(e)}")
        exit(1)

if __name__ == '__main__':
    main()
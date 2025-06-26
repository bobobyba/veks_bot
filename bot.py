import logging
import os
import asyncio
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    CallbackContext,
    filters
)

# Глобальная блокировка для предотвращения дублирования
import fcntl
lock_file = None

def acquire_lock():
    global lock_file
    lock_file = open('bot.lock', 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("🔒 Файловая блокировка установлена")
        return True
    except (IOError, BlockingIOError):
        logger.warning("⚠️ Бот уже запущен! Завершаем процесс.")
        return False

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('bot.log')
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# ==================== ЗАЩИТА ОТ ДУБЛИРОВАНИЯ ====================
def prevent_multiple_instances():
    if not acquire_lock():
        exit(1)

prevent_multiple_instances()

# ==================== КОНСТАНТЫ И НАСТРОЙКИ ====================
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Структура материалов с ценами
MATERIALS = {
    'банер': {
        'Ламинированный': 350,
        'Литой': 400, 
        'Двухсторонний': 450
    },
    'пленка': {
        'С ламинацией': 550,
        'Без ламинации': 500
    },
    'холст': {
        'Натуральный': 800,
        'Синтетический': 700
    }
}

MIN_SIZE = 0.1
MAX_SIZE = 50.0
MIN_QUANTITY = 1
MAX_QUANTITY = 1000

# Шаги диалога
STEP_MATERIAL = 1
STEP_MATERIAL_TYPE = 2
STEP_WIDTH = 3
STEP_HEIGHT = 4
STEP_QUANTITY = 5
STEP_COMPLETED = 6

user_data = {}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================== 

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
    """Обработчик выбора основного материала"""
    query = update.callback_query
    await query.answer()
    
    material = query.data
    user_data[query.from_user.id] = {
        'material': material,
        'step': STEP_MATERIAL_TYPE
    }
    
    # Создаем кнопки для подтипов материала
    buttons = []
    for material_type in MATERIALS[material]:
        buttons.append([InlineKeyboardButton(material_type, callback_data=f"type_{material_type}")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(
        text=f"🖌️ <b>Выбран материал:</b> {material}\n\nВыберите тип:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================== 
def format_price(price: float) -> str:
    """Форматирует цену с пробелами между тысячами"""
    return "{:,.2f}".format(price).replace(",", " ").replace(".", ",")

def calculate_cost(material: str, material_type: str, height: float, width: float, quantity: int) -> str:
    """Рассчитывает стоимость заказа с компактным выводом"""
    if material not in MATERIALS or material_type not in MATERIALS[material]:
        return "❌ Ошибка: неверно указан материал"
    
    price_per_sqm = MATERIALS[material][material_type]
    area = height * width
    total_cost = area * price_per_sqm * quantity
    
    return (
        f"📊 <b>Итоговый расчет</b>\n\n"
        f"🖨️ Материал: {material} ({material_type})\n"
        f"📏 Размер: {width}м × {height}м | "
        f"🔢 Количество: {quantity} шт.\n\n"
        f"💵 <b>Стоимость: {format_price(total_cost)} руб.</b>"
    )

async def material_type_selection(update: Update, context: CallbackContext) -> None:
    """Обработчик выбора типа материала"""
    query = update.callback_query
    await query.answer()
    
    material_type = query.data.replace('type_', '')
    user_id = query.from_user.id
    user_data[user_id]['material_type'] = material_type
    user_data[user_id]['step'] = STEP_WIDTH
    
    await query.edit_message_text(
        text=f"🖨️ <b>Материал:</b> {user_data[user_id]['material']} ({material_type})\n\n"
             f"Введите ширину в метрах:",
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
            material_type = user_data[user_id]['material_type']
            width = user_data[user_id]['width']
            height = user_data[user_id]['height']
            
            result = calculate_cost(material, material_type, height, width, quantity)
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
async def main():
    """Основная асинхронная функция запуска"""
    try:
        application = Application.builder().token(TOKEN).build()
        
        # Асинхронный сброс вебхука
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхук сброшен, соединения очищены")

        # Регистрация обработчиков (ваш существующий код)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(material_selection, pattern="^(банер|пленка|холст)$"))
        application.add_handler(CallbackQueryHandler(material_type_selection, pattern="^type_"))
        application.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("🤖 Бот запускается...")
        await application.run_polling()

    except telegram.error.Conflict as e:
        logger.error(f"🚨 Конфликт: {e}. Убедитесь, что бот не запущен в другом месте.")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка: {str(e)}")
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    finally:
        if lock_file:
            lock_file.close()

if __name__ == '__main__':
    prevent_multiple_instances()  # Проверка перед запуском
    asyncio.run(main())
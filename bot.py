from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, CallbackContext
from telegram.ext import filters

TOKEN = '7978164646:AAEbOwVCrJ4mfmKQKZ77Ynpvs1rRvxHSZQc'

materials = {
    'банер': 300,
    'пленка': 500,
    'холст': 700
}

# Минимальные и максимальные значения
MIN_SIZE = 0.1
MAX_SIZE = 999999
MIN_QUANTITY = 1
MAX_QUANTITY = 1000

STEP_MATERIAL = 1
STEP_WIDTH = 2
STEP_HEIGHT = 3
STEP_QUANTITY = 4
STEP_COMPLETED = 5  # Новый шаг - расчет завершен

user_data = {}

def format_price(price: float) -> str:
    """Форматирует цену с пробелами между тысячами"""
    return "{:,.2f}".format(price).replace(",", " ").replace(".", ",")

def calculate_cost(material, height, width, quantity):
    if material not in materials:
        return "Ошибка: материал не найден"
    
    material_cost = materials[material]
    area = height * width
    cost_per_item = area * material_cost
    total_cost = cost_per_item * quantity
    
    return (
        f"📊 <b>Итоговый расчет</b>\n\n"
        f"🎨 Материал: {material}\n"
        f"📏 Размер: {width}м × {height}м\n"
        f"🔢 Количество: {quantity} шт.\n\n"
        f"💵 <b>Стоимость: {format_price(total_cost)} руб.</b>"
    )

async def start(update: Update, context: CallbackContext) -> None:
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
    query = update.callback_query
    await query.answer()
    
    material = query.data
    user_data[query.from_user.id] = {'material': material, 'step': STEP_WIDTH}
    
    await query.edit_message_text(
        text=f"🖌️ <b>Выбран материал:</b> {material}\n\nВведите ширину в метрах:",
        parse_mode='HTML'
    )

def parse_number(text: str) -> float:
    return float(text.replace(',', '.'))

async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

    # Если расчет завершен, предлагаем начать новый
    if user_id in user_data and user_data[user_id].get('step') == STEP_COMPLETED:
        await update.message.reply_text(
            "Расчет завершен. Начните новый расчет командой /start",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Новый расчет", callback_data="restart")]
            ]),
            parse_mode='HTML'
        )
        return

    if user_id not in user_data:
        await update.message.reply_text("Пожалуйста, начните с команды /start")
        return

    try:
        current_step = user_data[user_id]['step']

        if current_step == STEP_WIDTH:
            width = parse_number(text)
            if not (MIN_SIZE <= width <= MAX_SIZE):
                raise ValueError
            user_data[user_id]['width'] = width
            user_data[user_id]['step'] = STEP_HEIGHT
            await update.message.reply_text("📏 Введите высоту в метрах:")

        elif current_step == STEP_HEIGHT:
            height = parse_number(text)
            if not (MIN_SIZE <= height <= MAX_SIZE):
                raise ValueError
            user_data[user_id]['height'] = height
            user_data[user_id]['step'] = STEP_QUANTITY
            await update.message.reply_text("🔢 Введите количество:")

        elif current_step == STEP_QUANTITY:
            quantity = int(text)
            if not (MIN_QUANTITY <= quantity <= MAX_QUANTITY):
                raise ValueError
            
            material = user_data[user_id]['material']
            width = user_data[user_id]['width']
            height = user_data[user_id]['height']
            
            result = calculate_cost(material, height, width, quantity)
            
            # Помечаем расчет как завершенный
            user_data[user_id]['step'] = STEP_COMPLETED
            
            keyboard = [[InlineKeyboardButton("🔄 Новый расчет", callback_data="restart")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                result,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

    except ValueError:
        await update.message.reply_text("❌ Ошибка! Пожалуйста, введите корректное число.")

async def restart(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await start(update, context)

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(material_selection, pattern="^(банер|пленка|холст)$"))
    application.add_handler(CallbackQueryHandler(restart, pattern="^restart$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()
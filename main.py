import telebot
import threading
from telebot import types
import time
import asyncio
from bleak import BleakClient, BleakScanner
from env import *

bot = telebot.TeleBot(TOKEN)

DEVICE_NAME = "ESP32_SmartLamp"
TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

UI = {
    'home': '\U0001F3E0',
    'gear': '\u2699\ufe0f',
    'robot': '\U0001F916',
    'hand': '\u270B',
    'sun': '\u2600\ufe0f',
    'bulb': '\U0001F4A1',
    'clock': '\U0001F552',
    'sync': '\U0001F504',
    'power_on': '\u2705',
    'power_off': '\U0001F534',
    'keyboard': '\u2328\ufe0f',
    'loading': '\u23F3',
    'bt_on': '\U0001F517',
    'bt_off': '\U0001F198',
    'check': '\u2705',
    'search': '\U0001F50D'
}

ambient_light = 0
lamp_brightness = 0
auto_mode = True
offset = 0
manual_value = 50
is_powered_on = True

ble_connected = False
ble_client = None
dashboard_msg_id = None
current_chat_id = None

async def send_to_esp(command):
    global ble_client, ble_connected
    if ble_connected and ble_client:
        try:
            await ble_client.write_gatt_char(RX_UUID, command.encode())
        except Exception as e:
            print(f"Error: {e}")

def notification_handler(sender, data):
    global ambient_light, lamp_brightness
    try:
        raw_data = data.decode('utf-8')
        parts = raw_data.split('-')
        if len(parts) == 2:
            ambient_light = int(parts[0])
            raw_bright = int(parts[1])
            lamp_brightness = int((raw_bright / 255) * 100)
            update_dashboard()
    except Exception as e:
        print(f"Error: {e}")

async def ble_worker():
    global ble_connected, ble_client
    while True:
        if not ble_connected:
            try:
                print(f"{UI['search']} Поиск {DEVICE_NAME}...")
                device = await BleakScanner.find_device_by_name(DEVICE_NAME)
                if device:
                    print(f"{UI['check']} Устройство подлючено!...")
                    async with BleakClient(device) as client:
                        ble_client = client
                        ble_connected = True
                        update_dashboard()
                        await client.start_notify(TX_UUID, notification_handler)
                        while client.is_connected:
                            await asyncio.sleep(1)
            except Exception as e:
                print(f"Stopped: {e}")
            ble_connected = False
            ble_client = None
            update_dashboard()
        await asyncio.sleep(5)

ble_loop = asyncio.new_event_loop()

def sync_with_hardware():
    if not is_powered_on:
        cmd = "M0"
    elif auto_mode:
        cmd = f"A{offset}"
    else:
        val_255 = int((manual_value / 100) * 255)
        cmd = f"M{val_255}"
    asyncio.run_coroutine_threadsafe(send_to_esp(cmd), ble_loop)

def create_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    p_label = f"{UI['power_off']} ВЫКЛЮЧИТЬ" if is_powered_on else f"{UI['power_on']} ВКЛЮЧИТЬ"
    markup.add(types.InlineKeyboardButton(p_label, callback_data="toggle_power"))
    m_label = 'АВТО' if auto_mode else 'РУЧНОЙ'
    markup.add(types.InlineKeyboardButton(f"{UI['sync']} Режим: {m_label}", callback_data="toggle_mode"))
    if auto_mode:
        markup.add(
            types.InlineKeyboardButton("-10% Смещение", callback_data="off_-10"),
            types.InlineKeyboardButton("+10% Смещение", callback_data="off_+10")
        )
    else:
        markup.add(types.InlineKeyboardButton(f"{UI['keyboard']} Ввести яркость", callback_data="ask_manual"))
    return markup

def update_dashboard():
    if dashboard_msg_id and current_chat_id:
        m_icon = UI['robot'] if auto_mode else UI['hand']
        m_text = "АВТОМАТИЧЕСКИЙ" if auto_mode else "РУЧНОЙ"
        p_status = "" if is_powered_on else " *(ВЫКЛЮЧЕНО)*"
        bt_status = f"{UI['bt_on']} Связь: OK" if ble_connected else f"{UI['bt_off']} Связь: ПОТЕРЯНА"
        text = (f"{UI['home']} **УМНЫЙ СВЕТ: ПАНЕЛЬ**\n\n"
                f"{bt_status}\n"
                f"{UI['gear']} Режим: `{m_icon} {m_text}`\n"
                f"{UI['sun']} Датчик: `{ambient_light}`\n"
                f"{UI['bulb']} Лампа: `{lamp_brightness}%`{p_status} "
                + (f" ({offset:+d}%)" if auto_mode and offset != 0 else "") +
                f"\n{UI['clock']} Обновлено: {time.strftime('%H:%M:%S')}")
        try:
            bot.edit_message_text(
                chat_id=current_chat_id,
                message_id=dashboard_msg_id,
                text=text,
                reply_markup=create_keyboard(),
                parse_mode='Markdown'
            )
        except:
            pass

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global auto_mode, offset, is_powered_on
    if call.data == "toggle_power":
        is_powered_on = not is_powered_on
    elif call.data == "toggle_mode":
        auto_mode = not auto_mode
    elif call.data.startswith("off_"):
        val = int(call.data.split("_")[1])
        offset = max(-100, min(100, offset + val))
    elif call.data == "ask_manual":
        bot.answer_callback_query(call.id, "Напишите яркость 0-100")
        bot.register_next_step_handler(call.message, process_manual_input)
        return
    sync_with_hardware()
    update_dashboard()
    bot.answer_callback_query(call.id)

def process_manual_input(message):
    global manual_value
    try:
        bot.delete_message(message.chat.id, message.message_id)
        val = int(message.text)
        manual_value = max(0, min(100, val))
        sync_with_hardware()
        update_dashboard()
    except:
        pass

@bot.message_handler(commands=['start'])
def start(message):
    global dashboard_msg_id, current_chat_id
    current_chat_id = message.chat.id
    sent_msg = bot.send_message(current_chat_id, f"{UI['loading']} Подключение...", reply_markup=create_keyboard())
    dashboard_msg_id = sent_msg.message_id
    update_dashboard()

def start_ble_thread():
    asyncio.set_event_loop(ble_loop)
    ble_loop.run_until_complete(ble_worker())

threading.Thread(target=start_ble_thread, daemon=True).start()
bot.polling(none_stop=True)
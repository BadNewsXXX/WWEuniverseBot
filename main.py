import asyncio
import logging
import database.database as db
import keyboards as kb
import hashlib
import hmac
import base64
import websockets
import json
import requests
import os


from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import CallbackQuery
from datetime import datetime, timezone, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import StateFilter
from dotenv import load_dotenv





# Загружаем переменные из .env файла
load_dotenv()

# Получаем значения переменных окружения
tg_key = os.getenv("TOKEN")
api_key = os.getenv("OKX_api_key")
secret_key = os.getenv("OKX_secret_key")
passphrase = os.getenv("OKX_passphrase")
cmc_key = os.getenv("CMC_api_key")



# log
logging.basicConfig(level=logging.INFO)
# init
bot = Bot(token=os.getenv("TOKEN"))
dp = Dispatcher(storage = MemoryStorage())


async def create_signature(timestamp, method, requestPath, body =''):
    if body == '{}' or body is None:
        body = ''
    message = f'{timestamp}{method}{requestPath}{body}'
    mac = hmac.new(bytes(os.getenv("OKX_secret_key"), encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod=hashlib.sha256)
    signature = base64.b64encode(mac.digest()).decode('utf-8')
    return signature

async def get_time():
    timestamp = int(datetime.now(timezone.utc).timestamp())
    return str(timestamp)

async def ping_pong(websocket):
    while True:
        try:
            await websocket.ping()
            print("Ping sent")
            await asyncio.sleep(10)  # Отправляем пинг каждые 10 секунд
        except Exception as e:
            print(f"Ping error: {e}")
            break

async def authenticate_and_ping():
    url = "wss://ws.okx.com:8443/ws/v5/business"
    async with websockets.connect(url, timeout=15, ping_timeout=None, ping_interval=None) as websocket:
        print("WebSocket connection established")

        timestamp = await get_time()
        method = 'GET'
        requestPath = '/users/self/verify'
        body = ''
        signature = await create_signature(timestamp, method, requestPath, body)

        login_message = {
            "op": "login",
            "args": [
                {
                    "apiKey": os.getenv("OKX_api_key"),
                    "passphrase": os.getenv("OKX_passphrase"),
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ]
        }
        await websocket.send(json.dumps(login_message))
        auth_response = await websocket.recv()
        print(f"Authentication response: {auth_response}")

        subscribe_message = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "deposit-info",
                    "uid": "429658822286951495"
                }
            ]
        }
        print(f"Sent subscription request: {subscribe_message}")
        await websocket.send(json.dumps(subscribe_message))
        response = await websocket.recv()
        print(f"Subscription response: {response}")
        
        # Запускаем получение сообщений и пинг параллельно
        await asyncio.gather(
            handle_responses(websocket),
            ping_pong(websocket)
        )

# Функция обработки ответов WebSocket
async def handle_responses(websocket):
    while True:
        try:
            response = await websocket.recv()
            print("Received response:", response)
            
            try:
                data = json.loads(response)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {e}")
                continue
            
            print("Parsed data:", data)

            if 'data' in data:
                for deposit in data['data']:
                    print(f"Deposit info: {deposit}")

                    txId = deposit.get('txId')
                    amount = deposit.get('amt')
                    state = deposit.get('state')
                    timestamp = deposit.get('ts')
                    currency = deposit.get('ccy')

                    if not txId:
                        print("Invalid txId format")
                        continue
                    
                    if isinstance(amount, (int, float)):
                        amount = float(amount)
                    elif isinstance(amount, str):
                        try:
                            amount = float(amount)
                        except ValueError:
                            print("Invalid amount format")
                            continue
                    else:
                        print("Invalid amount format")
                        continue
                    
                    if not isinstance(state, str) or not state.isdigit():
                        print("Invalid state format")
                        continue
                    state = int(state)
                    try:
                        timestamp = float(timestamp) / 1000  # Преобразование в секунды
                        timestamp = datetime.fromtimestamp(timestamp)
                    except (ValueError, TypeError):
                        print("Invalid timestamp format")
                        continue

                    await db.handle_deposit(txId, amount, state, timestamp, currency)
                    
            else:
                print("No 'data' key in response")
                
        except websockets.ConnectionClosedOK:
            print("WebSocket connection closed by server")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

async def get_crypto_rate(crypto_symbol):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    parameters = {
        'symbol': crypto_symbol,
        'convert': 'USDT'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': os.getenv("CMC_api_key"),  # Вставьте ваш ключ
    }

    response = requests.get(url, headers=headers, params=parameters)
    data = response.json()
    return data['data'][crypto_symbol]['quote']['USDT']['price']

# Пример использования
ltc_rate = get_crypto_rate('LTC')
ton_rate = get_crypto_rate('TON')
print(f'LTC rate: {ltc_rate}, TON rate: {ton_rate}')
                      





class TransactionState(StatesGroup):
    waiting_for_hash = State()
    waiting_for_hash_LTC = State()



@dp.message(Command("add_subscription"))
async def add_subscription(message: types.Message):
    # Укажите ваш Telegram user_id
    admin_user_id = int(os.getenv("Acc_id"))  # Ваш личный user_id

    # Проверка, является ли отправитель сообщения вами (администратором)
    if message.from_user.id != admin_user_id:
        await message.reply("You are not authorized to use this command.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("Please provide the user_id as an argument.")
        return

    # Преобразуем user_id в целое число
    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply("Invalid user_id. Please provide a valid numeric ID.")
        return
    
    # Преобразуем количество месяцев в целое число
    try:
        months = int(args[2])
        if months <= 0:
            raise ValueError("The number of months must be positive.")
    except ValueError:
        await message.reply("Invalid number of months. Please provide a valid number.")
        return

    # Проверяем, есть ли уже пользователь в базе
    async with db.async_session() as session:
        user = await session.scalar(db.select(db.UserSubscription).where(db.UserSubscription.user_id == user_id))

        if not user:
            # Если пользователя нет, добавляем его в базу
            new_subscription = db.UserSubscription(
                user_id=user_id,
                subscription_start=datetime.now(timezone.utc),
                subscription_end=datetime.now(timezone.utc) + timedelta(days=30 * months)  # Добавляем 1 месяц
            )
            session.add(new_subscription)
            await message.reply(f"User {user_id}'s subscription has been added for {months} month(s).")
        else:
            user.subscription_end += timedelta(days=30 * months)
            await message.reply(f"User {user_id}'s subscription has been extended by {months} month(s).")

        await session.commit()

    try:
        result = await bot.create_chat_invite_link(db.CHANNEL_ID, member_limit=1)
        await bot.send_message(user_id, f"Your link to the channel: {result.invite_link}.")
    except Exception as e:
        await message.reply(f"Failed to add user {user_id}: {e}")


@dp.message(Command("remove_subscription"))
async def remove_subscription(message: types.Message):
    # Укажите ваш Telegram user_id
    admin_user_id = int(os.getenv("Acc_id"))  # Ваш личный user_id

    # Проверка, является ли отправитель сообщения вами (администратором)
    if message.from_user.id != admin_user_id:
        await message.reply("You are not authorized to use this command.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Please provide the user_id as an argument.")
        return

    # Преобразуем user_id в целое число
    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply("Invalid user_id. Please provide a valid numeric ID.")
        return

    # Удаляем пользователя из базы данных
    async with db.async_session() as session:
        user = await session.scalar(db.select(db.UserSubscription).where(db.UserSubscription.user_id == user_id))

        if not user:
            await message.reply(f"No subscription found for user {user_id}.")
            return

        # Удаляем пользователя из базы данных
        await session.delete(user)
        await session.commit()
        await message.reply(f"User {user_id}'s subscription has been removed from the database.")

    # Удаляем пользователя из канала
    try:
        await bot.ban_chat_member(db.CHANNEL_ID, user_id)
        await bot.unban_chat_member(db.CHANNEL_ID, user_id)
        print(f"User {user_id} has been removed and unbanned from the channel.")
    except Exception as e:
        await message.reply(f"Failed to remove user {user_id} from the channel: {e}")


#message
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    await message.answer("Hello!", reply_markup=kb.main)
    await message.answer("Choose the channel you need. Welcome! ⭐️", reply_markup=kb.channels)

@dp.callback_query(F.data =='public channel')
async def Sub_on_month(callback: CallbackQuery):
    await callback.answer('Public channel')
    await callback.message.edit_text("Public channel: https://t.me/wweuniverse00 \n", parse_mode="HTML", reply_markup=kb.backtomenu)

@dp.callback_query(F.data =='back to menu channels')
async def Menu_back(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.channels)


@dp.callback_query(F.data =='private channel')
async def SubscriptionMenu(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("Hello. Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.subscriptions)

@dp.callback_query(F.data =='TelegramStars')
async def TelegramXTR(callback: CallbackQuery):
    await callback.answer('')
    prices = [LabeledPrice(label="Support with Stars", amount=450)]  
    await bot.send_invoice(
        callback.message.chat.id,
        title="Premium subscription on month",
        description="Here you can pay via telegram stars. Just simply press pay button.",
        currency="XTR",
        prices=prices,
        start_parameter="stars_support",
        payload="support-payment"
    )

@dp.callback_query(F.data == 'TelegramStars(2)')
async def TelegramXTR2(callback: CallbackQuery):
    await callback.answer('')
    prices = [LabeledPrice(label="Support with Stars", amount=1100)]
    await bot.send_invoice(
        callback.message.chat.id,
        title="Premium subscription on 3 months",
        description="Here you can pay via telegram stars. Just simply press pay button.",
        currency="XTR",
        prices=prices,
        start_parameter="stars_support_2",
        payload="support-payment-2"
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    # Проверка на допустимость товара и других параметров
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    successful_payment: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    amount = successful_payment.total_amount  # без деления

    # Обработка количества месяцев подписки в зависимости от суммы
    months = 0
    if successful_payment.invoice_payload == "support-payment" and amount >= 450:
        months = 1
    elif successful_payment.invoice_payload == "support-payment-2" and amount >= 1100:
        months = 3

    # Если сумма недостаточная, отправляем сообщение
    if months == 0:
        await message.answer("Insufficient amount to activate a subscription.")
        return

    result_message = await db.provide_productStars(user_id, months)
    await message.answer(result_message)


@dp.callback_query(F.data =='DonationAlerts')
async def da_pay_1month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f" <b>Payment method:</b> 🌎 Donation Alerts \n <b>Cost:</b> 6$ \n <b>Your ID:</b> {user_id} \n 1. Head to the link below: https://www.donationalerts.com/r/wweuniverse69 . \n \n 2. Choose exact amount of 6$. \n \n 3. In the message box, enter your ID that you see above. 👆 \n \n 4. Choose a convenient payment method for you. \n \n 5. After your donation this bot will provide you private channel link! ✅ \n \n Enjoy! ☀️ \n \n If need help: https://t.me/actuallydone \n", parse_mode="HTML", reply_markup=kb.DA_donate)    

@dp.callback_query(F.data =='DonationAlerts(2)')
async def da_pay_3months(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f" <b>Payment method:</b> 🌎 Donation Alerts \n <b>Cost:</b> 15$ \n <b>Your ID:</b> {user_id} \n 1. Head to the link below: https://www.donationalerts.com/r/wweuniverse69 . \n \n 2. Choose exact amount of 15$. \n \n 3. In the message box, enter your ID that you see above. 👆 \n \n 4. Choose a convenient payment method for you. \n \n 5. After your donation this bot will provide you private channel link! ✅ \n \n Enjoy! ☀️ \n \n If need help: https://t.me/actuallydone \n", parse_mode="HTML", reply_markup=kb.DA_donate2) 

@dp.callback_query(F.data =='back from paymentDA')
async def TRC20pay_on_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text("<b> Premium access on MONTH </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n - Interesting information about WWE superstars outside of the ring! \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 30 days \n <b> Price:</b> 6$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment1)

@dp.callback_query(F.data =='back from paymentDA(2)')
async def TRC20pay_on_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text("<b> Premium access on 3 MONTHS </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 90 days \n <b> Price:</b> 15$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment2)

@dp.message(F.text =='Subscriptions 💵')
async def SubscriptionMenu(message: types.Message):
    await message.answer("Hello,honey 😏. Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.subscriptions)

@dp.message(F.text =='Support ⚙️')
async def Support(message: types.Message):
    await message.answer("If you read the FAQ and didn't find the answer to your question, you can personally DM me : https://t.me/actuallydone ")

@dp.message(F.text =='FAQ ❔')
async def FAQ(message: types.Message):
    await message.answer(" 1.<b> I always encounter low-quality videos. What’s the quality like on your channel? </b> \n Answer: All my videos are available in 1080p and above, so you don’t need to worry about quality. \n 2. <b>Why is there a cost for this content?</b> \n Answer: Many people can’t watch WWE on TV due to various reasons—work, health, etc. On my channel, you’ll find high-quality content, faster than anywhere else, ready for you to enjoy whenever you can. 😊 \n 3. <b>I don’t understand how to do something(pay,choose,etc.). What should I do?</b> \n Answer: Don't worry, just personally DM me and I will solve your issue. \n <b>But don't spam.</b> You will slow down the proccess. Think of others. \n 4. <b>If I accidentally made an incorrect payment, is there a refund?</b> \n Answer: If you paid to my crypto address but used the wrong network, it’s okay—we can sort it out. Also, if you used other payment methods, just DM me, and I’ll assist you ASAP. \n My contact: https://t.me/actuallydone ", parse_mode="HTML")

@dp.callback_query(F.data =='prem on month')
async def Sub_on_month(callback: CallbackQuery):
    await callback.answer('You chose premium on month')
    await callback.message.edit_text("<b> Premium access on MONTH </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n - Interesting information about WWE superstars outside of the ring! \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 30 days \n <b> Price:</b> 6$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment1)

@dp.callback_query(F.data =='prem on 3 months')
async def Sub_on_3months(callback: CallbackQuery):
    await callback.answer('You chose prem on month')
    await callback.message.edit_text("<b> Premium access on 3 MONTHS </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 90 days \n <b> Price:</b> 15$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment2)


@dp.callback_query(F.data =='back to menu')
async def Menu_back(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.subscriptions)


@dp.callback_query(F.data =='paymentTRC20')
async def TRC20pay_on_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f" <b>Payment method:</b> 🌎 Crypto: USDT(TRC20) \n <b>Cost:</b> 6$ \n <b>Your ID:</b> {user_id} \n <b>Payment address:</b> \n \n Tether USDT (TRC20): \n <pre>TGsNKiNTHRxMXmymYRzV73TkwidzJLV4Uu</pre> \n Make a payment using address above 👆 \n \n Once your payment is successful, click on the 'I paid' button and enter your transaction hash. It will automatically grant you access to the channel! \n \n Wait few minutes for transaction completion ✅ \n \n If need help: https://t.me/actuallydone \n", parse_mode="HTML", reply_markup= kb.paymentbutton)    

@dp.callback_query(F.data =='paymentTRC20(2)')
async def TRC20pay_on_3months(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f" <b>Payment method:</b> 🌎 Crypto: USDT(TRC20) \n <b>Cost:</b> 15$ \n <b>Your ID:</b> {user_id} \n <b>Payment address:</b> \n \n Tether USDT (TRC20): \n <pre>TGsNKiNTHRxMXmymYRzV73TkwidzJLV4Uu</pre> \n Make a payment using address above 👆 \n \n Once your payment is successful, click on the 'I paid' button and enter your transaction hash. It will automatically grant you access to the channel! \n \n Wait few minutes for transaction completion ✅ \n \n If need help: https://t.me/actuallydone \n", parse_mode="HTML", reply_markup= kb.paymentbutton2)    
    

@dp.callback_query(F.data =='paymentTON')
async def TONpay_on_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f"<b>Payment method:</b> 🌎 Crypto: Toncoin (TON) \n Your ID:<b> {user_id} </b>, Cost: <b> 6$ </b> \n To make a right deposit, you need to follow a few steps: \n 1. Press the button <b> 'Start payment' </b> \n 2. Copy amount of cryptocurrency. ⚠️<b> WARNING! </b> (You need to send EXACT amount or MORE. Be aware of fees. If you deposit via <b>wallet</b>, it's gonna be fee so be attentive! If you deposit via <b>exchange</b>, check the amount you are sending!) \n 3. Copy address and <b>MEMO</b>, and send funds to it. ⚠️<b> WARNING! </b> (You need to copy <b>MEMO</b> and write it to correctly pass the payment.) \n 4. Once your transaction completed, simply press button <b> 'I paid' </b> and write your transaction hash. \n You will have 45 minutes to do this steps. \n IF something goes wrong, don't worry, just write me DM, i will help you ASAP. \n https://t.me/actuallydone" , parse_mode="HTML", reply_markup=kb.TONpay)

@dp.callback_query(F.data =='cryptopayTON')
async def TONpay(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    fiat_amount = 6
    crypto_rate = await get_crypto_rate('TON')
     # Инициация оплаты
    crypto_amount, payment_window_end = await db.initiate_paymentTON(user_id, fiat_amount, crypto_rate, transaction_hash="")
    await callback.message.answer(
        f"<b>Payment method</b>: 🌎 Crypto: Toncoin (TON)\n"
        f"Your ID: <b>{user_id} </b>\n"
        f"Cost: {fiat_amount}$\n"
        f"<b>Address for payment:</b><pre>EQD5vcDeRhwaLgAvralVC7sJXI-fc2aNcMUXqcx-BQ-OWnOZ</pre>\n"
        f"⚠️ <b>MEMO:</b><pre>8686668</pre>\n"
        f"<b>Crypto amount(TON)</b>: <pre>{crypto_amount:.8f}</pre>\n"
        f"Payment window ends: {payment_window_end.strftime('%H:%M:%S')} (<b>UTC</b>) (in 45 minutes)\n ", 
        parse_mode="HTML", reply_markup= kb.cryptopay_exit
    )



@dp.callback_query(F.data == 'cryptopaybutton')
async def Ipaidbutton(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Checking the transaction...')
    await state.set_state(TransactionState.waiting_for_hash_LTC)
    await callback.message.answer("Enter your transaction hash.")
    

@dp.message(StateFilter(TransactionState.waiting_for_hash_LTC))
async def process_transaction_hash(message: Message, state: FSMContext):
    transaction_hash = message.text
    user_id = message.from_user.id

    if len(transaction_hash) == 64 or 66:  # Пример проверки длины хэша
        deposit_info = await db.find_matching_deposit(transaction_hash)
        
        if deposit_info:  # Проверяем, что информация о депозите получена
            status = deposit_info['status']
            deposit_ccy = deposit_info['ccy']  # Забираем ccy из ответа функции
            if status == 'completed':
                already_used = await db.get_user_id_by_transaction_hash(transaction_hash)
                if already_used is not None:
                    await message.answer("This hash has already been used.")
                    await state.clear()
                    return    
                success = await db.link_deposit_with_user(transaction_hash, user_id)
                if success:
                    transaction_info = await db.get_transaction_info(user_id)
                    if transaction_info:
                        transaction_hash = transaction_info['transaction_hash']
                        amount_received = transaction_info['amount_received']
                        await db.update_payment_info_with_hash(user_id, transaction_hash)
                        expected_ccy = await db.get_expected_currency(transaction_hash)
                        if expected_ccy is None:
                            await message.answer("Expected currency not found for your payment.")
                            await state.clear()
                            return
                        if expected_ccy != deposit_ccy:
                            await message.answer(f"Currency mismatch! Expected {expected_ccy}, but received {deposit_ccy}.")
                            await state.clear()
                            return
                        # Теперь можем вызвать функцию для проверки оплаты
                        await db.check_payment(transaction_hash, amount_received)
                    else:
                        await message.answer("Transaction information not found.")
                        await state.clear()
                else:
                    print("An error occurred while linking the transaction.")
                    await state.clear()
                await state.clear()  # Завершаем состояние ожидания

            elif status == 'pending':
                await message.answer("Transaction in process. Please wait.")
            elif status == 'not_found':
                await message.answer("Can't get info about your transaction hash. Contact the Admin.")
                await state.clear()
        else:
            await message.answer("Can't find this deposit.")
            await state.clear()
    else:
        await message.answer("Invalid transaction hash. Try again.")
        await state.clear()

@dp.callback_query(F.data =='cryptocancelpayment')
async def TONpay_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    await db.cancel_payment(user_id)
    await callback.answer('You successfully cancel the payment!')
    await callback.message.edit_text("Hello,honey 😏. Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.subscriptions)





@dp.callback_query(F.data =='paymentTON(2)')
async def TONpay_on_3months(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f" <b>Payment method:</b> 🌎 Crypto: Toncoin(TON) \n <b>Cost:</b> 15$ \n <b>Your ID:</b> {user_id} \n To make a right deposit, you need to follow a few steps: \n 1. Press the button <b> 'Start payment' </b> \n 2. Copy amount of cryptocurrency. ⚠️<b> WARNING! </b> (You need to send EXACT amount or MORE. Be aware of fees. If you deposit via wallet, it's gonna be fee so be attentive! If you deposit via exchange, check the amount you are sending!) \n 3. Copy address and <b>MEMO</b>, and send funds to it. ⚠️<b> WARNING! </b> You need to copy <b>MEMO</b> and write it to correctly pass the payment. \n 4. Once your transaction completed, simply press button <b> 'I paid' </b> and write your transaction hash. \n You will have 45 minutes to do this steps. \n IF something goes wrong, don't worry, just write me DM, i will help you ASAP. \n https://t.me/actuallydone" , parse_mode="HTML", reply_markup=kb.TONpay2)

@dp.callback_query(F.data =='cryptopayTON(2)')
async def TONpay(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    fiat_amount = 15
    crypto_rate = await get_crypto_rate('TON')
     # Инициация оплаты
    crypto_amount, payment_window_end = await db.initiate_paymentTON(user_id, fiat_amount, crypto_rate, transaction_hash="")
    await callback.message.answer(
        f"<b>Payment method</b>: 🌎 Crypto: Toncoin (TON)\n"
        f"Your ID: <b>{user_id} </b>\n"
        f"Cost: {fiat_amount}$\n"
        f"<b>Address for payment:</b><pre>EQD5vcDeRhwaLgAvralVC7sJXI-fc2aNcMUXqcx-BQ-OWnOZ</pre>\n"
        f"⚠️ <b>MEMO:</b><pre>8686668</pre>\n"
        f"<b>Crypto amount(TON)</b>: <pre>{crypto_amount:.8f}</pre>\n"
        f"Payment window ends: {payment_window_end.strftime('%H:%M:%S')} (<b>UTC</b>) (in 45 minutes)\n ", 
        parse_mode="HTML", reply_markup= kb.cryptopay_exit
    )



@dp.callback_query(F.data == 'cryptopaybutton')
async def Ipaidbutton(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Checking the transaction...')
    await state.set_state(TransactionState.waiting_for_hash_LTC)
    await callback.message.answer("Enter your transaction hash.")
    

@dp.message(StateFilter(TransactionState.waiting_for_hash_LTC))
async def process_transaction_hash(message: Message, state: FSMContext):
    transaction_hash = message.text
    user_id = message.from_user.id

    if len(transaction_hash) == 64 or 66:  # Пример проверки длины хэша
        deposit_info = await db.find_matching_deposit(transaction_hash)
        
        if deposit_info:  # Проверяем, что информация о депозите получена
            status = deposit_info['status']
            deposit_ccy = deposit_info['ccy']  # Забираем ccy из ответа функции
            if status == 'completed':
                already_used = await db.get_user_id_by_transaction_hash(transaction_hash)
                if already_used is not None:
                    await message.answer("This hash has already been used.")
                    await state.clear()
                    return    
                success = await db.link_deposit_with_user(transaction_hash, user_id)
                if success:
                    transaction_info = await db.get_transaction_info(user_id)
                    if transaction_info:
                        transaction_hash = transaction_info['transaction_hash']
                        amount_received = transaction_info['amount_received']
                        await db.update_payment_info_with_hash(user_id, transaction_hash)
                        expected_ccy = await db.get_expected_currency(transaction_hash)
                        if expected_ccy is None:
                            await message.answer("Expected currency not found for your payment.")
                            await state.clear()
                            return
                        if expected_ccy != deposit_ccy:
                            await message.answer(f"Currency mismatch! Expected {expected_ccy}, but received {deposit_ccy}.")
                            await state.clear()
                            return
                        # Теперь можем вызвать функцию для проверки оплаты
                        await db.check_payment(transaction_hash, amount_received)
                    else:
                        await message.answer("Transaction information not found.")
                        await state.clear()
                else:
                    print("An error occurred while linking the transaction.")
                    await state.clear()
                await state.clear()  # Завершаем состояние ожидания

            elif status == 'pending':
                await message.answer("Transaction in process. Please wait.")
            elif status == 'not_found':
                await message.answer("Can't get info about your transaction hash. Contact the Admin.")
                await state.clear()
        else:
            await message.answer("Can't find this deposit.")
            await state.clear()
    else:
        await message.answer("Invalid transaction hash. Try again.")
        await state.clear()


@dp.callback_query(F.data =='paymentLTC')
async def LTCpay_on_month(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f"<b>Payment method:</b> 🌎 Crypto: Litecoin(LTC) \n Your ID:<b> {user_id} </b>, Cost: <b> 6$ </b> \n To make a right deposit, you need to follow a few steps: \n 1. Press the button <b> 'Start payment' </b> \n 2. Copy amount of cryptocurrency. ⚠️<b> WARNING! </b> (You need to send EXACT amount or MORE. Be aware of fees. If you deposit via <b>wallet</b>, it's gonna be fee so be attentive! If you deposit via <b>exchange</b>, check the amount you are sending!) \n 3. Copy address and send funds to it. \n 4. Once your transaction completed, simply press button <b> 'I paid' </b> and write your transaction hash. \n ⚠️ Deposit via LTC can take around 25-30 minutes. Try to enter you transaction hash after this time.\n You will have 45 minutes to do this steps. \n IF something goes wrong, don't worry, just write me DM, i will help you ASAP. \n https://t.me/actuallydone" , parse_mode="HTML", reply_markup=kb.LTCpay)

@dp.callback_query(F.data =='cryptopayLTC')
async def LTCpay(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    fiat_amount = 6
    crypto_rate = await get_crypto_rate('LTC')
     # Инициация оплаты
    crypto_amount, payment_window_end = await db.initiate_paymentLTC(user_id, fiat_amount, crypto_rate, transaction_hash="")
    await callback.message.answer(
        f"<b>Payment method</b>: 🌎 Crypto: Litecoin (LTC)\n"
        f"Your ID: <b>{user_id} </b>\n"
        f"Cost: {fiat_amount}$\n"
        f"<b>Address for payment:</b><pre>MPaZJcoVdhUeNerRaYKVkcLgxpNwjQPhif</pre>\n"
        f"<b>Crypto amount(LTC)</b>: <pre>{crypto_amount:.8f}</pre>\n"
        f"Payment window ends: {payment_window_end.strftime('%H:%M:%S')} (<b>UTC</b>) (in 45 minutes)\n ", 
        parse_mode="HTML", reply_markup= kb.cryptopay_exit
    )

@dp.callback_query(F.data == 'cryptopaybutton')
async def Ipaidbutton(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Checking the transaction...')
    await state.set_state(TransactionState.waiting_for_hash_LTC)
    await callback.message.answer("Enter your transaction hash.")
    


@dp.message(StateFilter(TransactionState.waiting_for_hash_LTC))
async def process_transaction_hash(message: Message, state: FSMContext):
    transaction_hash = message.text
    user_id = message.from_user.id

    if len(transaction_hash) == 64 or 66:  # Пример проверки длины хэша
        deposit_info = await db.find_matching_deposit(transaction_hash)
        
        if deposit_info:  # Проверяем, что информация о депозите получена
            status = deposit_info['status']
            deposit_ccy = deposit_info['ccy']  # Забираем ccy из ответа функции
            if status == 'completed':
                already_used = await db.get_user_id_by_transaction_hash(transaction_hash)
                if already_used is not None:
                    await message.answer("This hash has already been used.")
                    await state.clear()
                    return    
                success = await db.link_deposit_with_user(transaction_hash, user_id)
                if success:
                    transaction_info = await db.get_transaction_info(user_id)
                    if transaction_info:
                        transaction_hash = transaction_info['transaction_hash']
                        amount_received = transaction_info['amount_received']
                        await db.update_payment_info_with_hash(user_id, transaction_hash)
                        expected_ccy = await db.get_expected_currency(transaction_hash)
                        if expected_ccy is None:
                            await message.answer("Expected currency not found for your payment.")
                            await state.clear()
                            return
                        if expected_ccy != deposit_ccy:
                            await message.answer(f"Currency mismatch! Expected {expected_ccy}, but received {deposit_ccy}.")
                            await state.clear()
                            return
                        # Теперь можем вызвать функцию для проверки оплаты
                        await db.check_payment(transaction_hash, amount_received)
                    else:
                        await message.answer("Transaction information not found.")
                        await state.clear()
                else:
                    print("An error occurred while linking the transaction.")
                    await state.clear()
                await state.clear()  # Завершаем состояние ожидания

            elif status == 'pending':
                await message.answer("Transaction in process. Please wait.")
            elif status == 'not_found':
                await message.answer("Can't get info about your transaction hash. Contact the Admin.")
                await state.clear()
        else:
            await message.answer("Can't find this deposit.")
            await state.clear()
    else:
        await message.answer("Invalid transaction hash. Try again.")
        await state.clear()


@dp.callback_query(F.data =='paymentLTC(2)')
async def LTCpay_on_3months(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    await callback.message.edit_text(f"<b>Payment method:</b> 🌎 Crypto: Litecoin(LTC) \n Your ID:<b> {user_id} </b>, Cost:<b> 15$ </b>\n To make a right deposit, you need to follow a few steps: \n 1. Press the button <b> 'Start payment' </b> \n 2. Copy amount of cryptocurrency. WARNING! (You need to send EXACT amount or MORE. Be aware of fees. If you deposit via wallet, it's gonna be fee so be attentive! If you deposit via exchange, check the amount you are sending!) \n 3. Copy address and send funds to it. \n 4. Once your transaction completed, simply press button <b> 'I paid' </b> and write your transaction hash. \n You will have 45 minutes to do this steps. \n IF something goes wrong, don't worry, just write me DM, i will help you ASAP. \n https://t.me/actuallydone" , parse_mode="HTML", reply_markup=kb.LTCpay2)


@dp.callback_query(F.data =='cryptopayLTC(2)')
async def LTCpay2(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer('')
    fiat_amount = 15
    crypto_rate = await get_crypto_rate('LTC')
     # Инициация оплаты
    crypto_amount, payment_window_end = await db.initiate_paymentLTC(user_id, fiat_amount, crypto_rate, transaction_hash="")
    await callback.message.answer(
        f"<b>Payment method</b>: 🌎 Crypto: Litecoin (LTC)\n"
        f"Your ID: <b>{user_id} </b>\n"
        f"Cost: {fiat_amount}$\n"
        f"<b>Address for payment:</b><pre>MPaZJcoVdhUeNerRaYKVkcLgxpNwjQPhif</pre>\n"
        f"<b>Crypto amount(LTC)</b>: <pre>{crypto_amount:.8f}</pre>\n"
        f"Payment window ends: {payment_window_end.strftime('%H:%M:%S')} (<b>UTC</b>) (in 45 minutes)\n ", 
        parse_mode="HTML", reply_markup= kb.cryptopay_exit
    )

@dp.callback_query(F.data == 'cryptopaybutton')
async def Ipaidbutton(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Checking the transaction...')
    await state.set_state(TransactionState.waiting_for_hash_LTC)
    await callback.message.answer("Enter your transaction hash.")
    


@dp.message(StateFilter(TransactionState.waiting_for_hash_LTC))
async def process_transaction_hash(message: Message, state: FSMContext):
    transaction_hash = message.text
    user_id = message.from_user.id

    if len(transaction_hash) == 64 or 66:  # Пример проверки длины хэша
        deposit_info = await db.find_matching_deposit(transaction_hash)
        
        if deposit_info:  # Проверяем, что информация о депозите получена
            status = deposit_info['status']
            deposit_ccy = deposit_info['ccy']  # Забираем ccy из ответа функции
            if status == 'completed':
                already_used = await db.get_user_id_by_transaction_hash(transaction_hash)
                if already_used is not None:
                    await message.answer("This hash has already been used.")
                    await state.clear()
                    return    
                success = await db.link_deposit_with_user(transaction_hash, user_id)
                if success:
                    transaction_info = await db.get_transaction_info(user_id)
                    if transaction_info:
                        transaction_hash = transaction_info['transaction_hash']
                        amount_received = transaction_info['amount_received']
                        await db.update_payment_info_with_hash(user_id, transaction_hash)
                        expected_ccy = await db.get_expected_currency(transaction_hash)
                        if expected_ccy is None:
                            await message.answer("Expected currency not found for your payment.")
                            await state.clear()
                            return
                        if expected_ccy != deposit_ccy:
                            await message.answer(f"Currency mismatch! Expected {expected_ccy}, but received {deposit_ccy}.")
                            await state.clear()
                            return
                        # Теперь можем вызвать функцию для проверки оплаты
                        await db.check_payment(transaction_hash, amount_received)
                    else:
                        await message.answer("Transaction information not found.")
                        await state.clear()
                else:
                    print("An error occurred while linking the transaction.")
                    await state.clear()
                await state.clear()  # Завершаем состояние ожидания

            elif status == 'pending':
                await message.answer("Transaction in process. Please wait.")
            elif status == 'not_found':
                await message.answer("Can't get info about your transaction hash. Contact the Admin.")
                await state.clear()
        else:
            await message.answer("Can't find this deposit.")
            await state.clear()
    else:
        await message.answer("Invalid transaction hash. Try again.")
        await state.clear()




@dp.message(F.text =='My subscription ⏳')
async def cmd_subscription(message: types.Message): 
    user_id = message.from_user.id
    subscription = await db.get_subscription(user_id)
    
    if subscription:
        start_date, end_date = subscription
        start_date_formatted = start_date.strftime("%Y-%m-%d")
        end_date_formatted = end_date.strftime("%Y-%m-%d")  
        await message.answer(f"<b>🎉 You have an active subscription! 👑</b>\n\n"
                     f"🗓️ <b>Subscription is valid until:</b> {end_date_formatted}\n"
                     "⚡️ <i>Enjoy your premium content!</i>",
                     parse_mode="HTML")
    else:
        await message.answer("⏳ <b>No subscription found.</b> \n Take a look at the subscriptions you can buy on the button below 👇\n", parse_mode="HTML", reply_markup=kb.buyfromsubscription) 


@dp.callback_query(F.data =='buy from sub')
async def Paymentcrypto(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("Here you can find useful information about premium subscriptions that you are looking for. Welcome! ⭐️", reply_markup=kb.subscriptions)
    

@dp.callback_query(F.data =='back from payment')
async def Backfrompay(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("<b> Premium access on MONTH </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n - Interesting information about WWE superstars outside of the ring! \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 30 days \n <b> Price:</b> 6$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment1)

@dp.callback_query(F.data =='back from payment(2)')
async def Backfrompay(callback: CallbackQuery):
    await callback.answer('')
    await callback.message.edit_text("<b> Premium access on 3 MONTHS </b>😈 \n ☀️ <b>Welcome</b>. This premium subscription will give you access to : \n \n - Previous WWE shows in HIGH quality 📸📸\n \n - Get content FASTER than everyone 💫💫 \n \n - Exclusive interviews from WWE superstars 😈🔥 \n \n <b>And so much more! Join US!</b> \n \n <b> Duration:</b> 90 days \n <b> Price:</b> 15$ \n \n <b> Choose your payment method: </b> \n", parse_mode="HTML", reply_markup=kb.payment2)



@dp.callback_query(F.data == 'I paid')
async def Ipaidbutton(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Checking the transaction...')
    await state.set_state(TransactionState.waiting_for_hash)
    await callback.message.answer("Enter your transaction hash.")
    




@dp.message(StateFilter(TransactionState.waiting_for_hash))
async def process_transaction_hash(message: Message, state: FSMContext):
    transaction_hash = message.text
    user_id = message.from_user.id

    if len(transaction_hash) == 66:  # Пример проверки длины хэша
        deposit_info = await db.find_matching_deposit(transaction_hash)
        
        if deposit_info:  # Проверяем, что информация о депозите получена
            status = deposit_info['status']
            amount = deposit_info['amount']  # Проверяем состояние
            if status == 'completed':
                already_used = await db.get_user_id_by_transaction_hash(transaction_hash)
                if already_used is not None:
                    await message.answer("This hash has already been used.")
                    return    
                success = await db.link_deposit_with_user(transaction_hash, user_id)
                if success:
                    await db.provide_product(user_id, amount)  # Передаем amount
                else:
                    print("An error occurred while linking the transaction.")
                await state.clear()  # Завершаем состояние ожидания

            elif status == 'pending':
                await message.answer("Transaction in process. Please wait.")
            elif status == 'not_found':
                await message.answer("Can't get info about your transaction hash. Contact the Admin.")
                await state.clear()
        else:
            await message.answer("Can't find this deposit.")
            await state.clear()
    else:
        await message.answer("Invalid transaction hash. Try again.")
        await state.clear()



async def main():
    
    auth_subscribe_task = asyncio.create_task(authenticate_and_ping())
    
    bot_task = asyncio.create_task(dp.start_polling(bot))

    scheduler_task = asyncio.create_task(db.scheduler())

    await asyncio.gather(auth_subscribe_task, bot_task, scheduler_task)
  



if __name__ == "__main__":
    asyncio.run(main())

    
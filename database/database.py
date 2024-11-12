import main as m
import asyncio
from datetime import datetime, timedelta, timezone, time
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, DateTime, String, BigInteger, Float, ForeignKey
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import relationship
from dotenv import load_dotenv
import os

load_dotenv()


# Создание базы данных
DATABASE_URL = os.getenv("DATABASE_URL")
# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=True)
# Создаем асинхронную сессию
async_session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
# Создаем базовый класс для моделей
Base = declarative_base()

CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Модель для таблицы пользователей
class UserSubscription(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    subscription_start = Column(DateTime(timezone=True), nullable=False)
    subscription_end = Column(DateTime(timezone=True), nullable=False)



class PaymentInfo(Base):
    __tablename__ = 'pay_info'

    id = Column(Integer, primary_key=True, autoincrement=True)  # Уникальный ID платежа
    user_id = Column(BigInteger, nullable=False)  # ID пользователя
    crypto_amount = Column(Float, nullable=False)  # Сумма в криптовалюте
    crypto_rate = Column(Float, nullable=False)  # Курс криптовалюты на момент оплаты
    payment_window_end = Column(DateTime(timezone=True), nullable=False)  # Конец временного окна оплаты
    status = Column(String(20), nullable=False, default='pending')  # Статус платежа ('pending', 'completed')
    transaction_hash = Column(String(255), unique=True)
    ccy = Column(String)

    def __repr__(self):
        return f"<PaymentInfo(user_id={self.user_id}, crypto_amount={self.crypto_amount}, crypto_rate={self.crypto_rate}, status={self.status})>"

class Deposit(Base):
    __tablename__ = 'deposits'

    id = Column(Integer, primary_key=True, index=True)
    txId = Column(String(255), unique=True, index=True)  # txId как уникальный идентификатор
    amount = Column(Float)
    state = Column(Integer)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    user_id = Column(BigInteger, ForeignKey("user_track.user_id"), nullable=True)
    ccy = Column(String)

    user = relationship("UserTrack", back_populates="deposits")



class UserTrack(Base):
    __tablename__ = 'user_track'

    id = Column(Integer, primary_key=True, autoincrement=True)  # Уникальный идентификатор
    user_id = Column(BigInteger, unique=True, nullable=False) 

    deposits = relationship("Deposit", back_populates="user")


async def scheduler():
    while True:
        await remove_expired_users()
        await asyncio.sleep(21600)



# Asynchronous function to remove expired users
async def remove_expired_users():
    # Create a new async session
    async with async_session() as session:
        # Get current date and time
        current_time = datetime.now(timezone.utc)

        # Query the database for users whose subscription has expired
        result = await session.execute(
            select(UserSubscription).where(UserSubscription.subscription_end < current_time)
        )
        expired_users = result.scalars().all()

        # Loop through expired users and remove them from the channel
        for user in expired_users:
            try:
                print(f"Removing user {user.user_id} from the channel...")
                await m.bot.ban_chat_member(CHANNEL_ID, user.user_id)
                await m.bot.unban_chat_member(CHANNEL_ID, user.user_id)
                # Optionally, delete the user from the database after removal
                await session.delete(user)
                await session.commit()
            except Exception as e:
                print(f"Error removing user {user.user_id}: {e}")



# Функция для расчёта суммы в волатильной криптовалюте
async def calculate_crypto_amount(fiat_amount: float, crypto_rate: float) -> float:
    return fiat_amount / crypto_rate

# Инициация оплаты
async def initiate_paymentTON(user_id: BigInteger, fiat_amount: float, crypto_rate: float, transaction_hash: str):
    # Фиксируем курс и создаём окно времени
    crypto_amount = await calculate_crypto_amount(fiat_amount, crypto_rate)
    payment_window_end = datetime.now(timezone.utc) + timedelta(minutes=45)
    payment_window_end = payment_window_end.astimezone(timezone.utc)
    

    # Сохраняем информацию о платеже в базе данных
    async with async_session() as session:
        async with session.begin():
            payment_info = PaymentInfo(
                user_id=user_id,
                crypto_amount=crypto_amount,
                crypto_rate=crypto_rate,
                payment_window_end=payment_window_end,
                transaction_hash =transaction_hash,
                ccy="TON",
                status="pending"
                  # Статус ожидает оплаты
            )
            session.add(payment_info)
            await session.commit()
    return crypto_amount, payment_window_end

async def initiate_paymentLTC(user_id: BigInteger, fiat_amount: float, crypto_rate: float, transaction_hash: str):
    # Фиксируем курс и создаём окно времени
    crypto_amount = await calculate_crypto_amount(fiat_amount, crypto_rate)
    payment_window_end = datetime.now(timezone.utc) + timedelta(minutes=45)
    payment_window_end = payment_window_end.astimezone(timezone.utc)
    

    # Сохраняем информацию о платеже в базе данных
    async with async_session() as session:
        async with session.begin():
            payment_info = PaymentInfo(
                user_id=user_id,
                crypto_amount=crypto_amount,
                crypto_rate=crypto_rate,
                payment_window_end=payment_window_end,
                transaction_hash =transaction_hash,
                ccy="LTC",
                status="pending"
                  # Статус ожидает оплаты
            )
            session.add(payment_info)
            await session.commit()
    return crypto_amount, payment_window_end

# Проверка поступления оплаты
async def check_payment(transaction_hash: str, amount_received: float):
    async with async_session() as session:
        current_time = datetime.now(timezone.utc)
        # Ищем запись транзакции
        payment_info = await session.scalar(
            select(PaymentInfo)
            .where(PaymentInfo.transaction_hash == transaction_hash)
            .order_by(PaymentInfo.id.desc())  # Сортировка по id, чтобы взять последнюю запись
)
        if payment_info:
            # Приводим время из базы данных к UTC
            payment_window_end_utc = payment_info.payment_window_end.astimezone(timezone.utc)
            current_time = datetime.now(timezone.utc)
            print(f"Current UTC time: {current_time}")
            print(f"Payment window end time (converted to UTC): {payment_window_end_utc}")
            if datetime.now(timezone.utc) <= payment_window_end_utc:
                if amount_received >= payment_info.crypto_amount:
                    payment_info.status = "completed"  # Обновляем статус на завершён
                    await session.commit()
                    await provide_productCrypto(payment_info.user_id, amount_received, payment_info.crypto_rate)
                else:
                    await m.bot.send_message(payment_info.user_id, "Insufficient amount. Recheck withdrawal fees/amount.")
            else:
                await m.bot.send_message(payment_info.user_id, "The time for payment has expired. Try again/Contact the Admin.")
        else:
            await m.bot.send_message(payment_info.user_id, "No transaction found.")

async def get_transaction_info(user_id: int):
    async with async_session() as session:
        async with session.begin():
            deposit_info = await session.scalar(
                select(Deposit).where(Deposit.user_id == user_id)
                .order_by(Deposit.id.desc())
            )

            if deposit_info:
                return {
                    'transaction_hash': deposit_info.txId,  # Поле с хэшем транзакции
                    'amount_received': deposit_info.amount  # Поле с полученной суммой
                }
            else:
                return None

async def update_payment_info_with_hash(user_id: int, transaction_hash: str):
    async with async_session() as session:
        payment_info = await session.scalar(
            select(PaymentInfo).where(PaymentInfo.user_id == user_id)
            .order_by(PaymentInfo.id.desc())
        )
        if payment_info:
            payment_info.transaction_hash = transaction_hash
            await session.commit()


async def add_user(user_id):
    async with async_session() as session:
        async with session.begin():
            # Проверяем, существует ли уже запись с данным user_id
            existing_user = await session.execute(
                select(UserTrack).where(UserTrack.user_id == user_id)
            )
            existing_user = existing_user.scalar_one_or_none()

            if existing_user is None:
                # Если пользователя нет, добавляем нового
                new_user = UserTrack(user_id=user_id)
                session.add(new_user)
            else:
                print("User is already exists.")
        await session.commit()


async def find_matching_deposit(transaction_hash: str):
    async with async_session() as session:
        async with session.begin():
            deposits = await session.execute(
                select(Deposit).where(
                    Deposit.txId == transaction_hash,
                )
            )
            deposit = deposits.scalar_one_or_none()

            if deposit:
                if deposit.state == 2:  # Пример проверки состояния (2 - завершено)
                    print('Transaction completed')
                    return {
                        'status': 'completed',  # Возвращаем статус completed
                        'amount': deposit.amount,  # Возвращаем сумму транзакции
                        'ccy': deposit.ccy
                    }
                else:
                    print('Transaction pending')
                    return {
                        'status': 'pending',  # Возвращаем статус pending
                        'amount': deposit.amount, # Также возвращаем сумму, даже если pending
                        'ccy': deposit.ccy
                    }
            print("Transaction not found")
            return None


async def get_expected_currency(transaction_hash: str):
    async with async_session() as session:
        async with session.begin():
            # Получаем ожидаемую валюту для пользователя из базы данных
            result = await session.execute(
                select(PaymentInfo.ccy).where(PaymentInfo.transaction_hash == transaction_hash)
            )
            expected_ccy = result.scalar_one_or_none()

            if expected_ccy is None:
                print("Expected currency not found for this user")
                return None

            return expected_ccy


async def get_user_id_by_transaction_hash(transaction_hash: str):
    async with async_session() as session:
        async with session.begin():
            # Ищем запись депозита с данным transaction_hash
            deposit = await session.scalar(
                select(Deposit.user_id).where(Deposit.txId == transaction_hash)
            )
            return deposit

# Функция для обработки депозита
async def handle_deposit(transaction_hash: str, amount: float, state: int, timestamp: datetime, currency: str):
    async with async_session() as session:
        async with session.begin():
            # Попытка найти существующую запись с таким же txId
            deposit = await session.scalar(
                select(Deposit).where(Deposit.txId == transaction_hash)
            )
            
            if deposit:
                # Если запись уже существует, обновляем поля
                deposit.amount = amount
                deposit.state = state
                deposit.timestamp = timestamp
            else:
                # Если записи не существует, создаём новую
                deposit = Deposit(
                    txId=transaction_hash,
                    amount=amount,
                    state=state,
                    timestamp=timestamp,
                    ccy=currency
                )
                session.add(deposit)

        # Коммитим изменения
        await session.commit()

async def link_deposit_with_user(transaction_hash: str, user_id: int):
    async with async_session() as session:
        async with session.begin():
            deposit = await session.scalar(
                select(Deposit).where(Deposit.txId == str(transaction_hash))
            )
            
            if deposit:
                # Проверяем, связан ли уже этот transaction_hash с каким-либо user_id
                if deposit.user_id is not None:
                    print(f"Transaction hash {transaction_hash} уже связан с user_id {deposit.user_id}")
                    return False  # Возвращаем False, если transaction_hash уже связан с пользователем
                # Обновляем запись в таблице deposits, добавляя user_id
                deposit.user_id = user_id
                session.add(deposit)
                await session.commit()
                print(f"Deposit {transaction_hash} linked with user {user_id}")
                return True  # Транзакция успешно привязана
            else:
                print("Deposit not found")
                return False

async def cancel_payment(user_id: int):
    async with async_session() as session:
        async with session.begin():
            # Находим запись платежа по user_id
            payment_info = await session.scalar(
                select(PaymentInfo).where(PaymentInfo.user_id == user_id)
                .order_by(PaymentInfo.id.desc())
            )
            if payment_info:
                await session.delete(payment_info)  # Удаляем запись
                await session.commit()
            else:
                await m.bot.send_message(user_id, "No active payment found.")


async def provide_product(user_id: int, amount: float):
    subscription_prices = {
        1: 6,   # 1 месяц стоит 6$
        3: 15   # 3 месяца стоят 15$
    }

    # Определяем количество месяцев на основе суммы депозита
    months = 0
    for months_option, price in subscription_prices.items():
        if amount >= price:
            months = months_option

    if months == 0:
        await m.bot.send_message(user_id, "Insufficient amount to subscribe.")
        return
    # Логика предоставления продукта. Например, активация подписки.
    async with async_session() as session:
        user = await session.scalar(select(UserSubscription).where(UserSubscription.user_id == user_id))
        if not user:
            # Если пользователь ещё не имеет подписки, создаём новую запись
            new_subscription = UserSubscription(
                user_id=user_id,
                subscription_start=datetime.now(timezone.utc),
                subscription_end=datetime.now(timezone.utc) + timedelta(days=30 * months)  # Увеличиваем на количество месяцев
            )
            session.add(new_subscription)
        else:
            # Продлеваем подписку
            user.subscription_end += timedelta(days=30 * months)  # Увеличиваем на количество месяцев
        
        await session.commit()
    result = await m.bot.create_chat_invite_link(CHANNEL_ID, member_limit=1)
    await m.bot.send_message(user_id, f"Congratulations! Your subscription activated for {months} month(s). There is your link to the channel: {result.invite_link}. Enjoy😈🔥")

async def provide_productCrypto(user_id: int, amount: float, crypto_rate: float):
    # Определяем стоимость подписок в фиатной валюте
    subscription_prices = {
        1: 6,  # 1 месяц
        3: 15  # 3 месяца
    }
    
    # Определяем сколько криптовалюты нужно для каждой подписки
    subscription_costs_in_crypto = {months: price / crypto_rate for months, price in subscription_prices.items()}

    months = 0
    for months_option, crypto_price in subscription_costs_in_crypto.items():
        if amount >= crypto_price:
            months = months_option

    if months == 0:
        await m.bot.send_message(user_id, "Insufficient amount to subscribe.")
        return
    
    async with async_session() as session:
        user = await session.scalar(select(UserSubscription).where(UserSubscription.user_id == user_id))
        if not user:
            # Если пользователь ещё не имеет подписки, создаём новую запись
            new_subscription = UserSubscription(
                user_id=user_id,
                subscription_start=datetime.now(timezone.utc),
                subscription_end=datetime.now(timezone.utc) + timedelta(days=30 * months)  # Увеличиваем на количество месяцев
            )
            session.add(new_subscription)
        else:
            # Продлеваем подписку
            user.subscription_end += timedelta(days=30 * months)  # Увеличиваем на количество месяцев
        
        await session.commit()
    result = await m.bot.create_chat_invite_link(CHANNEL_ID, member_limit=1)
    await m.bot.send_message(user_id, f"Congratulations! Your subscription activated for {months} month(s). There is your link to the channel: {result.invite_link}. \n <i>Enjoy!</i>😈🔥")

async def some_async_function():
    # Асинхронный код
    pass

# Функция для добавления подписки пользователя
async def add_subscription(user_id: BigInteger, start_date: datetime, end_date: datetime):
    async with async_session() as session:
        async with session.begin():
            new_subscription = UserSubscription(
                user_id=user_id,
                subscription_start=start_date,
                subscription_end=end_date
            )
            session.add(new_subscription)
            await session.commit()
           

# Функция для получения подписки пользователя
async def get_subscription(user_id: BigInteger):
    async with async_session() as session:
        async with session.begin():
            try:
                query = text("SELECT subscription_start, subscription_end FROM users WHERE user_id = :user_id")
                result = await session.execute(query, {"user_id": user_id})
                subscription = result.first()
                
                if subscription:
                    return subscription
                else:
                    print("No subscription found.")
                    return None
            except Exception as e:
                print(f"Error during DB query execution: {e}")
                return None
                       
async def provide_productStars(user_id: int, months: int):
    # Логика предоставления продукта и активации подписки
    async with async_session() as session:
        user = await session.scalar(select(UserSubscription).where(UserSubscription.user_id == user_id))
        if not user:
            # Если пользователя нет в базе, создаём новую запись
            new_subscription = UserSubscription(
                user_id=user_id,
                subscription_start=datetime.now(timezone.utc),
                subscription_end=datetime.now(timezone.utc) + timedelta(days=30 * months)
            )
            session.add(new_subscription)
        else:
            # Продлеваем подписку
            user.subscription_end += timedelta(days=30 * months)

        await session.commit()

    result = await m.bot.create_chat_invite_link(CHANNEL_ID, member_limit=1)
    return f"Your subscription is active for {months} month(s). Here is your link: {result.invite_link}"



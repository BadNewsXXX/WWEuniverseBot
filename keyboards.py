from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

main = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Subscriptions 💵'),
                                      KeyboardButton(text='My subscription ⏳')],
                                     [KeyboardButton(text='Support ⚙️'),
                                      KeyboardButton(text='FAQ ❔')]],
                            resize_keyboard=True,
                            input_field_placeholder='Select menu item...')

subscriptions = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Premium access on month 💎', callback_data='prem on month')],
    [InlineKeyboardButton(text='Premium access on 3 months 💎', callback_data='prem on 3 months')]])

channels = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Public channel 💎', callback_data='public channel')],
    [InlineKeyboardButton(text='Private channel 💎', callback_data='private channel')]])

backtomenu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back to menu channels')]])


payment1 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🌎 Via telegram', callback_data='paymentTG')],
    [InlineKeyboardButton(text='🌎 Crypto: USDT(TRC20)', callback_data='paymentTRC20')],
    [InlineKeyboardButton(text='🌎 Crypto: Toncoin(TON)', callback_data='paymentTON')],
    [InlineKeyboardButton(text='🌎 Crypto: Litecoin(LTC)', callback_data='paymentLTC')],
    [InlineKeyboardButton(text='🌎 Telegram stars ⭐️', callback_data='TelegramStars')],
    [InlineKeyboardButton(text='🌎 Donation Alerts', callback_data='DonationAlerts')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back to menu')]])
payment2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🌎 Via telegram', callback_data='paymentTG')],
    [InlineKeyboardButton(text='🌎 Crypto: USDT(TRC20)', callback_data='paymentTRC20(2)')],
    [InlineKeyboardButton(text='🌎 Crypto: Toncoin(TON)', callback_data='paymentTON(2)')],
    [InlineKeyboardButton(text='🌎 Crypto: Litecoin(LTC)', callback_data='paymentLTC(2)')],
    [InlineKeyboardButton(text='🌎 Telegram stars ⭐️', callback_data='TelegramStars(2)')],
    [InlineKeyboardButton(text='🌎 Donation Alerts', callback_data='DonationAlerts(2)')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back to menu')]])


paymentbutton = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ I paid', callback_data='I paid')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment')]])
paymentbutton2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ I paid', callback_data='I paid')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment(2)')]])





buyfromsubscription = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅Buy premium', callback_data='buy from sub')]])

LTCpay = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='⏳ Start payment', callback_data='cryptopayLTC')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment')]])

LTCpay2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='⏳ Start payment', callback_data='cryptopayLTC(2)')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment(2)')]])

TONpay = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='⏳ Start payment', callback_data='cryptopayTON')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment')]])

TONpay2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='⏳ Start payment', callback_data='cryptopayTON(2)')],
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from payment(2)')]])

cryptopay_exit = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='✅ I paid', callback_data='cryptopaybutton')],
    [InlineKeyboardButton(text='❌Cancel payment', callback_data='cryptocancelpayment')]])

DA_donate = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from paymentDA')]])

DA_donate2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔙Back to menu', callback_data='back from paymentDA(2)')]])
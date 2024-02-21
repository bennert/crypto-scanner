""" Telegram handling module """
import time
import numpy as np

from dotenv import dotenv_values
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          PollAnswerHandler)
from file_handling import (file_exists, add_json, load_json, update_json, save_json,
                            FILENAMEMINQUOTEVOLUME, FILENAMEBASECOIN, FILENAMEPAIRLIST,
                            FILENAMEMINSTOCHRSI, FILENAMEBUYSIGNALSACTIVE)
from exchange_handling import (set_exchange, fetch_ticker, get_pair_list, retrieve_buy_signals,
                               prev_timefram_minute_list)

FILENAMESECRETS = "./secrets/.env"

CMD_START = "Start"
CMD_START_BUY_SIGNALS = "StartBuySignals"
CMD_STOP_BUY_SIGNALS = "StopBuySignals"
CMD_CHECK_STATUS = "CheckStatus"
CMD_DISPLAY_MIN_QUOTE_VOLUME = "DisplayMinQuoteVolume"
CMDPOLLMINQUOTEVOLUME = "PollMinQuoteVolume"
CMDDISPLAYBASECOIN = "DisplayBaseCoin"
CMDPOLLBASECOIN = "PollBaseCoin"
CMDDISPLAYPAIRLIST = "DisplayPairList"
CMDPOLLPAIRLIST = "PollPairList"
CMDUPDATEPAIRLIST = "UpdatePairList"
CMDDISPLAYMINSTOCHRSI = "DisplayMinStochRsi"
CMDPOLLMINSTOCHRSI = "PollMinStochRsi"

updating_pair_list = {}

def start_telegram_bot():
    """Start telegram bot"""
    if file_exists(FILENAMESECRETS):
        secrets = dotenv_values(FILENAMESECRETS)
        token = secrets["TELEGRAM_TOKEN_SCANNER"]
        application = Application.builder().token(token).build()
        for command, handler in command_dict.items():
            application.add_handler(CommandHandler(command, handler))
        application.add_handler(PollAnswerHandler(receive_poll_selection))
        application.run_polling(poll_interval=1.0, timeout=180)
    else:
        print(f"Missing secret file: {FILENAMESECRETS} with telegram token")

# Support methods
def get_job(job_queue, name):
    """Get job by name"""
    queuelist = job_queue.get_jobs_by_name(name=name)
    return queuelist[0].job if len(queuelist) > 0 else None

def split_with_numpy(array_list, chunk_size):
    """Split array with numpy"""
    indices = np.arange(chunk_size, len(array_list), chunk_size)
    return np.array_split(array_list, indices)

async def receive_poll_selection(update: Update, context: CallbackContext) -> None:
    """Receive poll selection"""
    # the bot can receive closed poll updates we don't care about
    answer = update.poll_answer
    poll_id = answer.poll_id
    chat_id = str(context.bot_data[poll_id]["chat_id"])
    try:
        questions = context.bot_data[poll_id]["questions"]
    # this means this poll answer update is from an old poll, we can't stop it then
    except KeyError:
        return
    poll = context.bot_data[poll_id]["poll"]
    if poll == CMDPOLLMINQUOTEVOLUME:
        update_json(FILENAMEMINQUOTEVOLUME, chat_id, questions[answer.option_ids[0]])
    elif poll == CMDPOLLBASECOIN:
        update_json(FILENAMEBASECOIN, chat_id, questions[answer.option_ids[0]])
    elif poll == CMDPOLLPAIRLIST:
        #To be updated to handle multiple poll answers
        valid_coin_pairs = []
        selected_options = answer.option_ids
        for question_id in selected_options:
            valid_coin_pairs.append(questions[question_id])
        add_json(FILENAMEPAIRLIST, chat_id, valid_coin_pairs)
    elif poll == CMDPOLLMINSTOCHRSI:
        update_json(FILENAMEMINSTOCHRSI, chat_id, questions[answer.option_ids[0]])
    quiz_data = context.bot_data[poll_id]
    await context.bot.stop_poll(quiz_data["chat_id"], quiz_data["message_id"])

def get_message_content(item):
    """Compose content of message"""
    message_content = ""
    previour_date_time = ""
    date_time = item["datetime"]
    if previour_date_time != date_time:
        previour_date_time = date_time
        message_content += f"Time: {date_time}\n======================\n"
    pair = item["pair"]
    close = item["close"]
    quote_volume_m = item["quote_volume_m"]
    change_day = item["change_day"]
    change_day_perc = item["change_day_perc"]
    bb_buy = item["bbBuy"]
    stoch_buy = item["stochBuy"]
    stoch_rsi_buy = item["stochRsiBuy"]
    rsi_buy = item["rsiBuy"]
    buy_signal_list = [
        "BB " if bb_buy else '',
        "StochRsi" if stoch_rsi_buy else '',
        "RSI" if rsi_buy else ''
    ]
    buy_signal_list = [x for x in buy_signal_list if x != '']
    buy_signal = ', '.join(buy_signal_list)
    signal_emoji = "\U0001F7E2" if bb_buy else "\U0001F534"
    high = item["high"]
    low = item["low"]
    bb_width = item["bbWidth"]
    stoch_k = item["stochK"]
    stoch_d = item["stochD"]
    stoch_rsi_d = item["stochRsiD"]
    stoch_rsi_k = item["stochRsiK"]
    rsi = item["rsi"]
    macd_value = item["macdValue"]
    macd_signal = item["macdSignal"]
    macd_diff = item["macdDiff"]
    message_content += \
        f"Pair: {pair} (Vol:{quote_volume_m:7.2f}M)\n" \
        f"Change day: {change_day:.2f} / {change_day_perc:.2f}%\n" + \
        f"{signal_emoji}<b>Buy signal: [{buy_signal}]</b>\n" \
        f"{'<b>' if stoch_buy else ''}" \
        f"Stoch D: {stoch_d:.2f} K: {stoch_k:.2f}\n" \
        f"{'</b>' if stoch_buy else ''}" \
        f"{'<b>' if stoch_rsi_buy else ''}" \
        f"StochRsi D: {stoch_rsi_d:.2f}% K: {stoch_rsi_k:.2f}%" \
        f"{'</b>' if stoch_rsi_buy else ''}\n" \
        f"{'<b>' if rsi_buy else ''}" \
        f"RSI: {rsi:.2f}%" \
        f"{'</b>' if rsi_buy else ''}\n" \
        f"MACD: {macd_value:.3f} Signal: {macd_signal:.3f} Histogram: {macd_diff:.3f}\n" \
        f"{'<b>' if bb_buy else ''}" \
        f"BB H/L/W: {high:.5f} / {low:.5f} / {bb_width:.2f}%" \
        f"{'</b>' if bb_buy else ''}\n" \
        f"Close: {close:.5f}\n\n"
    return message_content

async def retrieve_all_buy_signals(
        chat_id, timeframe_range, message, pair_list, min_stoch_rsi_value):
    """Retrieve all buy signals"""
    if chat_id not in prev_timefram_minute_list:
        prev_timefram_minute_list[chat_id] = dict([[x, ""] for x in timeframe_range])
    for timeframe_minute in prev_timefram_minute_list[chat_id]:
        buy_list = await retrieve_buy_signals(
            message, timeframe_minute, pair_list, min_stoch_rsi_value)
        if len(buy_list) > 0:
            await message.reply_text(
                f"<b><u>Buy signals ({timeframe_minute} minutes):</u></b>",
                parse_mode=ParseMode.HTML)
            for i in buy_list:
                await message.reply_text(
                    get_message_content(buy_list[i]),
                    parse_mode=ParseMode.HTML)

async def get_buy_signals(context: CallbackContext):
    """Get buy signals"""
    job = context.job
    message = job.data["message"]
    update = job.data["update"]
    chat_id = str(message.chat_id)
    min_stoch_rsi = load_json(FILENAMEMINSTOCHRSI)
    if chat_id not in min_stoch_rsi.keys():
        await poll_min_stockrsi(update, context)
    min_stoch_rsi_value = int(min_stoch_rsi[chat_id])
    timeframe_range = [3, 5]
    pair_list = load_json(FILENAMEPAIRLIST)
    await retrieve_all_buy_signals(
        chat_id, timeframe_range, message, pair_list, min_stoch_rsi_value)

async def generate_pair_list(context: CallbackContext):
    """Generate pair list"""
    msg = await context.job.data["message"].reply_text("Update Pair List")
    update = context.job.data["update"]
    chat_id = str(msg.chat_id)
    min_quote_volume = load_json(FILENAMEMINQUOTEVOLUME)
    if chat_id not in min_quote_volume.keys():
        await poll_min_quote_volume(update, context)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id not in base_coin.keys():
        await poll_base_coin(update, context)
    min_day_volume = int(min_quote_volume[chat_id])
    heading = \
        f"Get pair list with minimum day volume of {min_day_volume:10,d} {base_coin[chat_id]}\n"
    job_buy = get_job(context.application.job_queue, chat_id)
    if job_buy is not None:
        job_buy.pause()
    set_exchange("kucoin")
    valid_coin_pairs = await get_pair_list(base_coin[chat_id], min_day_volume, msg, heading)
    update_json(FILENAMEPAIRLIST, chat_id, valid_coin_pairs)

    await msg.edit_text("Pair List updated")
    updating_pair_list[chat_id] = False
    if job_buy is not None:
        job_buy.resume()


# Command methods
# pylint: disable=unused-argument
async def start(update: Update, context: CallbackContext):
    """Start"""
    set_exchange("kucoin")
    message = update.effective_message
    chat_id = str(update.effective_user.id)
    buy_signals_active = load_json(FILENAMEBUYSIGNALSACTIVE)
    buy_signals_active_chat_id = chat_id in buy_signals_active and \
        buy_signals_active[chat_id]
    menu_list = [
        (CMD_STOP_BUY_SIGNALS if buy_signals_active_chat_id else CMD_START_BUY_SIGNALS),
        CMD_CHECK_STATUS,
        CMD_DISPLAY_MIN_QUOTE_VOLUME,
        CMDDISPLAYBASECOIN,
        CMDDISPLAYPAIRLIST,
        CMDDISPLAYMINSTOCHRSI,
        CMDPOLLMINQUOTEVOLUME,
        CMDPOLLBASECOIN,
        CMDPOLLPAIRLIST,
        CMDUPDATEPAIRLIST,
        CMDPOLLMINSTOCHRSI
    ]
    keyboard = [[KeyboardButton("/" + menu_item)] for menu_item in menu_list]
    reply_markup = ReplyKeyboardMarkup(keyboard)
    await message.reply_text("Choose action:", reply_markup=reply_markup)

async def start_buy_signals(update: Update, context: CallbackContext):
    """Start buy signals"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    msg = await message.reply_text("Start Checking buy signals")
    job_queue = context.application.job_queue
    update_json(FILENAMEBUYSIGNALSACTIVE, chat_id, True)
    await start(update, context)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id not in base_coin.keys():
        await stop_buy_signals(update, context)
        await poll_base_coin(update, context)
        return
    min_quote_volume = load_json(FILENAMEMINQUOTEVOLUME)
    if chat_id not in min_quote_volume.keys():
        await stop_buy_signals(update, context)
        await poll_min_quote_volume(update, context)
        return
    min_day_volume = float(min_quote_volume[chat_id])/1000000
    pair_list = load_json(FILENAMEPAIRLIST)
    if chat_id not in pair_list.keys() or len(pair_list[chat_id]) == 0:
        data = context.user_data
        data["message"] = msg
        data["update"] = update
        job_queue.run_once(generate_pair_list,1 , data=data)
        updating_pair_list[chat_id] = True
    if chat_id in updating_pair_list and updating_pair_list[chat_id]:
        updating_text = "Updating pair list. Pleas wait till finished"
        while updating_pair_list[chat_id]:
            time.sleep(5)
            updating_text += "."
            msg.edit_text(updating_text)
    await msg.edit_text(
        "Checking buy signals of pairs:\n* " + ("\n* ".join(sorted(pair_list[chat_id]))) + \
        f"\nwith minimum day volume of {min_day_volume:7.0f}M {base_coin[chat_id]}")
    data = context.user_data
    data["update"] = update
    data["message"] = message
    data["bot"] = context.bot
    job_buy = get_job(job_queue, chat_id)
    if job_buy is None:
        job_queue.run_repeating(get_buy_signals, 60, data=data, name=chat_id)
    else:
        job_buy.resume()

async def stop_buy_signals(update: Update, context: CallbackContext):
    """Stop buy signals"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    update_json(FILENAMEBUYSIGNALSACTIVE, chat_id, False)
    await message.reply_text("Buy signals stopped")
    job_buy = get_job(context.application.job_queue, chat_id)
    if job_buy is not None:
        job_buy.pause()
    await start(update, context)

async def check_status(update: Update, context: CallbackContext):
    """Check status of scanner"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    buy_signals_active = load_json(FILENAMEBUYSIGNALSACTIVE)
    buy_signals_active_chat_id = chat_id in buy_signals_active and \
        buy_signals_active[chat_id]
    job_buy = get_job(context.application.job_queue, chat_id)
    if job_buy is None:
        if not buy_signals_active_chat_id:
            await stop_buy_signals(update, context)
        else:
            await start_buy_signals(update, context)
    await message.reply_text(
        "Scanner is " + ("" if buy_signals_active_chat_id else "NOT ") + "checking buy signals")

async def display_min_quote_volume(update: Update, context: CallbackContext) -> None:
    """Display minimum quote volume"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    min_quote_volume = load_json(FILENAMEMINQUOTEVOLUME)
    if chat_id in min_quote_volume.keys():
        await message.reply_text("Minimum Quote Volume: " + (min_quote_volume[chat_id]))
    else:
        await poll_min_quote_volume(update, context)

async def display_base_coin(update: Update, context: CallbackContext) -> None:
    """Display base coin"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id in base_coin.keys():
        await message.reply_text("Base coin: " + (base_coin[chat_id]))
    else:
        await poll_base_coin(update, context)

async def display_pair_list(update: Update, context: CallbackContext) -> None:
    """Display pair list"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id not in base_coin.keys():
        await poll_base_coin(update, context)
    pair_list = load_json(FILENAMEPAIRLIST)
    if chat_id not in pair_list.keys():
        await update_pair_list(update, context)
        await message.reply_text(
            f"First select pairs with /{CMDPOLLPAIRLIST} and click again on /{CMDDISPLAYPAIRLIST}")
    else:
        min_quote_volume = load_json(FILENAMEMINQUOTEVOLUME)
        min_day_volume = int(min_quote_volume[chat_id])
        pair_list_with_volume = []
        for coin_pair in pair_list[chat_id]:
            ticker = fetch_ticker(coin_pair)
            quote_volume = ticker["quoteVolume"]
            if quote_volume > min_day_volume:
                pair_list_with_volume.append(f"{quote_volume/1000000:7.2f}M => {coin_pair}")

        await message.reply_text("Pair list:\n* " + ("\n* ".join(sorted(pair_list_with_volume))))

async def display_min_stockrsi(update: Update, context: CallbackContext) -> None:
    """Display minimum stochrsi"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    min_stoch_rsi = load_json(FILENAMEMINSTOCHRSI)
    if chat_id in min_stoch_rsi.keys():
        await message.reply_text("Minimum StochRsi: " + (min_stoch_rsi[chat_id]))
    else:
        await poll_min_stockrsi(update, context)

async def poll_min_quote_volume(update: Update, context: CallbackContext) -> None:
    """"Poll minimum quote volume"""
    quote_volumes = [
        "500000000",
        "100000000",
        "50000000",
        "10000000"
    ]
    message = await context.bot.send_poll(
        update.effective_chat.id,
        "Select minimum quote volume", 
        quote_volumes,
        is_anonymous=False,
        allows_multiple_answers=False
    )
    payload = {# Save some info about the poll the bot_data for later use in receive_quiz_answer
        message.poll.id: {
            "poll": CMDPOLLMINQUOTEVOLUME,
            "questions": quote_volumes,
            "chat_id": update.effective_chat.id,
            "message_id": message.message_id,
            "answers": 0
        }
    }
    context.bot_data.update(payload)

async def poll_base_coin(update: Update, context: CallbackContext) -> None:
    """Poll base coin"""
    coins = [
        "BTC",
        "BUSD",
        "USDT"
    ]
    message = await context.bot.send_poll(
        update.effective_chat.id,
        "Select pairs to scan", 
        coins,
        is_anonymous=False,
        allows_multiple_answers=False
    )
    payload = {# Save some info about the poll the bot_data for later use in receive_quiz_answer
        message.poll.id: {
            "poll": CMDPOLLBASECOIN,
            "questions": coins,
            "chat_id": update.effective_chat.id,
            "message_id": message.message_id,
            "answers": 0
        }
    }
    context.bot_data.update(payload)

async def poll_pair_list(update: Update, context: CallbackContext) -> None:
    """Poll pair list"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id not in base_coin.keys():
        await poll_base_coin(update, context)
    pair_list = load_json(FILENAMEPAIRLIST)
    if chat_id not in pair_list.keys():
        await update_pair_list(update, context)
    else:
        question_list = split_with_numpy(pair_list[chat_id], 10)
        pair_list[chat_id].clear()
        save_json(FILENAMEPAIRLIST, pair_list)
        for questions in question_list:
            if len(questions) == 1:
                questions.append("End of List")
            message = await context.bot.send_poll(
                update.effective_chat.id,
                "Select pairs to scan", 
                questions.tolist(),
                is_anonymous=False,
                allows_multiple_answers=True
            )
            # Save some info about the poll the bot_data for later use in receive_quiz_answer
            payload = {
                message.poll.id: {
                    "poll": CMDPOLLPAIRLIST,
                    "questions": questions,
                    "chat_id": update.effective_chat.id,
                    "message_id": message.message_id,
                    "answers": 0
                }
            }
            context.bot_data.update(payload)

async def update_pair_list(update: Update, context: CallbackContext):
    """Update pair list"""
    message = update.message if update.callback_query is None else update.callback_query.message
    data = context.user_data
    data["message"] = message
    data["update"] = update
    context.application.job_queue.run_once(generate_pair_list, 1, data=data)
    updating_pair_list[str(message.chat_id)] = True

async def poll_min_stockrsi(update: Update, context: CallbackContext) -> None:
    """Poll minimum stochrsi"""
    min_values = ["5", "10", "15", "20"]
    message = await context.bot.send_poll(
        update.effective_chat.id,
        "Select bottom value of StochRsi", 
        min_values,
        is_anonymous=False,
        allows_multiple_answers=False
    )
    payload = {# Save some info about the poll the bot_data for later use in receive_quiz_answer
        message.poll.id: {
            "poll": CMDPOLLMINSTOCHRSI,
            "questions": min_values,
            "chat_id": update.effective_chat.id,
            "message_id": message.message_id,
            "answers": 0
        }
    }
    context.bot_data.update(payload)

command_dict = {
    CMD_START: start,
    CMD_START_BUY_SIGNALS: start_buy_signals,
    CMD_STOP_BUY_SIGNALS: stop_buy_signals,
    CMD_CHECK_STATUS: check_status,
    CMD_DISPLAY_MIN_QUOTE_VOLUME: display_min_quote_volume,
    CMDDISPLAYBASECOIN: display_base_coin,
    CMDDISPLAYPAIRLIST: display_pair_list,
    CMDDISPLAYMINSTOCHRSI: display_min_stockrsi,
    CMDPOLLMINQUOTEVOLUME: poll_min_quote_volume,
    CMDPOLLBASECOIN: poll_base_coin,
    CMDPOLLPAIRLIST : poll_pair_list,
    CMDUPDATEPAIRLIST: update_pair_list,
    CMDPOLLMINSTOCHRSI: poll_min_stockrsi
}

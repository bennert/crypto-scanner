"""Module to scan crypto markets"""
import json
import os
import time
from datetime import datetime
from dotenv import dotenv_values

import ccxt
import numpy as np
import pandas as pd
import pytz
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TimedOut
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          JobQueue, PollAnswerHandler)

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

exchange = ccxt.binance()
QueueJob = JobQueue
FILENAMEBUYSIGNALSACTIVE = "./state/buysignalsactive.json"
FILENAMEMINQUOTEVOLUME = "./state/minquotevol.json"
FILENAMEBASECOIN = "./state/basecoin.json"
FILENAMEPAIRLIST = "./state/pairlist.json"
dataList = {}
prev_timefram_minute_list = {}
updating_pair_list = {}
FILENAMEMINSTOCHRSI = "./state/minstochrsi.json"

# pylint: disable=consider-using-dict-items

def add_json(file_name, chat_id, value):
    """Add json value of chat_id to file"""
    json_dict = load_json(file_name)
    json_dict[chat_id] += value
    save_json(file_name, json_dict)

def update_json(file_name, chat_id, value):
    """Update json value of chat_id in file"""
    json_dict = load_json(file_name)
    json_dict[chat_id] = value
    save_json(file_name, json_dict)

def load_json(file_name):
    """Load json value of file"""
    value = {}
    if os.path.isfile(file_name):
        with open(file_name, 'r', encoding="utf-8") as file:
            value = json.load(file)
    return value

def save_json(file_name, json_value):
    """Save json string to file"""
    with open(file_name, 'w', encoding="utf-8") as file:
        json.dump(json_value, file)

async def generate_pair_list(context: CallbackContext):
    """Generate pair list"""
    # global updating_pair_list
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
    job_buy = get_job(chat_id)
    if job_buy is not None:
        job_buy.pause()
    exchange.load_markets()
    coin_pairs = [p for p in exchange.symbols \
        if '/' + base_coin[chat_id] in p and 'BUSD' not in p]
    valid_coin_pairs = []
    for coin_pair in coin_pairs:
        if exchange.markets[coin_pair]['active']:
            try:
                await msg.edit_text(f"{heading}Checking pair:\n{coin_pair}")
            except (TimedOut) as exception:
                print(f"Message with coin pair {coin_pair} got exception {exception}")
            ticker = exchange.fetch_ticker(coin_pair)
            if ticker["quoteVolume"] > min_day_volume:
                valid_coin_pairs.append(coin_pair)
    update_json(FILENAMEPAIRLIST, chat_id, valid_coin_pairs)

    await msg.edit_text("Pair List updated")
    updating_pair_list[chat_id] = False
    if job_buy is not None:
        job_buy.resume()

def copy_data(timeframe_minute, date_time):
    """Copy pair list data"""
    data = {}
    pair_list = load_json(FILENAMEPAIRLIST)
    for pair_from_list in dataList[timeframe_minute][date_time]:
        if pair_from_list in pair_list:
            data[pair_from_list] = dataList[timeframe_minute][date_time]
    return data

async def retrieve_buy_signals(message, timeframe_minute, min_stoch_rsi_value):
    """Retrieve buy signals"""
    chat_id = str(message.chat_id)
    timeframe_hour = 60 / timeframe_minute
    timeframe_day = int(24 * timeframe_hour)
    timeframe = str(timeframe_minute) + 'm'
    data = {}
    pair_list = load_json(FILENAMEPAIRLIST)
    for pair in pair_list[chat_id]:
        if len(data) > 0 and pair in data:
            continue
        bars = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=timeframe_day)
        data_frame = pd.DataFrame(
            bars[:-1], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        timestamp = int(data_frame["timestamp"].iloc[-1])/1000
        date_time = datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Amsterdam'))
        if len(data) == 0:
            if chat_id in prev_timefram_minute_list and \
                timeframe_minute in prev_timefram_minute_list[chat_id] and \
                date_time == prev_timefram_minute_list[chat_id][timeframe_minute]:
                break
            elif timeframe_minute in dataList and \
                date_time in dataList[timeframe_minute]:
                data = copy_data(timeframe_minute, date_time)
            prev_timefram_minute_list[chat_id][timeframe_minute] = date_time
        indicator_bb = BollingerBands(close=data_frame["close"], window=20, window_dev=2)
        indicator_stoch_rsi = StochRSIIndicator(
            close=data_frame["close"], window=14, smooth1=3, smooth2=3)
        indicator_rsi = RSIIndicator(close=data_frame["close"], window=14)
        indicator_macd = MACD(
            close=data_frame["close"], window_slow=26, window_fast=12, window_sign=9)

        openday = data_frame['open'].iloc[0]
        close = data_frame['close'].iloc[-1]
        change_day = close - openday
        change_day_perc = (change_day / openday) * 100
        # Add Bollinger Bands features
        data_frame['bb_bbm'] = indicator_bb.bollinger_mavg()
        data_frame['bb_bbh'] = indicator_bb.bollinger_hband()
        data_frame['bb_bbl'] = indicator_bb.bollinger_lband()
        data_frame['bb_width'] = (
            (data_frame['bb_bbh'] - data_frame['bb_bbl']) / data_frame['bb_bbm']) * 100
        # Add Bollinger Band high indicator
        data_frame['bb_bbhi'] = indicator_bb.bollinger_hband_indicator()
        # Add Bollinger Band low indicator
        data_frame['bb_bbli'] = indicator_bb.bollinger_lband_indicator()
        bb_buy = bool(data_frame['bb_bbli'].iloc[-1])
        bb_sell = bool(data_frame['bb_bbhi'].iloc[-1])

        data_frame['stochRsiD'] = indicator_stoch_rsi.stochrsi_d() * 100
        data_frame['stochRsiK'] = indicator_stoch_rsi.stochrsi_k() * 100
        stoch_rsi_max = 80
        stoch_rsi_min = min_stoch_rsi_value
        stoch_rsi_buy = \
            data_frame['stochRsiD'].iloc[-1] < stoch_rsi_min and \
            data_frame['stochRsiK'].iloc[-1] < stoch_rsi_min
        stoch_rsi_sell = \
            data_frame['stochRsiD'].iloc[-1] > stoch_rsi_max and \
            data_frame['stochRsiK'].iloc[-1] > stoch_rsi_max

        data_frame['rsi'] = indicator_rsi.rsi()
        rsi_max = 70
        rsi_min = 30
        rsi_buy = data_frame['rsi'].iloc[-1] < rsi_min
        rsi_sell = data_frame['rsi'].iloc[-1] > rsi_max

        data_frame['macdValue'] = indicator_macd.macd()
        data_frame['macdSignal'] = indicator_macd.macd_signal()
        data_frame['macdDiff'] = indicator_macd.macd_diff()

        data[pair] = {
            "pair": pair,
            "datetime": date_time, #df['timestamp'].iloc[-1],
            "close": data_frame['close'].iloc[-1],
            "change_day": change_day,
            "change_day_perc": change_day_perc,
            "high": data_frame['bb_bbh'].iloc[-1],
            "low": data_frame['bb_bbl'].iloc[-1],
            "bbWidth": data_frame['bb_width'].iloc[-1],
            "stochRsiD": data_frame['stochRsiD'].iloc[-1],
            "stochRsiK": data_frame['stochRsiK'].iloc[-1],
            "rsi": data_frame['rsi'].iloc[-1],
            "macdValue": data_frame['macdValue'].iloc[-1],
            "macdSignal": data_frame['macdSignal'].iloc[-1],
            "macdDiff": data_frame['macdDiff'].iloc[-1],
            "bbBuy": bb_buy,
            "stochRsiBuy": stoch_rsi_buy,
            "rsiBuy": rsi_buy,
            "bbSell": bb_sell,
            "stochRsiSell": stoch_rsi_sell,
            "rsiSell": rsi_sell
        }
    buy_list = {}
    for i in data:
        if bool(data[i]["bbBuy"]) and \
            bool(data[i]["stochRsiBuy"]):
            buy_list[i] = data[i]
    if len(buy_list) > 0:
        await message.reply_text(
            f"<b><u>Buy signals ({timeframe_minute} minutes):</u></b>", parse_mode=ParseMode.HTML)
        for i in buy_list:
            await message.reply_text(get_message_content(buy_list[i]), parse_mode=ParseMode.HTML)

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
    change_day = item["change_day"]
    change_day_perc = item["change_day_perc"]
    bb_buy = item["bbBuy"]
    stoch_rsi_buy = item["stochRsiBuy"]
    rsi_buy = item["rsiBuy"]
    buy_signal_list = [
        "BB " if bb_buy else '',
        "StochRsi" if stoch_rsi_buy else '',
        "RSI" if rsi_buy else ''
    ]
    buy_signal_list = [x for x in buy_signal_list if x != '']
    buy_signal = ', '.join(buy_signal_list)
    high = item["high"]
    low = item["low"]
    bb_width = item["bbWidth"]
    stoch_rsi_d = item["stochRsiD"]
    stoch_rsi_k = item["stochRsiK"]
    rsi = item["rsi"]
    macd_value = item["macdValue"]
    macd_signal = item["macdSignal"]
    macd_diff = item["macdDiff"]
    message_content += f"Pair: {pair}\nChange day: {change_day:.2f} / {change_day_perc:.2f}%\n" + \
        f"<b>Buy signal: [{buy_signal}]</b>\n" \
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
    timeframe_range = [1, 3, 5]
    if chat_id not in prev_timefram_minute_list.keys():
        prev_timefram_minute_list[chat_id] = dict([[x, ""] for x in timeframe_range])
    for timeframe_minute in prev_timefram_minute_list[chat_id]:
        await retrieve_buy_signals(message, timeframe_minute, min_stoch_rsi_value)

def get_job(name):
    """Get job by name"""
    queuelist = QueueJob.get_jobs_by_name(name=name)
    if len(queuelist) > 0:
        return queuelist[0].job
    else:
        return None

async def start_buy_signals(update: Update, context: CallbackContext):
    """Start buy signals"""
    # global pairList
    # global get_buy_signals_active
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    msg = await message.reply_text("Start Checking buy signals")
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
    min_day_volume = int(min_quote_volume[chat_id])
    pair_list = load_json(FILENAMEPAIRLIST)
    if chat_id not in pair_list.keys() or len(pair_list[chat_id]) == 0:
        data = context.user_data
        data["message"] = msg
        data["update"] = update
        QueueJob.run_once(generate_pair_list,1 , data=data)
        updating_pair_list[chat_id] = True
    if chat_id in updating_pair_list and updating_pair_list[chat_id]:
        updating_text = "Updating pair list. Pleas wait till finished"
        while updating_pair_list[chat_id]:
            time.sleep(5)
            updating_text += "."
            msg.edit_text(updating_text)
    await msg.edit_text(
        "Checking buy signals of pairs:\n* " + ("\n* ".join(sorted(pair_list[chat_id]))) + \
        f"\nwith minimum day volume of {min_day_volume:10,d} {base_coin[chat_id]}")
    data = context.user_data
    data["update"] = update
    data["message"] = message
    data["bot"] = context.bot
    job_buy = get_job(chat_id)
    if job_buy is None:
        QueueJob.run_repeating(get_buy_signals, 60, data=data, name=chat_id)
    else:
        job_buy.resume()

async def stop_buy_signals(update: Update, context: CallbackContext):
    """Stop buy signals"""
    # global get_buy_signals_active
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    update_json(FILENAMEBUYSIGNALSACTIVE, chat_id, False)
    await message.reply_text("Buy signals stopped")
    job_buy = get_job(chat_id)
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
    job_buy = get_job(chat_id)
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

async def poll_min_quote_volume(update: Update, context: CallbackContext) -> None:
    """"Poll minimum quote volume"""
    quote_volumes = [
        "500000000",
        "100000000",
        "50000000"
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

async def display_base_coin(update: Update, context: CallbackContext) -> None:
    """Display base coin"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    base_coin = load_json(FILENAMEBASECOIN)
    if chat_id in base_coin.keys():
        await message.reply_text("Base coin: " + (base_coin[chat_id]))
    else:
        await poll_base_coin(update, context)

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
        await message.reply_text(f"First select pairs with /{CMDPOLLPAIRLIST} and click again on /{CMDDISPLAYPAIRLIST}")
    else:
        await message.reply_text("Pair list:\n* " + ("\n* ".join(sorted(pair_list[chat_id]))))

def split_with_numpy(array_list, chunk_size):
    """Split array with numpy"""
    indices = np.arange(chunk_size, len(array_list), chunk_size)
    return np.array_split(array_list, indices)

async def poll_pair_list(update: Update, context: CallbackContext) -> None:
    """Poll pair list"""
    # global pairList
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


async def receive_poll_selection(update: Update, context: CallbackContext) -> None:
    """Receive poll selection"""
    # global base_coin
    # global pairList
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

async def update_pair_list(update: Update, context: CallbackContext):
    """Update pair list"""
    message = update.message if update.callback_query is None else update.callback_query.message
    data = context.user_data
    data["message"] = message
    data["update"] = update
    QueueJob.run_once(generate_pair_list, 1, data=data)
    updating_pair_list[str(message.chat_id)] = True

async def display_min_stockrsi(update: Update, context: CallbackContext) -> None:
    """Display minimum stochrsi"""
    message = update.message if update.callback_query is None else update.callback_query.message
    chat_id = str(message.chat_id)
    min_stoch_rsi = load_json(FILENAMEMINSTOCHRSI)
    if chat_id in min_stoch_rsi.keys():
        await message.reply_text("Minimum StochRsi: " + (min_stoch_rsi[chat_id]))
    else:
        await poll_min_stockrsi(update, context)

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

# pylint: disable=unused-argument
async def start(update: Update, context: CallbackContext):
    """Start"""
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
    # return get_buy_signals_active

def main():
    """"Main"""
    global QueueJob
    secrets = dotenv_values(".env")
    token = secrets["TELEGRAM_TOKEN_SCANNER"]
    application = Application.builder().token(token).build()
    QueueJob = application.job_queue
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
    for command in command_dict:
        application.add_handler(CommandHandler(command, command_dict[command]))
    application.add_handler(PollAnswerHandler(receive_poll_selection))
    application.run_polling(poll_interval=1.0, timeout=180)

if __name__ == '__main__':
    main()

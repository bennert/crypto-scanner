"""Exchange handling"""
from datetime import datetime
import ccxt
import pandas as pd
import pytz

from ta.momentum import RSIIndicator, StochRSIIndicator, StochasticOscillator
from ta.trend import MACD
from ta.volatility import BollingerBands
from telegram.error import TimedOut

dataList = {}
prev_timefram_minute_list = {}

exchange = None

def set_exchange(exchange_name):
    """Set exchange"""
    global exchange
    if exchange_name in ccxt.exchanges:
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class()
    else:
        exchange = ccxt.binance()

async def get_pair_list(base_coin, min_day_volume, message, heading):
    """Get pair list"""
    exchange.load_markets()
    coin_pairs = [p for p in exchange.symbols \
        if '/' + base_coin in p and 'BUSD' not in p]
    valid_coin_pairs = []
    for coin_pair in coin_pairs:
        if exchange.markets[coin_pair]['active']:
            try:
                await message.edit_text(f"{heading}Checking pair:\n{coin_pair}")
            except (TimedOut) as exception:
                print(f"Message with coin pair {coin_pair} got exception {exception}")
            ticker = exchange.fetch_ticker(coin_pair)
            if ticker["quoteVolume"] > min_day_volume:
                valid_coin_pairs.append(coin_pair)
    return valid_coin_pairs

def copy_data(pair_list, timeframe_minute, date_time):
    """Copy pair list data"""
    data = {}
    for pair_from_list in dataList[timeframe_minute][date_time]:
        if pair_from_list in pair_list:
            data[pair_from_list] = dataList[timeframe_minute][date_time]
    return data

async def retrieve_buy_signals(message, timeframe_minute, pair_list, min_stoch_rsi_value):
    """Retrieve buy signals"""
    chat_id = str(message.chat_id)
    timeframe_hour = 60 / timeframe_minute
    timeframe_day = int(24 * timeframe_hour)
    timeframe = str(timeframe_minute) + 'm'
    data = {}
    for pair in pair_list[chat_id]:
        if len(data) > 0 and pair in data:
            continue
        ticker = exchange.fetch_ticker(pair)
        quote_volume_m = ticker["quoteVolume"]/1000000

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
                data = copy_data(pair_list, timeframe_minute, date_time)
            prev_timefram_minute_list[chat_id][timeframe_minute] = date_time
        indicator_bb = BollingerBands(close=data_frame["close"], window=20, window_dev=2)
        indicator_stoch = StochasticOscillator(
            close=data_frame["close"], high=data_frame["high"], low=data_frame["low"], window=14,
            smooth_window=3)
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

        data_frame['stoch_signal'] = indicator_stoch.stoch_signal()
        data_frame['stoch'] = indicator_stoch.stoch()
        stoch_max = 80
        stoch_min = 20
        stoch_buy = \
            data_frame['stoch_signal'].iloc[-1] < stoch_min and \
            data_frame['stoch'].iloc[-1] < stoch_min
        stoch_sell = \
            data_frame['stoch_signal'].iloc[-1] > stoch_max and \
            data_frame['stoch'].iloc[-1] > stoch_max

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
            "quote_volume_m": quote_volume_m,
            "change_day": change_day,
            "change_day_perc": change_day_perc,
            "high": data_frame['bb_bbh'].iloc[-1],
            "low": data_frame['bb_bbl'].iloc[-1],
            "bbWidth": data_frame['bb_width'].iloc[-1],
            "stochD": data_frame['stoch_signal'].iloc[-1],
            "stochK": data_frame['stoch'].iloc[-1],
            "stochRsiD": data_frame['stochRsiD'].iloc[-1],
            "stochRsiK": data_frame['stochRsiK'].iloc[-1],
            "rsi": data_frame['rsi'].iloc[-1],
            "macdValue": data_frame['macdValue'].iloc[-1],
            "macdSignal": data_frame['macdSignal'].iloc[-1],
            "macdDiff": data_frame['macdDiff'].iloc[-1],
            "bbBuy": bb_buy,
            "stochBuy": stoch_buy,
            "stochRsiBuy": stoch_rsi_buy,
            "rsiBuy": rsi_buy,
            "bbSell": bb_sell,
            "stochSell": stoch_sell,
            "stochRsiSell": stoch_rsi_sell,
            "rsiSell": rsi_sell
        }

    buy_list = {
        i: data[i] for i in data if data[i]["bbBuy"] and data[i]["stochRsiBuy"]
    }
    return buy_list

def fetch_ticker(pair):
    """Fetch ticker"""
    return exchange.fetch_ticker(pair)

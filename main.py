import sys
import json
import time
import pandas as pd
import numpy as np
import datetime
import os
import logging
import ta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content

import v20
from oandapyV20 import API
from oandapyV20.contrib.factories import InstrumentsCandlesFactory
import oandapyV20.endpoints.instruments as instrument
import oandapyV20.endpoints.accounts as accounts

from ta.trend import MACD

from ta.volatility import   donchian_channel_hband, donchian_channel_lband

PERIOD="D"
dict_hf={}
params_hf = { "count": 50,"granularity": PERIOD}

logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
logging.root.setLevel(logging.DEBUG)


access_token = os.environ.get('OANDA_ACCESS_TOKEN')
client = API(access_token=access_token, environment="live",request_params={'timeout': 30})
api = v20.Context('api-fxtrade.oanda.com','443',token=access_token)
account_id = os.environ.get('OANDA_ACCOUNT_ID')
sendgrid_key = os.environ.get('SENDGRID_KEY')
sg = SendGridAPIClient(sendgrid_key)


def send_email(subject, content):

    try:   
       mail = Mail(from_email='dailymacd@test.com',
                subject=subject + "@" + str(datetime.datetime.today()), 
                to_emails= 'eric@leconte.me',
                plain_text_content=str(content))

       logging.info(str(content))
       response=sg.send(mail)

    except Exception as e:
       logging.error("error sending email:" + str(e))


def fetch_candles_from ( instr, params):
    return fetch_candles(instr, params)


def cnv(instr, params, df):
    candles  = fetch_candles_from(instr, params)
    
    for candle in candles:
       data_ = pd.Series(candle)
       df=df.append(data_, ignore_index=True)  

    return df


def build_df (instr, params, timeframe):
    
    dict={}
    dict=dict_hf
    if (instr not in dict):
        df = pd.DataFrame()
    else:
        df = dict[instr]
    
    df=cnv( instr, params, df) 
    dict[instr]= df
    return df


def fetch_candles(instr, params):

    for r in InstrumentsCandlesFactory(instrument=instr, params=params):

        logging.debug(r)
        client.request(r)
        resp = r.response.get('candles')
        candles=[]

        for candle in resp:
                candles.append( {
                    "time": candle.get('time')[0:19], 
                    "open": float(candle['mid']['o']),
                    "high": float(candle['mid']['h']),
                    "low": float(candle['mid']['l']),
                    "close": float(candle['mid']['c'])
                    # "volume": float(candle['volume'])
                    }       )
    
    logging.info("for fx_pair:" + instr + " returning " + str(len(candles)) + " candles")
    return candles


if __name__ == '__main__':

    r = accounts.AccountInstruments(accountID=account_id)
    resp = client.request(r)
    instruments = resp["instruments"]
    stats=""

    for inst in instruments:

        logging.info(inst["name"]  + ":"+ str(inst["pipLocation"]))
        df= build_df(inst["name"], params_hf, PERIOD)

        indicator_macd = MACD(close=df['close'], n_slow=21, n_fast=9, n_sign=8, fillna=False)
        indicator_donchian_h = donchian_channel_hband()
        indicator_donchian_l = donchian_channel_lband()
        
        df['macd_dif'] = indicator_macd.macd_diff()
        df['ema_short'] = df['open'].ewm(span=20,min_periods=0,adjust=False,ignore_na=False).mean()
        df['ema_long'] = df['open'].ewm(span=50,min_periods=0,adjust=False,ignore_na=False).mean()
        df['donchian_h'] = indicator_donchian_h
        df['donchian_l'] = indicator_donchian_l
        

        if df['close'].iloc[-1] <= df['donchian_h'].iloc[-1]:
            stats+="DC +++" + inst["name"]+"\n"

        if df['close'].iloc[-1] <= df['donchian_l'].iloc[-1]:
            stats+="DC ---" + inst["name"]+"\n"
            
        
        #if df['macd_dif'].iloc[-1]>0 and df['macd_dif'].iloc[-2]<0:
        #    stats+="MAC +++" + inst["name"]+"\n"
        #elif df['macd_dif'].iloc[-1]<0 and df['macd_dif'].iloc[-2]>0:
        #    stats+="MAC ---" + inst["name"]+"\n"

        #if (df['close'].iloc[-1]>df['ema_short'].iloc[-1] and df['close'].iloc[-2]<df['ema_short'].iloc[-2]):
        #    stats+="EMA +++ " + inst["name"] +"\n"
        #elif (df['close'].iloc[-1]<df['ema_short'].iloc[-1] and df['close'].iloc[-2]>df['ema_short'].iloc[-2]):
        #stats+="EMA --- " + inst["name"] +"\n"
    
        print(stats)
        time.sleep(5)

    send_email("daily macd", stats)
    print(stats)




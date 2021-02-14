import sys
import json
import time
import pandas as pd
import numpy as np
import datetime
import os
import logging
import ta
import requests


import v20
from oandapyV20 import API
from oandapyV20.contrib.factories import InstrumentsCandlesFactory
import oandapyV20.endpoints.instruments as instrument
import oandapyV20.endpoints.accounts as accounts

from ta.trend import MACD

from ta.volatility import  DonchianChannel

#mailgun settings
mailgun_key = os.environ.get('MAILGUN_KEY')
mailgun_sandbox= os.environ.get('MAILGUN_SANDBOX')
to_email= os.environ.get('MAILGUN_RECIPIENT')


PERIOD="D"
dict_hf={}
params_hf = { "count": 50,"granularity": PERIOD}

logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
logging.root.setLevel(logging.DEBUG)


access_token = os.environ.get('OANDA_ACCESS_TOKEN')
client = API(access_token=access_token, environment="live",request_params={'timeout': 30})
api = v20.Context('api-fxtrade.oanda.com','443',token=access_token)
account_id = os.environ.get('OANDA_ACCOUNT_ID')


def send_email(subject, content):
    try:
            request_url = 'https://api.mailgun.net/v2/{0}/messages'.format(mailgun_sandbox)
            request = requests.post(request_url, auth=('api', mailgun_key), data={
                'from': 'dailymacd@test.com',
                'to': to_email,
                'subject':subject + "@" + str(datetime.datetime.today()),
                'text': str(content)
            })

            print ('Status: {0}'.format(request.status_code))
            print ('Body:   {0}'.format(request.text))
    except Exception as e:
        print('An error occurred: ',e)



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
    statsdc=""
    statsema=""
    statsminmax=""

    for inst in instruments:

        logging.info(inst["name"]  + ":"+ str(inst["pipLocation"]))
        df= build_df(inst["name"], params_hf, PERIOD)

        indicator_macd = MACD(close=df['close'], n_slow=21, n_fast=9, n_sign=8, fillna=False)
        indicator_dc = DonchianChannel(high=df['high'], low=df['low'], close=df['close'], n=20, offset=0, fillna=False)
        indicator_donchian_h = indicator_dc.donchian_channel_hband()
        indicator_donchian_l = indicator_dc.donchian_channel_lband()
        
        df['macd_dif'] = indicator_macd.macd_diff()
        df['ema_short'] = df['open'].ewm(span=100,min_periods=0,adjust=False,ignore_na=False).mean()
        df['ema_long'] = df['open'].ewm(span=100,min_periods=0,adjust=False,ignore_na=False).mean()
        df['donchian_h'] = indicator_donchian_h
        df['donchian_l'] = indicator_donchian_l

        df['ewm10'] = df['close'].ewm(span=10,min_periods=0,adjust=False,ignore_na=False).mean()
        df['ewm20'] = df['close'].ewm(span=20,min_periods=0,adjust=False,ignore_na=False).mean()
        df['ewm50'] = df['close'].ewm(span=50,min_periods=0,adjust=False,ignore_na=False).mean()

        df['max20'] = df['close'].rolling(20).max()
        df['min20'] = df['close'].rolling(20).min()
        print(df)
        
        if (df['max20'].iloc[-1]<= df['close'].iloc[-1]) and (df['max20'].iloc[-1]> df['close'].iloc[-2]):
            statsminmax+=" MAX BREAKOUT: "+inst["name"]+"\n"

        if (df['min20'].iloc[-1]>= df['close'].iloc[-1]) and (df['min20'].iloc[-1]< df['close'].iloc[-2])  :
            statsminmax+=" MIN BREAKOUT: "+inst["name"]+"\n"

        if ( (df['ewm10'].iloc[-1] < df['ewm20'].iloc[-1] ) and ( df['ewm20'].iloc[-1] < df['ewm50'].iloc[-1] )) \
        and (  df['ewm10'].iloc[-2] > df['ewm20'].iloc[-2] or df['ewm20'].iloc[-2] > df['ewm50'].iloc[-2]):       
            statsema+=("DOWN TREND: "+inst["name"])+"\n"

        if (( df['ewm10'].iloc[-1] > df['ewm20'].iloc[-1] ) and ( df['ewm20'].iloc[-1] > df['ewm50'].iloc[-1] )) \
        and (  df['ewm10'].iloc[-2] < df['ewm20'].iloc[-2] or df['ewm20'].iloc[-2] < df['ewm50'].iloc[-2]):       
            statsema+=("UP TREND: "+ inst["name"])+"\n"

        if df['close'].iloc[-1] >= df['donchian_h'].iloc[-1]:
            statsdc+="DC +++" + inst["name"]+"\n"

        if df['close'].iloc[-1] <= df['donchian_l'].iloc[-1]:
            statsdc+="DC ---" + inst["name"]+"\n"

    
        print(statsema)
        print(statsdc)
        print(statsminmax)
        time.sleep(5)

    send_email("daily macd dc", statsdc)
    send_email("daily macd trend", statsema)
    send_email("daily macd minmax", statsminmax)
    

    



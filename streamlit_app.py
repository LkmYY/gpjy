import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import yfinance as yf
import ta
import tushare as ts
from news.news_analyzer import NewsAnalyzer
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
from PIL import Image
import plotly.io as pio
import os
import sys
import requests
import time

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategy.strategy_analyzer import StrategyAnalyzer
import baostock as bs

def get_realtime_data(symbol, market_type):
    """
    获取盘中实时数据
    
    Args:
        symbol (str): 股票代码
        market_type (str): 市场类型
        
    Returns:
        dict: 实时数据
    """
    try:
        if market_type == "A股":
            # 添加市场后缀
            if symbol.startswith('6'):
                full_symbol = f"{symbol}.SH"
            else:
                full_symbol = f"{symbol}.SZ"
                
            # 使用tushare获取实时数据
            ts.set_token('1eff01596da7f92d7af202478e924ea7836ee40f52cf0636bc01f489')
            pro = ts.pro_api()
            
            # 获取当日实时行情
            try:
                # 尝试使用tushare的实时行情接口
                realtime = ts.get_realtime_quotes(symbol)
                
                if realtime is None or realtime.empty:
                    # 尝试使用baostock获取
                    bs.login()
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    rs = bs.query_history_k_data_plus(
                        full_symbol,
                        "date,time,open,high,low,close,volume,amount",
                        start_date=today_str,
                        end_date=today_str,
                        frequency="5"  # 5分钟线
                    )
                    
                    if rs.error_code != '0':
                        st.warning(f"获取实时数据失败: {rs.error_msg}")
                        bs.logout()
                        return None
                    
                    data_list = []
                    while (rs.next()):
                        data_list.append(rs.get_row_data())
                    
                    bs.logout()
                    
                    if not data_list:
                        st.warning("今日无交易数据")
                        return None
                    
                    # 获取最新的5分钟数据
                    latest = data_list[-1]
                    return {
                        'open': float(latest[2]),
                        'high': float(latest[3]),
                        'low': float(latest[4]),
                        'price': float(latest[5]),  # 收盘价作为当前价格
                        'pre_close': None,  # baostock不提供前收盘价
                        'volume': float(latest[6]),
                        'amount': float(latest[7]),
                        'time': f"{latest[0]} {latest[1]}"
                    }
                
                # 转换tushare数据格式
                return {
                    'open': float(realtime['open'].iloc[0]),
                    'high': float(realtime['high'].iloc[0]),
                    'low': float(realtime['low'].iloc[0]),
                    'price': float(realtime['price'].iloc[0]),
                    'pre_close': float(realtime['pre_close'].iloc[0]),
                    'volume': float(realtime['volume'].iloc[0]) * 100,  # 转换为股
                    'amount': float(realtime['amount'].iloc[0]) * 10000,  # 转换为元
                    'time': realtime['date'].iloc[0] + ' ' + realtime['time'].iloc[0]
                }
            except Exception as e:
                st.warning(f"获取A股实时数据时出错: {str(e)}，尝试其他方法")
                
                # 尝试使用日线数据的最新记录
                today_str = datetime.now().strftime('%Y%m%d')
                df = pro.daily(ts_code=full_symbol, start_date=today_str, end_date=today_str)
                
                if df is not None and not df.empty:
                    return {
                        'open': float(df['open'].iloc[0]),
                        'high': float(df['high'].iloc[0]),
                        'low': float(df['low'].iloc[0]),
                        'price': float(df['close'].iloc[0]),
                        'pre_close': float(df['pre_close'].iloc[0]) if 'pre_close' in df.columns else None,
                        'volume': float(df['vol'].iloc[0]),
                        'amount': float(df['amount'].iloc[0]),
                        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                return None
                
        elif market_type == "港股":
            # 添加港股后缀
            full_symbol = f"{symbol}.HK"
            
            # 使用yfinance获取实时数据
            try:
                stock = yf.Ticker(full_symbol)
                today_data = stock.history(period='1d')
                
                if today_data.empty:
                    return None
                
                latest = today_data.iloc[-1]
                
                return {
                    'open': float(latest['Open']),
                    'high': float(latest['High']),
                    'low': float(latest['Low']),
                    'price': float(latest['Close']),
                    'pre_close': None,  # yfinance不直接提供前收盘价
                    'volume': float(latest['Volume']),
                    'amount': float(latest['Volume'] * latest['Close']),  # 估算成交额
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            except Exception as e:
                st.warning(f"获取港股实时数据时出错: {str(e)}")
                return None
                
        else:  # 美股
            # 使用yfinance获取实时数据
            try:
                stock = yf.Ticker(symbol)
                today_data = stock.history(period='1d')
                
                if today_data.empty:
                    return None
                
                latest = today_data.iloc[-1]
                
                return {
                    'open': float(latest['Open']),
                    'high': float(latest['High']),
                    'low': float(latest['Low']),
                    'price': float(latest['Close']),
                    'pre_close': None,  # yfinance不直接提供前收盘价
                    'volume': float(latest['Volume']),
                    'amount': float(latest['Volume'] * latest['Close']),  # 估算成交额
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            except Exception as e:
                st.warning(f"获取美股实时数据时出错: {str(e)}")
                return None
    except Exception as e:
        st.error(f"获取实时数据时出错: {str(e)}")
        return None

def analyze_intraday_trend(realtime_data, historical_df):
    """
    分析盘中趋势
    
    Args:
        realtime_data (dict): 实时数据
        historical_df (pd.DataFrame): 历史数据
        
    Returns:
        dict: 趋势分析结果
    """
    try:
        # 默认结果
        result = {
            'trend': '无法分析',
            'reason': '数据不足',
            'prediction': '无法预测',
            'price_change_pct': 0,
            'amplitude': 0,
            'relative_volume': 0
        }
        
        # 检查数据有效性
        if not realtime_data or historical_df is None or historical_df.empty:
            return result
            
        # 计算价格变化百分比
        if 'pre_close' in realtime_data and realtime_data['pre_close']:
            price_change_pct = (realtime_data['price'] - realtime_data['pre_close']) / realtime_data['pre_close'] * 100
        else:
            # 如果没有前收盘价，使用昨日收盘价
            price_change_pct = (realtime_data['price'] - historical_df['Close'].iloc[-1]) / historical_df['Close'].iloc[-1] * 100
            
        # 计算振幅
        amplitude = (realtime_data['high'] - realtime_data['low']) / realtime_data['low'] * 100
        
        # 计算相对成交量（与5日平均成交量相比）
        avg_volume = historical_df['Volume'].tail(5).mean()
        relative_volume = realtime_data['volume'] / avg_volume if avg_volume > 0 else 0
        
        # 更新结果
        result['price_change_pct'] = price_change_pct
        result['amplitude'] = amplitude
        result['relative_volume'] = relative_volume
        
        # 分析趋势
        if price_change_pct > 3:
            result['trend'] = '强势上涨'
            if relative_volume > 1.5:
                result['reason'] = '价格大幅上涨，成交量放大，表明买盘积极'
                result['prediction'] = '短期内可能继续上涨，但注意回调风险'
            else:
                result['reason'] = '价格上涨但成交量不足，上涨动能不足'
                result['prediction'] = '可能面临回调风险，建议谨慎'
        elif price_change_pct > 1:
            result['trend'] = '温和上涨'
            result['reason'] = '价格小幅上涨，市场情绪偏向乐观'
            result['prediction'] = '可能继续温和上涨，关注成交量变化'
        elif price_change_pct < -3:
            result['trend'] = '强势下跌'
            if relative_volume > 1.5:
                result['reason'] = '价格大幅下跌，成交量放大，表明卖盘积极'
                result['prediction'] = '短期内可能继续下跌，等待企稳信号'
            else:
                result['reason'] = '价格下跌但成交量不足，下跌动能有限'
                result['prediction'] = '可能即将企稳，关注支撑位表现'
        elif price_change_pct < -1:
            result['trend'] = '温和下跌'
            result['reason'] = '价格小幅下跌，市场情绪偏向谨慎'
            result['prediction'] = '可能继续温和下跌，关注支撑位'
        else:
            result['trend'] = '盘整'
            result['reason'] = '价格变动不大，市场处于观望状态'
            result['prediction'] = '短期内可能继续盘整，等待方向性突破'
            
        # 考虑均线位置
        if 'MA5' in historical_df.columns and 'MA10' in historical_df.columns and 'MA20' in historical_df.columns:
            ma5 = historical_df['MA5'].iloc[-1]
            ma10 = historical_df['MA10'].iloc[-1]
            ma20 = historical_df['MA20'].iloc[-1]
            
            # 多头排列：MA5 > MA10 > MA20
            if ma5 > ma10 > ma20:
                result['reason'] += '，均线呈多头排列，中期趋势向上'
                if realtime_data['price'] > ma5:
                    result['prediction'] += '，价格站上所有均线，上升趋势强劲'
                elif realtime_data['price'] < ma20:
                    result['prediction'] += '，价格跌破MA20，可能是调整信号'
            # 空头排列：MA5 < MA10 < MA20
            elif ma5 < ma10 < ma20:
                result['reason'] += '，均线呈空头排列，中期趋势向下'
                if realtime_data['price'] < ma5:
                    result['prediction'] += '，价格跌破所有均线，下降趋势明显'
                elif realtime_data['price'] > ma20:
                    result['prediction'] += '，价格站上MA20，可能是反弹信号'
            else:
                result['reason'] += '，均线交叉，趋势不明确'
                
        return result
    except Exception as e:
        return {
            'trend': '分析出错',
            'reason': f'分析过程出错: {str(e)}',
            'prediction': '无法预测',
            'price_change_pct': 0,
            'amplitude': 0,
            'relative_volume': 0
        }

def format_price(price, market_type):
    """
    根据市场类型格式化价格显示
    
    Args:
        price (float): 价格
        market_type (str): 市场类型
        
    Returns:
        str: 格式化后的价格字符串
    """
    if price is None:
        return "N/A"
        
    if market_type == "A股":
        return f"¥{price:.2f}"
    elif market_type == "港股":
        return f"HK${price:.2f}"
    else:  # 美股
        return f"${price:.2f}"

def get_a_stock_data(symbol, start, end):
    """
    获取A股数据
    
    Args:
        symbol (str): 股票代码
        start (datetime): 开始日期
        end (datetime): 结束日期
        
    Returns:
        pd.DataFrame: 股票数据
    """
    try:
        # 初始化tushare
        ts.set_token('1eff01596da7f92d7af202478e924ea7836ee40f52cf0636bc01f489')  # 需要替换为实际的token
        pro = ts.pro_api()
        
        # 获取数据
        df = pro.daily(ts_code=symbol, 
                      start_date=start.strftime('%Y%m%d'),
                      end_date=end.strftime('%Y%m%d'))
        
        if df.empty:
            st.error(f"无法获取股票 {symbol} 的数据，请检查股票代码是否正确")
            return None
            
        # 重命名列
        df = df.rename(columns={
            'trade_date': 'date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'vol': 'Volume',
            'amount': 'Amount'
        })
        
        # 转换日期格式
        df['date'] = pd.to_datetime(df['date'])
        
        # 按日期升序排序
        df = df.sort_values('date')
        
        return df
    except Exception as e:
        st.error(f"获取A股数据时出错: {str(e)}")
        return None

def get_hk_stock_data(symbol, start, end):
    """
    获取港股数据
    
    Args:
        symbol (str): 股票代码
        start (datetime): 开始日期
        end (datetime): 结束日期
        
    Returns:
        pd.DataFrame: 股票数据
    """
    try:
        # 初始化tushare
        ts.set_token('1eff01596da7f92d7af202478e924ea7836ee40f52cf0636bc01f489')
        pro = ts.pro_api()
        
        # 获取数据
        df = pro.hk_daily(ts_code=symbol, 
                         start_date=start.strftime('%Y%m%d'),
                         end_date=end.strftime('%Y%m%d'))
        
        if df.empty:
            st.error(f"无法获取港股 {symbol} 的数据，请检查股票代码是否正确")
            return None
            
        # 重命名列
        df = df.rename(columns={
            'trade_date': 'date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'vol': 'Volume',
            'amount': 'Amount'
        })
        
        # 转换日期格式
        df['date'] = pd.to_datetime(df['date'])
        
        # 按日期升序排序
        df = df.sort_values('date')
        
        return df
    except Exception as e:
        st.error(f"获取港股数据时出错: {str(e)}")
        return None

@st.cache_data
def get_stock_data(symbol, start, end, market_type):
    """
    获取股票数据
    
    Args:
        symbol (str): 股票代码
        start (datetime): 开始日期
        end (datetime): 结束日期
        market_type (str): 市场类型
        
    Returns:
        pd.DataFrame: 股票数据
    """
    try:
        if market_type == "A股":
            # A股逻辑保持不变
            if symbol.startswith('6'):
                symbol = f"{symbol}.SH"
            else:
                symbol = f"{symbol}.SZ"
            return get_a_stock_data(symbol, start, end)
        elif market_type == "港股":
            # 港股逻辑保持不变
            symbol = f"{symbol}.HK"
            return get_hk_stock_data(symbol, start, end)
        else:
            # 美股数据获取添加重试机制
            max_retries = 3
            retry_delay = 2  # 秒
            
            for attempt in range(max_retries):
                try:
                    stock = yf.Ticker(symbol)
                    df = stock.history(start=start, end=end, interval="1d")
                    
                    if df.empty:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        st.error(f"无法获取股票 {symbol} 的数据，请检查股票代码是否正确")
                        return None
                    
                    # 重置索引，将日期作为列
                    df = df.reset_index()
                    df = df.rename(columns={'Date': 'date'})
                    
                    return df
                    
                except requests.exceptions.HTTPError as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        st.warning(f"请求频率限制，正在重试... ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay * (attempt + 1))  # 指数退避
                        continue
                    raise
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        st.warning(f"获取数据出错，正在重试... ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    raise
                    
            st.error(f"在 {max_retries} 次尝试后仍无法获取股票数据")
            return None
            
    except Exception as e:
        st.error(f"获取股票数据时出错: {str(e)}")
        return None

def calculate_indicators(df):
    """
    计算技术指标
    
    Args:
        df (pd.DataFrame): 股票数据
        
    Returns:
        pd.DataFrame: 添加技术指标后的数据
    """
    if df is None or df.empty:
        return None
        
    try:
        # 检查数据量是否足够
        min_periods = 60  # 根据需要的最长周期（如60日均线）设置
        if len(df) < min_periods:
            st.warning(f"数据量不足，需要至少{min_periods}个交易日的数据来计算所有技术指标。当前仅有{len(df)}个交易日的数据。")
            return None
            
        # 数据预处理
        # 1. 确保所有价格数据为正数
        df['Open'] = df['Open'].abs()
        df['High'] = df['High'].abs()
        df['Low'] = df['Low'].abs()
        df['Close'] = df['Close'].abs()
        df['Volume'] = df['Volume'].abs()
        
        # 2. 处理可能的无效值
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna(method='ffill').fillna(method='bfill')
        
        # 计算移动平均线
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA30'] = df['Close'].rolling(window=30).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 计算MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Histogram'] = df['MACD'] - df['Signal']
        
        # 计算RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算KDJ
        low_min = df['Low'].rolling(window=9).min()
        high_max = df['High'].rolling(window=9).max()
        df['K'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['D'] = df['K'].rolling(window=3).mean()
        df['J'] = 3 * df['K'] - 2 * df['D']
        
        # 计算布林带
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        df['BB_Upper'] = df['BB_Middle'] + 2 * df['Close'].rolling(window=20).std()
        df['BB_Lower'] = df['BB_Middle'] - 2 * df['Close'].rolling(window=20).std()
        
        # 计算OBV (On-Balance Volume)
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        
        # 计算CCI (Commodity Channel Index)
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        mean_deviation = abs(typical_price - typical_price.rolling(window=20).mean()).rolling(window=20).mean()
        df['CCI'] = (typical_price - typical_price.rolling(window=20).mean()) / (0.015 * mean_deviation)
        
        # 计算Williams %R
        highest_high = df['High'].rolling(window=14).max()
        lowest_low = df['Low'].rolling(window=14).min()
        df['Williams_R'] = -100 * (highest_high - df['Close']) / (highest_high - lowest_low)
        
        # 计算DMI (Directional Movement Index)
        df['TR'] = np.maximum(df['High'] - df['Low'], 
                             np.maximum(abs(df['High'] - df['Close'].shift(1)), 
                                       abs(df['Low'] - df['Close'].shift(1))))
        df['ATR'] = df['TR'].rolling(window=14).mean()
        
        df['DM+'] = np.where((df['High'] - df['High'].shift(1)) > (df['Low'].shift(1) - df['Low']), 
                            np.maximum(df['High'] - df['High'].shift(1), 0), 0)
        df['DM-'] = np.where((df['Low'].shift(1) - df['Low']) > (df['High'] - df['High'].shift(1)), 
                            np.maximum(df['Low'].shift(1) - df['Low'], 0), 0)
                            
        df['DI+'] = 100 * (df['DM+'].rolling(window=14).mean() / df['ATR'])
        df['DI-'] = 100 * (df['DM-'].rolling(window=14).mean() / df['ATR'])
        
        df['DX'] = 100 * abs(df['DI+'] - df['DI-']) / (df['DI+'] + df['DI-'])
        df['ADX'] = df['DX'].rolling(window=14).mean()
        
        # 计算BIAS (Bias Ratio)
        df['BIAS6'] = (df['Close'] - df['Close'].rolling(window=6).mean()) / df['Close'].rolling(window=6).mean() * 100
        df['BIAS12'] = (df['Close'] - df['Close'].rolling(window=12).mean()) / df['Close'].rolling(window=12).mean() * 100
        df['BIAS24'] = (df['Close'] - df['Close'].rolling(window=24).mean()) / df['Close'].rolling(window=24).mean() * 100
        
        # 计算支撑位和阻力位
        # 使用过去20天的数据计算支撑位和阻力位
        window = 20
        if len(df) >= window:
            # 支撑位：过去20天的最低价的平均值
            df['Support'] = df['Low'].rolling(window=window).min()
            
            # 阻力位：过去20天的最高价的平均值
            df['Resistance'] = df['High'].rolling(window=window).max()
        else:
            # 如果数据不足，使用所有可用数据
            df['Support'] = df['Low'].min()
            df['Resistance'] = df['High'].max()
        
        return df
    except Exception as e:
        st.error(f"计算技术指标时出错: {str(e)}")
        return None

def plot_macd(df):
    """
    绘制MACD指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    # 添加MACD线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MACD'],
        name='MACD',
        line=dict(color='blue')
    ))
    
    # 添加信号线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Signal'],
        name='Signal',
        line=dict(color='orange')
    ))
    
    # 添加柱状图
    colors = ['red' if val >= 0 else 'green' for val in df['Histogram']]
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['Histogram'],
        name='Histogram',
        marker_color=colors
    ))
    
    fig.update_layout(
        title='MACD指标',
        yaxis_title='MACD值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_kdj(df):
    """
    绘制KDJ指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    # 添加K线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['K'],
        name='K值',
        line=dict(color='blue')
    ))
    
    # 添加D线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['D'],
        name='D值',
        line=dict(color='orange')
    ))
    
    # 添加J线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['J'],
        name='J值',
        line=dict(color='purple')
    ))
    
    # 添加超买超卖线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[80] * len(df),
        name='超买线',
        line=dict(color='red', dash='dash')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[20] * len(df),
        name='超卖线',
        line=dict(color='green', dash='dash')
    ))
    
    fig.update_layout(
        title='KDJ指标',
        yaxis_title='KDJ值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_rsi(df):
    """
    绘制RSI指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    # 添加RSI线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['RSI'],
        name='RSI',
        line=dict(color='blue')
    ))
    
    # 添加超买超卖线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[70] * len(df),
        name='超买线',
        line=dict(color='red', dash='dash')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[30] * len(df),
        name='超卖线',
        line=dict(color='green', dash='dash')
    ))
    
    fig.update_layout(
        title='RSI指标',
        yaxis_title='RSI值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_volume(df):
    """
    绘制成交量图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    # 添加成交量柱状图
    colors = ['red' if df['Close'].iloc[i] >= df['Open'].iloc[i] else 'green' 
             for i in range(len(df))]
    
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['Volume'],
        name='成交量',
        marker_color=colors
    ))
    
    # 添加5日均量线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Volume'].rolling(window=5).mean(),
        name='5日均量',
        line=dict(color='orange')
    ))
    
    # 添加10日均量线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Volume'].rolling(window=10).mean(),
        name='10日均量',
        line=dict(color='blue')
    ))
    
    fig.update_layout(
        title='成交量分析',
        yaxis_title='成交量',
        xaxis_title='日期',
        height=300
    )
    
    return fig

# 设置页面配置
st.set_page_config(
    page_title="股票分析系统",
    page_icon="📈",
    layout="wide"
)

# 页面标题
st.title("📈 股票分析系统")

# 获取股票数据
@st.cache_data
def get_stock_data(symbol, start, end, market_type):
    """
    获取股票数据
    
    Args:
        symbol (str): 股票代码
        start (datetime): 开始日期
        end (datetime): 结束日期
        market_type (str): 市场类型
        
    Returns:
        pd.DataFrame: 股票数据
    """
    try:
        if market_type == "A股":
            # A股逻辑保持不变
            if symbol.startswith('6'):
                symbol = f"{symbol}.SH"
            else:
                symbol = f"{symbol}.SZ"
            return get_a_stock_data(symbol, start, end)
        elif market_type == "港股":
            # 港股逻辑保持不变
            symbol = f"{symbol}.HK"
            return get_hk_stock_data(symbol, start, end)
        else:
            # 美股数据获取添加重试机制
            max_retries = 3
            retry_delay = 2  # 秒
            
            for attempt in range(max_retries):
                try:
                    stock = yf.Ticker(symbol)
                    df = stock.history(start=start, end=end, interval="1d")
                    
                    if df.empty:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        st.error(f"无法获取股票 {symbol} 的数据，请检查股票代码是否正确")
                        return None
                    
                    # 重置索引，将日期作为列
                    df = df.reset_index()
                    df = df.rename(columns={'Date': 'date'})
                    
                    return df
                    
                except requests.exceptions.HTTPError as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        st.warning(f"请求频率限制，正在重试... ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay * (attempt + 1))  # 指数退避
                        continue
                    raise
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        st.warning(f"获取数据出错，正在重试... ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    raise
                    
            st.error(f"在 {max_retries} 次尝试后仍无法获取股票数据")
            return None
            
    except Exception as e:
        st.error(f"获取股票数据时出错: {str(e)}")
        return None

# 侧边栏
st.sidebar.header("参数设置")
market_type = st.sidebar.selectbox("市场类型", ["A股", "港股", "美股"])
# 根据市场类型设置默认股票代码
default_symbol = {
    "A股": "300024",
    "港股": "00700",
    "美股": "AAPL"
}
stock_symbol = st.sidebar.text_input("股票代码", default_symbol[market_type])
start_date = st.sidebar.date_input("开始日期", datetime.now() - timedelta(days=90))  # 约65个交易日
end_date = st.sidebar.date_input("结束日期", datetime.now())

# 添加分析按钮到侧边栏
analyze_button = st.sidebar.button("开始深度分析")
volume_analysis_button = st.sidebar.button("主力行为分析")

# 在页面顶部添加盘中实时波动分析区域
st.markdown("## 📊 盘中实时波动分析")
realtime_container = st.container()

with realtime_container:
    # 创建三列布局
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.write(f"**市场类型:** {market_type}")
    with col2:
        st.write(f"**股票代码:** {stock_symbol}")
    with col3:
        refresh_realtime = st.button("刷新实时数据")
    
    # 使用session_state来控制自动刷新
    if 'auto_refresh_time' not in st.session_state:
        st.session_state.auto_refresh_time = time.time()
        
    if 'auto_refresh_enabled' not in st.session_state:
        st.session_state.auto_refresh_enabled = False
    
    # 添加自动刷新选项
    auto_refresh = st.checkbox("启用自动刷新（每5秒）", value=st.session_state.auto_refresh_enabled, key="auto_refresh_checkbox")
    
    # 更新自动刷新状态
    if auto_refresh != st.session_state.auto_refresh_enabled:
        st.session_state.auto_refresh_enabled = auto_refresh
        
    # 每5秒自动刷新
    current_time = time.time()
    if st.session_state.auto_refresh_enabled and current_time - st.session_state.auto_refresh_time >= 5:
        st.session_state.auto_refresh_time = current_time
        refresh_realtime = True
    
    # 获取实时数据
    if refresh_realtime or 'last_refresh' not in st.session_state:
        with st.spinner("正在获取实时数据..."):
            realtime_data = get_realtime_data(stock_symbol, market_type)
            
            if realtime_data:
                st.session_state['realtime_data'] = realtime_data
                st.session_state['last_refresh'] = datetime.now()
                
                # 获取历史数据用于分析
                df = get_stock_data(stock_symbol, start_date, end_date, market_type)
                if df is not None:
                    df = calculate_indicators(df)
                    if df is not None:
                        # 分析盘中趋势
                        trend_analysis = analyze_intraday_trend(realtime_data, df)
                        st.session_state['trend_analysis'] = trend_analysis
    
    # 显示实时数据和分析结果
    if 'realtime_data' in st.session_state and 'trend_analysis' in st.session_state:
        realtime_data = st.session_state['realtime_data']
        trend_analysis = st.session_state['trend_analysis']
        
        # 显示最后更新时间
        st.write(f"**最后更新时间:** {st.session_state['last_refresh'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 显示实时价格和基本信息
        price_col1, price_col2, price_col3 = st.columns(3)
        with price_col1:
            st.metric("实时价格", format_price(realtime_data['price'], market_type))
            st.metric("开盘价", format_price(realtime_data['open'], market_type))
        with price_col2:
            st.metric("最高价", format_price(realtime_data['high'], market_type))
            st.metric("最低价", format_price(realtime_data['low'], market_type))
        with price_col3:
            if 'pre_close' in realtime_data and realtime_data['pre_close']:
                price_change_pct = (realtime_data['price'] - realtime_data['pre_close']) / realtime_data['pre_close'] * 100
                st.metric("涨跌幅", f"{price_change_pct:.2f}%", delta=f"{price_change_pct:.2f}%")
            st.metric("成交量", f"{realtime_data['volume']/10000:.2f}万股")
        
        # 显示趋势分析结果
        trend_color = {
            '强势上涨': 'green',
            '温和上涨': 'lightgreen',
            '盘整': 'orange',
            '温和下跌': 'pink',
            '强势下跌': 'red',
            '分析出错': 'gray',
            '无法分析': 'gray'
        }.get(trend_analysis['trend'], 'gray')
        
        st.markdown(f"<h3 style='color: {trend_color};'>盘中趋势: {trend_analysis['trend']}</h3>", unsafe_allow_html=True)
        st.markdown(f"**分析依据:** {trend_analysis['reason']}")
        st.markdown(f"**后市预测:** {trend_analysis['prediction']}")
        
        # 删除原来的自动刷新选项
        # auto_refresh = st.checkbox("启用自动刷新（每5秒）", value=False)
        # if auto_refresh:
        #     time.sleep(5)  # 等待5秒
        #     st.experimental_rerun()  # 重新运行应用
    else:
        st.info("点击'刷新实时数据'按钮获取最新盘中数据")

# 创建标签页
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["K线图", "技术指标", "主力资金", "分析报告", "战法分析", "主力行为"])

def get_company_info(symbol):
    """
    获取公司基本信息
    
    Args:
        symbol (str): 股票代码
        
    Returns:
        dict: 公司信息
    """
    try:
        pro = ts.pro_api()
        # 获取公司基本信息
        basic = pro.daily_basic(ts_code=symbol, 
                              fields='ts_code,trade_date,pe,pb,ps,roe,roa,debt_to_assets,current_ratio')
        # 获取公司详细信息
        company = pro.stock_company(ts_code=symbol)
        
        if basic.empty or company.empty:
            return None
            
        # 获取最新财务指标
        latest_basic = basic.iloc[0]
        
        return {
            'basic_info': {
                '公司名称': company['chairman'].iloc[0],
                '上市日期': company['list_date'].iloc[0],
                '主营业务': company['main_business'].iloc[0],
                '所属行业': company['industry'].iloc[0],
                '总市值': company['market_cap'].iloc[0],
                '流通市值': company['float_market_cap'].iloc[0]
            },
            'financial_indicators': {
                '市盈率(PE)': latest_basic['pe'],
                '市净率(PB)': latest_basic['pb'],
                '市销率(PS)': latest_basic['ps'],
                '净资产收益率(ROE)': latest_basic['roe'],
                '总资产收益率(ROA)': latest_basic['roa'],
                '资产负债率': latest_basic['debt_to_assets'],
                '流动比率': latest_basic['current_ratio']
            }
        }
    except Exception as e:
        st.error(f"获取公司信息时出错: {str(e)}")
        return None

def get_industry_comparison(symbol):
    """
    获取行业对比数据
    
    Args:
        symbol (str): 股票代码
        
    Returns:
        pd.DataFrame: 行业对比数据
    """
    try:
        pro = ts.pro_api()
        # 获取公司所属行业
        company = pro.stock_company(ts_code=symbol)
        if company.empty:
            return None
            
        industry = company['industry'].iloc[0]
        
        # 获取同行业公司列表
        industry_companies = pro.stock_company(industry=industry)
        
        # 获取行业公司财务指标
        industry_data = []
        for ts_code in industry_companies['ts_code']:
            basic = pro.daily_basic(ts_code=ts_code, 
                                  fields='ts_code,trade_date,pe,pb,ps,roe,roa')
            if not basic.empty:
                industry_data.append(basic.iloc[0])
        
        if not industry_data:
            return None
            
        df = pd.DataFrame(industry_data)
        return df
        
    except Exception as e:
        st.error(f"获取行业对比数据时出错: {str(e)}")
        return None

def get_shareholder_structure(symbol):
    """
    获取股东结构数据
    
    Args:
        symbol (str): 股票代码
        
    Returns:
        pd.DataFrame: 股东结构数据
    """
    try:
        pro = ts.pro_api()
        # 获取十大股东数据
        top10 = pro.top10_holders(ts_code=symbol)
        # 获取十大流通股东数据
        top10_float = pro.top10_floatholders(ts_code=symbol)
        
        return {
            'top10_holders': top10,
            'top10_float_holders': top10_float
        }
    except Exception as e:
        st.error(f"获取股东结构数据时出错: {str(e)}")
        return None

def analyze_buy_sell_signals(df, company_info=None):
    """
    分析买卖点信号
    
    Args:
        df (pd.DataFrame): 股票数据
        company_info (dict): 公司基本面信息
        
    Returns:
        dict: 买卖点分析结果
    """
    signals = {
        'buy_signals': [],
        'sell_signals': [],
        'recommendation': '',
        'reason': '',
        'score': 0  # -100 到 100 的评分，负数表示卖出倾向，正数表示买入倾向
    }
    
    # 检查数据量是否足够
    if len(df) < 30:
        signals['recommendation'] = "数据不足"
        signals['reason'] = "选择的日期范围内数据量不足，无法进行可靠的技术分析"
        return signals
    
    # 技术面分析
    # 1. MACD指标分析
    if df['MACD'].iloc[-1] > df['Signal'].iloc[-1] and df['MACD'].iloc[-2] <= df['Signal'].iloc[-2]:
        signals['buy_signals'].append("MACD金叉")
        signals['score'] += 15
    elif df['MACD'].iloc[-1] < df['Signal'].iloc[-1] and df['MACD'].iloc[-2] >= df['Signal'].iloc[-2]:
        signals['sell_signals'].append("MACD死叉")
        signals['score'] -= 15
    
    # 2. KDJ指标分析
    if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]:
        signals['buy_signals'].append("KDJ金叉")
        signals['score'] += 10
    elif df['K'].iloc[-1] < df['D'].iloc[-1] and df['K'].iloc[-2] >= df['D'].iloc[-2]:
        signals['sell_signals'].append("KDJ死叉")
        signals['score'] -= 10
    
    # 3. RSI指标分析
    if df['RSI'].iloc[-1] < 30:
        signals['buy_signals'].append("RSI超卖")
        signals['score'] += 15
    elif df['RSI'].iloc[-1] > 70:
        signals['sell_signals'].append("RSI超买")
        signals['score'] -= 15
    
    # 4. 布林带分析
    if df['Close'].iloc[-1] < df['BB_Lower'].iloc[-1]:
        signals['buy_signals'].append("价格触及布林带下轨")
        signals['score'] += 10
    elif df['Close'].iloc[-1] > df['BB_Upper'].iloc[-1]:
        signals['sell_signals'].append("价格触及布林带上轨")
        signals['score'] -= 10
    
    # 5. 支撑位和阻力位分析
    if df['Close'].iloc[-1] < df['Support'].iloc[-1] * 1.02:
        signals['buy_signals'].append("价格接近支撑位")
        signals['score'] += 10
    elif df['Close'].iloc[-1] > df['Resistance'].iloc[-1] * 0.98:
        signals['sell_signals'].append("价格接近阻力位")
        signals['score'] -= 10
    
    # 6. 均线分析
    if df['MA5'].iloc[-1] > df['MA20'].iloc[-1] and df['MA5'].iloc[-2] <= df['MA20'].iloc[-2]:
        signals['buy_signals'].append("5日均线上穿20日均线")
        signals['score'] += 15
    elif df['MA5'].iloc[-1] < df['MA20'].iloc[-1] and df['MA5'].iloc[-2] >= df['MA20'].iloc[-2]:
        signals['sell_signals'].append("5日均线下穿20日均线")
        signals['score'] -= 15
    
    # 7. CCI指标分析
    if df['CCI'].iloc[-1] < -100:
        signals['buy_signals'].append("CCI超卖")
        signals['score'] += 10
    elif df['CCI'].iloc[-1] > 100:
        signals['sell_signals'].append("CCI超买")
        signals['score'] -= 10
    
    # 8. Williams %R指标分析
    if df['Williams_R'].iloc[-1] < -80:
        signals['buy_signals'].append("威廉指标超卖")
        signals['score'] += 10
    elif df['Williams_R'].iloc[-1] > -20:
        signals['sell_signals'].append("威廉指标超买")
        signals['score'] -= 10
    
    # 9. DMI指标分析
    if df['DI+'].iloc[-1] > df['DI-'].iloc[-1] and df['DI+'].iloc[-2] <= df['DI-'].iloc[-2]:
        signals['buy_signals'].append("DMI金叉")
        signals['score'] += 10
    elif df['DI+'].iloc[-1] < df['DI-'].iloc[-1] and df['DI+'].iloc[-2] >= df['DI-'].iloc[-2]:
        signals['sell_signals'].append("DMI死叉")
        signals['score'] -= 10
    
    # 10. 乖离率分析
    if df['BIAS6'].iloc[-1] < -10:
        signals['buy_signals'].append("20日乖离率超卖")
        signals['score'] += 10
    elif df['BIAS6'].iloc[-1] > 10:
        signals['sell_signals'].append("20日乖离率超买")
        signals['score'] -= 10
    
    # 基本面分析（如果有公司信息）
    if company_info:
        # 1. PE分析
        pe = company_info['financial_indicators']['市盈率(PE)']
        if pe < 15:
            signals['buy_signals'].append(f"PE较低 ({pe:.2f})")
            signals['score'] += 10
        elif pe > 30:
            signals['sell_signals'].append(f"PE较高 ({pe:.2f})")
            signals['score'] -= 10
        
        # 2. PB分析
        pb = company_info['financial_indicators']['市净率(PB)']
        if pb < 1.5:
            signals['buy_signals'].append(f"PB较低 ({pb:.2f})")
            signals['score'] += 5
        elif pb > 3:
            signals['sell_signals'].append(f"PB较高 ({pb:.2f})")
            signals['score'] -= 5
        
        # 3. ROE分析
        roe = company_info['financial_indicators']['净资产收益率(ROE)']
        if roe > 15:
            signals['buy_signals'].append(f"ROE较高 ({roe:.2f}%)")
            signals['score'] += 10
        elif roe < 5:
            signals['sell_signals'].append(f"ROE较低 ({roe:.2f}%)")
            signals['score'] -= 5
    
    # 综合评分，给出建议
    if signals['score'] >= 30:
        signals['recommendation'] = "强烈买入"
        signals['reason'] = "多项技术指标和基本面指标显示买入信号"
    elif signals['score'] >= 15:
        signals['recommendation'] = "建议买入"
        signals['reason'] = "部分技术指标和基本面指标显示买入信号"
    elif signals['score'] <= -30:
        signals['recommendation'] = "强烈卖出"
        signals['reason'] = "多项技术指标和基本面指标显示卖出信号"
    elif signals['score'] <= -15:
        signals['recommendation'] = "建议卖出"
        signals['reason'] = "部分技术指标和基本面指标显示卖出信号"
    else:
        signals['recommendation'] = "观望"
        signals['reason'] = "技术指标和基本面指标信号不明确，建议观望"
    
    return signals

def plot_buy_sell_points(df):
    """
    根据45度角战法绘制买卖点图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    # 创建子图
    fig = go.Figure()
    
    # 添加K线图
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='K线'
    ))
    
    # 添加均线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA5'],
        name='MA5',
        line=dict(color='red')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA10'],
        name='MA10',
        line=dict(color='orange')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA20'],
        name='MA20',
        line=dict(color='blue')
    ))
    
    # 标记买入点和卖出点
    buy_points = []
    sell_points = []
    
    # 检查数据量是否足够
    if len(df) > 20:
        # 计算均线角度（使用5日均线）
        ma5_angle = []
        for i in range(5, len(df)):
            # 计算MA5的角度（使用反正切函数）
            dx = 5  # 5个交易日
            dy = df['MA5'].iloc[i] - df['MA5'].iloc[i-5]
            angle = np.degrees(np.arctan2(dy, dx))
            ma5_angle.append(angle)
        
        # 将角度数据添加到DataFrame中
        df['MA5_Angle'] = [None]*5 + ma5_angle
        
        # 遍历数据寻找买卖点
        for i in range(20, len(df)):
            # 计算均线排列
            ma_alignment = (df['MA5'].iloc[i] > df['MA10'].iloc[i] > df['MA20'].iloc[i])
            reverse_ma_alignment = (df['MA5'].iloc[i] < df['MA10'].iloc[i] < df['MA20'].iloc[i])
            
            # 计算角度变化
            if df['MA5_Angle'].iloc[i] is not None:
                angle = df['MA5_Angle'].iloc[i]
                prev_angle = df['MA5_Angle'].iloc[i-1] if df['MA5_Angle'].iloc[i-1] is not None else 0
                
                # 买入条件：
                # 1. 均线多头排列
                # 2. MA5角度接近45度（允许一定范围：35-55度）
                # 3. 价格突破MA5且站稳
                # 4. 确保信号不会太密集（与前一个信号至少间隔10个交易日）
                if (ma_alignment and 
                    35 <= angle <= 55 and
                    df['Close'].iloc[i] > df['MA5'].iloc[i] and
                    df['Close'].iloc[i-1] > df['MA5'].iloc[i-1] and
                    (not buy_points or i - buy_points[-1] > 10)):
                    buy_points.append(i)
                
                # 卖出条件：
                # 1. 均线空头排列
                # 2. MA5角度接近-45度（允许一定范围：-55至-35度）
                # 3. 价格跌破MA5且确认
                # 4. 确保信号不会太密集（与前一个信号至少间隔10个交易日）
                elif (reverse_ma_alignment and 
                      -55 <= angle <= -35 and
                      df['Close'].iloc[i] < df['MA5'].iloc[i] and
                      df['Close'].iloc[i-1] < df['MA5'].iloc[i-1] and
                      (not sell_points or i - sell_points[-1] > 10)):
                    sell_points.append(i)
    
    # 添加买入点
    if buy_points:
        fig.add_trace(go.Scatter(
            x=[df.index[i] for i in buy_points],
            y=[df['Low'].iloc[i] * 0.99 for i in buy_points],
            mode='markers',
            marker=dict(
                symbol='triangle-up',
                size=15,
                color='red'
            ),
            name='买入信号'
        ))
    
    # 添加卖出点
    if sell_points:
        fig.add_trace(go.Scatter(
            x=[df.index[i] for i in sell_points],
            y=[df['High'].iloc[i] * 1.01 for i in sell_points],
            mode='markers',
            marker=dict(
                symbol='triangle-down',
                size=15,
                color='green'
            ),
            name='卖出信号'
        ))
    
    fig.update_layout(
        title='45度角战法买卖点分析',
        yaxis_title='价格',
        xaxis_title='日期',
        height=600,
        xaxis_rangeslider_visible=False
    )
    
    return fig

def plot_cci(df):
    """
    绘制CCI指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['CCI'],
        name='CCI',
        line=dict(color='purple')
    ))
    
    # 添加超买超卖线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[100] * len(df),
        name='超买线',
        line=dict(color='red', dash='dash')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[-100] * len(df),
        name='超卖线',
        line=dict(color='green', dash='dash')
    ))
    
    fig.update_layout(
        title='CCI指标',
        yaxis_title='CCI值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_williams_r(df):
    """
    绘制威廉指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['Williams_R'],
        name='Williams %R',
        line=dict(color='blue')
    ))
    
    # 添加超买超卖线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[-20] * len(df),
        name='超买线',
        line=dict(color='red', dash='dash')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=[-80] * len(df),
        name='超卖线',
        line=dict(color='green', dash='dash')
    ))
    
    fig.update_layout(
        title='威廉指标',
        yaxis_title='Williams %R值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_dmi(df):
    """
    绘制DMI指标图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['DI+'],
        name='+DI',
        line=dict(color='green')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['DI-'],
        name='-DI',
        line=dict(color='red')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['ADX'],
        name='ADX',
        line=dict(color='blue')
    ))
    
    fig.update_layout(
        title='DMI指标',
        yaxis_title='DMI值',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_bias(df):
    """
    绘制乖离率图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['BIAS6'],
        name='BIAS6',
        line=dict(color='red')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['BIAS12'],
        name='BIAS12',
        line=dict(color='blue')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['BIAS24'],
        name='BIAS24',
        line=dict(color='green')
    ))
    
    fig.update_layout(
        title='乖离率',
        yaxis_title='乖离率(%)',
        xaxis_title='日期',
        height=300
    )
    
    return fig

def plot_ma(df):
    """
    绘制均线图表
    
    Args:
        df (pd.DataFrame): 股票数据
    """
    fig = go.Figure()
    
    # 添加K线图
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='K线'
    ))
    
    # 添加均线
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA5'],
        name='MA5',
        line=dict(color='red')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA10'],
        name='MA10',
        line=dict(color='orange')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA20'],
        name='MA20',
        line=dict(color='blue')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA30'],
        name='MA30',
        line=dict(color='purple')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['MA60'],
        name='MA60',
        line=dict(color='green')
    ))
    
    fig.update_layout(
        title='K线与均线',
        yaxis_title='价格',
        xaxis_title='日期',
        height=500,
        xaxis_rangeslider_visible=False  # 禁用默认的范围滑块
    )
    
    return fig

def generate_analysis_report(df, stock_symbol, market_type, company_info=None, news_summary=None):
    """
    生成综合分析报告
    
    Args:
        df (pd.DataFrame): 股票数据
        stock_symbol (str): 股票代码
        market_type (str): 市场类型
        company_info (dict): 公司信息
        news_summary (dict): 新闻摘要
    
    Returns:
        bytes: PDF文件内容
    """
    # 创建PDF缓冲区
    buffer = io.BytesIO()
    
    # 创建PDF文档
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # 注册中文字体（使用系统自带的微软雅黑字体）
    font_path = "C:/Windows/Fonts/msyh.ttc"  # 微软雅黑字体路径
    pdfmetrics.registerFont(TTFont('MicrosoftYaHei', font_path))
    
    # 第一页：技术分析概览
    # 设置标题
    c.setFont('MicrosoftYaHei', 20)
    c.drawString(50, height - 50, f"{stock_symbol} 股票分析报告")
    c.setFont('MicrosoftYaHei', 12)
    c.drawString(50, height - 70, f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 计算当前价格和建议买卖价位
    current_price = df['Close'].iloc[-1]
    support_price = df['Support'].iloc[-1]
    resistance_price = df['Resistance'].iloc[-1]
    
    # 技术分析部分
    c.setFont('MicrosoftYaHei', 16)
    c.drawString(50, height - 100, "一、技术分析概览")
    
    # 保存图表为图片
    fig_ma = plot_ma(df)
    img_ma = pio.to_image(fig_ma, format='png')
    img_ma = Image.open(io.BytesIO(img_ma))
    img_ma.save('ma_temp.png')
    c.drawImage('ma_temp.png', 50, height - 400, width=500, height=250)
    
    # 买卖点分析
    signals = analyze_buy_sell_signals(df, company_info)
    c.setFont('MicrosoftYaHei', 12)
    y = height - 450
    
    # 价格建议
    c.drawString(50, y, f"当前价格：{format_price(current_price, market_type)}")
    y -= 20
    c.drawString(50, y, f"支撑位：{format_price(support_price, market_type)}")
    y -= 20
    c.drawString(50, y, f"阻力位：{format_price(resistance_price, market_type)}")
    y -= 20
    
    # 计算建议买入和卖出价位
    buy_price = support_price * 1.02  # 支撑位上方2%
    sell_price = resistance_price * 0.98  # 阻力位下方2%
    
    c.drawString(50, y, f"建议买入价位：{format_price(buy_price, market_type)}")
    y -= 20
    c.drawString(50, y, f"建议卖出价位：{format_price(sell_price, market_type)}")
    y -= 20
    
    # 综合建议
    y -= 20
    c.drawString(50, y, f"综合建议：{signals['recommendation']}")
    y -= 20
    c.drawString(50, y, f"评分：{signals['score']}")
    y -= 20
    c.drawString(50, y, f"原因：{signals['reason']}")
    
    # 第一页结束，保存页面
    c.showPage()
    
    # 第二页：买卖信号和操作建议
    c.setFont('MicrosoftYaHei', 16)
    c.drawString(50, height - 50, "技术分析详情")
    c.setFont('MicrosoftYaHei', 12)
    y = height - 80
    
    # 买入信号
    c.drawString(50, y, "买入信号：")
    for signal in signals['buy_signals']:
        y -= 20
        c.drawString(70, y, f"• {signal}")
    
    # 卖出信号
    y -= 30
    c.drawString(50, y, "卖出信号：")
    for signal in signals['sell_signals']:
        y -= 20
        c.drawString(70, y, f"• {signal}")
    
    # 操作建议
    y -= 40
    c.drawString(50, y, "具体操作建议：")
    y -= 20
    
    # 根据评分生成具体建议
    if signals['score'] >= 30:
        suggestion = f"""
        1. 强烈建议买入，可分批建仓：
           - 第一批：当价格回调至 {format_price(buy_price, market_type)} 时买入总仓位的30%
           - 第二批：当价格继续下探至 {format_price(support_price, market_type)} 时买入总仓位的20%
           - 设置止损位：{format_price(support_price * 0.95, market_type)}
        """
    elif signals['score'] >= 15:
        suggestion = f"""
        1. 建议小仓位买入：
           - 可在 {format_price(buy_price, market_type)} 买入总仓位的20%
           - 设置止损位：{format_price(support_price * 0.95, market_type)}
        """
    elif signals['score'] <= -30:
        suggestion = f"""
        1. 强烈建议卖出：
           - 当前可卖出全部持仓
           - 如需等待可设置止损位：{format_price(current_price * 0.95, market_type)}
        """
    elif signals['score'] <= -15:
        suggestion = f"""
        1. 建议逐步减仓：
           - 当价格触及 {format_price(sell_price, market_type)} 时卖出30%持仓
           - 设置止损位：{format_price(current_price * 0.95, market_type)}
        """
    else:
        suggestion = f"""
        1. 建议观望：
           - 可在 {format_price(buy_price, market_type)} 小仓位试探性买入
           - 或等待价格突破 {format_price(resistance_price, market_type)} 后回调再买入
           - 设置止损位：{format_price(support_price * 0.95, market_type)}
        """
    
    # 分行显示建议
    for line in suggestion.split('\n'):
        line = line.strip()
        if line:
            c.drawString(70, y, line)
            y -= 20
    
    # 风险提示
    y -= 40
    c.setFont('MicrosoftYaHei', 14)
    c.drawString(50, y, "风险提示：")
    c.setFont('MicrosoftYaHei', 12)
    y -= 20
    risk_tips = [
        "1. 本报告中的建议仅供参考，不构成投资建议",
        "2. 投资者需根据自身风险承受能力做出投资决策",
        "3. 股市有风险，投资需谨慎",
        f"4. 建议止损位设置在支撑位下方5%（{format_price(support_price * 0.95, market_type)}）"
    ]
    for tip in risk_tips:
        c.drawString(70, y, tip)
        y -= 20
    
    c.showPage()
    
    # 第三页：基本面分析
    if company_info:
        c.setFont('MicrosoftYaHei', 16)
        c.drawString(50, height - 50, "二、基本面分析")
        
        y = height - 80
        c.setFont('MicrosoftYaHei', 12)
        for key, value in company_info['basic_info'].items():
            y -= 20
            c.drawString(50, y, f"{key}：{value}")
        
        y -= 40
        c.drawString(50, y, "财务指标：")
        for key, value in company_info['financial_indicators'].items():
            y -= 20
            c.drawString(70, y, f"{key}：{value:.2f}")
        
        c.showPage()
    
    # 第四页：新闻分析
    if news_summary:
        c.setFont('MicrosoftYaHei', 16)
        c.drawString(50, height - 50, "三、新闻舆情分析")
        
        y = height - 80
        c.setFont('MicrosoftYaHei', 12)
        c.drawString(50, y, f"新闻总数：{news_summary['total_news']}")
        y -= 20
        c.drawString(50, y, f"利好新闻：{news_summary['sentiment_distribution'].get('利好', 0)}")
        y -= 20
        c.drawString(50, y, f"利空新闻：{news_summary['sentiment_distribution'].get('利空', 0)}")
    
    # 保存PDF
    c.save()
    
    # 删除临时文件
    if os.path.exists('ma_temp.png'):
        os.remove('ma_temp.png')
    
    # 获取PDF内容
    buffer.seek(0)
    return buffer.getvalue()

# 主程序
try:
    # 获取数据
    df = get_stock_data(stock_symbol, start_date, end_date, market_type)
    
    if df is not None:
        # 确保数据按照选择的日期范围进行筛选
        df = df.set_index('date')  # 将date列设置为索引
        df = df.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]
        df = df.reset_index()  # 重置索引，使date重新成为列
        
        # 移动分析按钮的处理逻辑到分析报告标签页
        with tab5:
            if analyze_button:
                with st.spinner("正在进行深度分析，请稍候..."):
                    # 计算指标
                    df = calculate_indicators(df)
                    
                    if df is not None:
                        # 获取公司信息
                        company_info = get_company_info(stock_symbol) if market_type == "A股" else None
                        
                        # 获取新闻分析
                        news_analyzer = NewsAnalyzer(stock_symbol, market_type)
                        news_summary = news_analyzer.get_news_summary(days=7)
                        
                        # 生成PDF报告
                        pdf_content = generate_analysis_report(df, stock_symbol, market_type, company_info, news_summary)
                        
                        # 显示分析结果
                        st.success("分析完成！")
                        
                        # 提供PDF下载
                        st.download_button(
                            label="下载分析报告",
                            data=pdf_content,
                            file_name=f"{stock_symbol}_分析报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf"
                        )
                        
                        # 显示主要分析结果
                        st.subheader("分析结果摘要")
                        
                        # 技术面分析
                        st.write("**技术面分析**")
                        signals = analyze_buy_sell_signals(df, company_info)
                        st.write(f"综合建议：{signals['recommendation']}")
                        st.write(f"评分：{signals['score']}")
                        st.write(f"原因：{signals['reason']}")
                        
                        # 显示买卖点
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**买入信号**")
                            for signal in signals['buy_signals']:
                                st.success(signal)
                        
                        with col2:
                            st.write("**卖出信号**")
                            for signal in signals['sell_signals']:
                                st.error(signal)
                        
                        # 显示K线图和买卖点
                        st.subheader("K线图与买卖点分析")
                        # 使用包含实时数据的DataFrame绘制买卖点图表
                        df_for_plot = df
                        if 'realtime_data' in st.session_state:
                            df_with_realtime = df.copy()
                            realtime_data = st.session_state['realtime_data']
                            # 如果有实时数据，更新最后一行的收盘价、最高价、最低价等
                            if len(df_with_realtime) > 0:
                                # 仅在交易时段更新
                                is_trading_hours = True  # 可以根据需要添加具体的交易时段判断逻辑
                                if is_trading_hours:
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Close'] = realtime_data['price']
                                    # 更新最高价和最低价（如果实时数据更高或更低）
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'High'] = max(df_with_realtime['High'].iloc[-1], realtime_data['high'])
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Low'] = min(df_with_realtime['Low'].iloc[-1], realtime_data['low'])
                                    # 更新成交量
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Volume'] = realtime_data['volume']
                                    # 重新计算技术指标
                                    df_with_realtime = calculate_indicators(df_with_realtime)
                                    df_for_plot = df_with_realtime
                                    
                        fig_buy_sell = plot_buy_sell_points(df_for_plot)
                        st.plotly_chart(fig_buy_sell, use_container_width=True)
                        
                        # 如果有公司信息，显示基本面分析
                        if company_info:
                            st.subheader("基本面分析")
                            st.write("**主要财务指标**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("市盈率(PE)", f"{company_info['financial_indicators']['市盈率(PE)']:.2f}")
                                st.metric("市净率(PB)", f"{company_info['financial_indicators']['市净率(PB)']:.2f}")
                                st.metric("ROE", f"{company_info['financial_indicators']['净资产收益率(ROE)']:.2f}%")
                            with col2:
                                st.metric("资产负债率", f"{company_info['financial_indicators']['资产负债率']:.2f}%")
                                st.metric("流动比率", f"{company_info['financial_indicators']['流动比率']:.2f}")
                        
                        # 显示新闻分析
                        if news_summary:
                            st.subheader("新闻情绪分析")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("新闻总数", news_summary['total_news'])
                            with col2:
                                st.metric("利好新闻", news_summary['sentiment_distribution'].get('正面', 0))
                            with col3:
                                st.metric("利空新闻", news_summary['sentiment_distribution'].get('负面', 0))
            else:
                st.info('点击侧边栏的"开始深度分析"按钮生成分析报告')
        
        # 检查数据量是否足够
        if len(df) < 2:
            st.error("选择的日期范围内没有足够的数据，请扩大日期范围")
        else:
            # 计算指标
            df = calculate_indicators(df)
            
            if df is not None:
                # 技术分析标签页
                with tab1:
                    # 创建左右布局
                    left_col, right_col = st.columns([2, 1])
                    
                    with left_col:
                        # 显示K线图和均线
                        st.subheader("K线与均线")
                        fig_ma = plot_ma(df)
                        st.plotly_chart(fig_ma, use_container_width=True)
                        
                        # 显示MACD指标
                        st.subheader("MACD指标")
                        fig_macd = plot_macd(df)
                        st.plotly_chart(fig_macd, use_container_width=True)
                        
                        # 显示KDJ指标
                        st.subheader("KDJ指标")
                        fig_kdj = plot_kdj(df)
                        st.plotly_chart(fig_kdj, use_container_width=True)
                        
                        # 显示买卖点图表
                        st.subheader("买卖点图表")
                        # 使用包含实时数据的DataFrame绘制买卖点图表
                        df_for_plot = df
                        if 'realtime_data' in st.session_state:
                            df_with_realtime = df.copy()
                            realtime_data = st.session_state['realtime_data']
                            # 如果有实时数据，更新最后一行的收盘价、最高价、最低价等
                            if len(df_with_realtime) > 0:
                                # 仅在交易时段更新
                                is_trading_hours = True  # 可以根据需要添加具体的交易时段判断逻辑
                                if is_trading_hours:
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Close'] = realtime_data['price']
                                    # 更新最高价和最低价（如果实时数据更高或更低）
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'High'] = max(df_with_realtime['High'].iloc[-1], realtime_data['high'])
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Low'] = min(df_with_realtime['Low'].iloc[-1], realtime_data['low'])
                                    # 更新成交量
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Volume'] = realtime_data['volume']
                                    # 重新计算技术指标
                                    df_with_realtime = calculate_indicators(df_with_realtime)
                                    df_for_plot = df_with_realtime
                                    
                        fig_buy_sell = plot_buy_sell_points(df_for_plot)
                        st.plotly_chart(fig_buy_sell, use_container_width=True)
                    
                    with right_col:
                        # 显示当前价格和主要指标
                        st.subheader("当前行情")
                        
                        # 使用实时数据显示当前价格（如果有）
                        if 'realtime_data' in st.session_state:
                            realtime_data = st.session_state['realtime_data']
                            st.metric("当前价格", format_price(realtime_data['price'], market_type))
                        else:
                            st.metric("当前价格", format_price(df['Close'].iloc[-1], market_type))
                        
                        # 显示主要技术指标
                        st.subheader("主要技术指标")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("RSI", f"{df['RSI'].iloc[-1]:.2f}")
                            st.metric("MACD", f"{df['MACD'].iloc[-1]:.2f}")
                            st.metric("KDJ-K", f"{df['K'].iloc[-1]:.2f}")
                            st.metric("CCI", f"{df['CCI'].iloc[-1]:.2f}")
                        with col2:
                            st.metric("ATR", f"{df['ATR'].iloc[-1]:.2f}")
                            st.metric("Williams %R", f"{df['Williams_R'].iloc[-1]:.2f}")
                            st.metric("ADX", f"{df['ADX'].iloc[-1]:.2f}")
                            st.metric("BIAS20", f"{df['BIAS6'].iloc[-1]:.2f}%")
                        
                        # 显示买卖点分析
                        st.subheader("买卖点分析")
                        company_info = get_company_info(stock_symbol) if market_type == "A股" else None
                        
                        # 将实时数据整合到DataFrame中进行分析
                        df_with_realtime = df.copy()
                        if 'realtime_data' in st.session_state:
                            realtime_data = st.session_state['realtime_data']
                            # 如果有实时数据，更新最后一行的收盘价、最高价、最低价等
                            if len(df_with_realtime) > 0:
                                # 仅在交易时段更新（非交易时段可能使用的是前一天的收盘价作为实时价格）
                                is_trading_hours = True  # 可以根据需要添加具体的交易时段判断逻辑
                                if is_trading_hours:
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Close'] = realtime_data['price']
                                    # 更新最高价和最低价（如果实时数据更高或更低）
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'High'] = max(df_with_realtime['High'].iloc[-1], realtime_data['high'])
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Low'] = min(df_with_realtime['Low'].iloc[-1], realtime_data['low'])
                                    # 更新成交量
                                    df_with_realtime.loc[df_with_realtime.index[-1], 'Volume'] = realtime_data['volume']
                                    # 重新计算技术指标
                                    df_with_realtime = calculate_indicators(df_with_realtime)
                                    
                        signals = analyze_buy_sell_signals(df_with_realtime if 'realtime_data' in st.session_state else df, company_info)
                        
                        # 显示买卖点推荐
                        if signals['recommendation'] == "数据不足":
                            st.warning(signals['reason'])
                        else:
                            recommendation_color = "green" if "买入" in signals['recommendation'] else "red" if "卖出" in signals['recommendation'] else "orange"
                            st.markdown(f"<h3 style='color: {recommendation_color};'>{signals['recommendation']}</h3>", unsafe_allow_html=True)
                            st.metric("综合评分", f"{signals['score']}")
                            st.write(f"**原因:** {signals['reason']}")
                            
                            # 显示是否使用了实时数据
                            if 'realtime_data' in st.session_state:
                                st.info(f"分析使用了截至 {st.session_state['last_refresh'].strftime('%H:%M:%S')} 的实时数据")
                        
                        # 显示买入信号
                        if signals['buy_signals']:
                            st.write("**买入信号:**")
                            for signal in signals['buy_signals']:
                                st.success(signal)
                        
                        # 显示卖出信号
                        if signals['sell_signals']:
                            st.write("**卖出信号:**")
                            for signal in signals['sell_signals']:
                                st.error(signal)
                        
                        # 显示其他技术指标图表
                        st.subheader("更多技术指标")
                        
                        # CCI指标
                        fig_cci = plot_cci(df)
                        st.plotly_chart(fig_cci, use_container_width=True)
                        
                        # Williams %R指标
                        fig_williams = plot_williams_r(df)
                        st.plotly_chart(fig_williams, use_container_width=True)
                        
                        # DMI指标
                        fig_dmi = plot_dmi(df)
                        st.plotly_chart(fig_dmi, use_container_width=True)
                        
                        # 乖离率
                        fig_bias = plot_bias(df)
                        st.plotly_chart(fig_bias, use_container_width=True)
                    
                    # 显示数据表格（全宽）
                    st.subheader("历史交易数据")
                    # 重命名列名为中文
                    display_df = df.copy()
                    # 确保列名映射正确
                    column_mapping = {
                        'Open': '开盘价',
                        'High': '最高价',
                        'Low': '最低价',
                        'Close': '收盘价',
                        'Volume': '成交量',
                        'Amount': '成交额',
                        'MACD': 'MACD',
                        'Signal': 'MACD信号线',
                        'Histogram': 'MACD柱状图',
                        'RSI': 'RSI',
                        'K': 'KDJ-K',
                        'D': 'KDJ-D',
                        'J': 'KDJ-J',
                        'OBV': 'OBV',
                        'ATR': 'ATR',
                        'BB_Upper': '布林带上轨',
                        'BB_Lower': '布林带下轨',
                        'BB_Middle': '布林带中轨',
                        'Support': '支撑位',
                        'Resistance': '阻力位',
                        'MA5': '5日均线',
                        'MA10': '10日均线',
                        'MA20': '20日均线',
                        'MA30': '30日均线',
                        'MA60': '60日均线',
                        'BB_Width': '布林带宽',
                        'DI+': '+DI',
                        'DI-': '-DI',
                        'ADX': 'ADX',
                        'CCI': 'CCI',
                        'Williams_R': '威廉指标',
                        'TR': 'TR',
                        'BIAS6': '6日乖离率',
                        'BIAS12': '12日乖离率',
                        'BIAS24': '24日乖离率'
                    }
                    display_df = display_df.rename(columns=column_mapping)
                    st.dataframe(display_df.tail())
                
                # 新闻分析标签页
                with tab2:
                    news_analyzer = NewsAnalyzer(stock_symbol, market_type)
                    news_summary = news_analyzer.get_news_summary(days=7)
                    
                    st.subheader("新闻情绪分析")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("新闻总数", news_summary['total_news'])
                    with col2:
                        st.metric("利好新闻", news_summary['sentiment_distribution'].get('正面', 0))
                    with col3:
                        st.metric("利空新闻", news_summary['sentiment_distribution'].get('负面', 0))
                
                # 基本面分析标签页
                with tab3:
                    # 获取公司信息
                    company_info = get_company_info(stock_symbol)
                    if company_info:
                        # 显示公司基本信息
                        st.subheader("公司基本信息")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            for key, value in company_info['basic_info'].items():
                                st.write(f"**{key}:** {value}")
                        
                        # 显示财务指标
                        st.subheader("财务指标")
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("市盈率(PE)", f"{company_info['financial_indicators']['市盈率(PE)']:.2f}")
                            st.metric("市净率(PB)", f"{company_info['financial_indicators']['市净率(PB)']:.2f}")
                        with col2:
                            st.metric("市销率(PS)", f"{company_info['financial_indicators']['市销率(PS)']:.2f}")
                            st.metric("净资产收益率(ROE)", f"{company_info['financial_indicators']['净资产收益率(ROE)']:.2f}%")
                        with col3:
                            st.metric("总资产收益率(ROA)", f"{company_info['financial_indicators']['总资产收益率(ROA)']:.2f}%")
                            st.metric("资产负债率", f"{company_info['financial_indicators']['资产负债率']:.2f}%")
                        with col4:
                            st.metric("流动比率", f"{company_info['financial_indicators']['流动比率']:.2f}")
                        
                        # 显示行业对比
                        st.subheader("行业对比分析")
                        industry_comparison = get_industry_comparison(stock_symbol)
                        if industry_comparison is not None:
                            # 计算行业平均值
                            industry_avg = industry_comparison.mean()
                            
                            # 创建对比图表
                            fig = go.Figure()
                            fig.add_trace(go.Bar(
                                name='行业平均',
                                x=['PE', 'PB', 'PS', 'ROE', 'ROA'],
                                y=[industry_avg['pe'], industry_avg['pb'], industry_avg['ps'], 
                                   industry_avg['roe'], industry_avg['roa']]
                            ))
                            fig.add_trace(go.Bar(
                                name='当前公司',
                                x=['PE', 'PB', 'PS', 'ROE', 'ROA'],
                                y=[company_info['financial_indicators']['市盈率(PE)'],
                                company_info['financial_indicators']['市净率(PB)'],
                                company_info['financial_indicators']['市销率(PS)'],
                                company_info['financial_indicators']['净资产收益率(ROE)'],
                                company_info['financial_indicators']['总资产收益率(ROA)']]
                            ))
                            
                            fig.update_layout(
                                title='与行业平均水平对比',
                                barmode='group',
                                height=400
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)
                        
                        # 显示股东结构
                        st.subheader("股东结构分析")
                        shareholder_data = get_shareholder_structure(stock_symbol)
                        if shareholder_data:
                            # 显示十大股东
                            st.write("**十大股东**")
                            st.dataframe(shareholder_data['top10_holders'])
                            
                            # 显示十大流通股东
                            st.write("**十大流通股东**")
                            st.dataframe(shareholder_data['top10_float_holders'])
                            
                            # 创建股东结构饼图
                            fig = go.Figure(data=[go.Pie(
                                labels=shareholder_data['top10_holders']['holder_name'],
                                values=shareholder_data['top10_holders']['hold_ratio'],
                                hole=.3
                            )])
                            
                            fig.update_layout(
                                title='十大股东持股比例',
                                height=400
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error("无法获取公司信息，请检查股票代码是否正确")

                # 战法分析标签页
                with tab6:
                    st.header("战法分析")
                    
                    # 创建三列布局
                    col1, col2, col3 = st.columns([1, 2, 1])
                    
                    with col2:
                        # 选择战法类型
                        strategy_type = st.selectbox(
                            "选择战法类型",
                            ["低吸战法", "龙头战法", "首板战法", "接力战法"]
                        )
                        
                        # 创建分析器实例
                        analyzer = StrategyAnalyzer()
                        
                        # 刷新按钮
                        if st.button("开始分析", type="primary"):
                            with st.spinner("正在分析中..."):
                                # 进度条
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                # 根据选择的战法类型进行分析
                                if strategy_type == "低吸战法":
                                    results = analyzer.low_suction_strategy()
                                elif strategy_type == "龙头战法":
                                    results = analyzer.leader_strategy()
                                elif strategy_type == "首板战法":
                                    results = analyzer.first_board_strategy()
                                else:  # 接力战法
                                    results = analyzer.relay_strategy()
                                
                                # 更新进度条
                                progress_bar.progress(100)
                                status_text.text("分析完成！")
                                
                                # 显示结果
                                if results:
                                    # 转换为DataFrame以便显示
                                    df_results = pd.DataFrame(results)
                                    display_columns = ['code', 'name', 'price', 'rsi', 'volume_ratio']
                                    st.dataframe(df_results[display_columns])
                                    
                                    # 显示统计信息
                                    st.subheader("统计信息")
                                    st.write(f"RSI平均值: {df_results['rsi'].mean():.2f}")
                                    st.write(f"成交量比率平均值: {df_results['volume_ratio'].mean():.2f}")
                                    st.write(f"价格范围: {df_results['price'].min():.2f} - {df_results['price'].max():.2f}")
                                else:
                                    st.warning("未找到符合条件的股票")
                        
                        # 停止按钮
                        if st.button("停止分析", type="secondary"):
                            analyzer.stop_analysis()
                            st.success("分析已停止")
                            
                        # 显示当前进度
                        if analyzer.progress > 0:
                            st.progress(analyzer.progress / 100)
                            st.write(f"已分析: {analyzer.analyzed_stocks}/{analyzer.total_stocks} 只股票")

                # 主力行为分析标签页
                with tab4:
                    st.header("主力行为分析")
                    
                    if volume_analysis_button:
                        with st.spinner("正在进行主力行为分析，请稍候..."):
                            # 创建分析器实例
                            analyzer = StrategyAnalyzer()
                            
                            # 获取股票数据
                            df = get_stock_data(stock_symbol, start_date, end_date, market_type)
                            
                            if df is not None:
                                # 计算技术指标
                                df = calculate_indicators(df)
                                
                                if df is not None:
                                    # 获取最新数据
                                    latest = df.iloc[-1]
                                    prev = df.iloc[-2]
                                    
                                    # 计算价格变化
                                    price_change = (latest['Close'] - prev['Close']) / prev['Close']
                                    
                                    # 计算成交量变化
                                    volume_change = latest['Volume'] / df['Volume'].rolling(window=5).mean().iloc[-1]
                                    
                                    # 计算换手率变化
                                    turnover_change = latest['Volume'] / df['Volume'].rolling(window=5).mean().iloc[-1]
                                    
                                    # 主力出货特征：
                                    # 1. 价格下跌
                                    # 2. 成交量放大
                                    # 3. 换手率显著增加
                                    # 4. 收盘价低于开盘价
                                    is_selling = (
                                        price_change < 0 and  # 价格下跌
                                        volume_change > 1.5 and  # 成交量放大
                                        turnover_change > 1.5 and  # 换手率显著增加
                                        latest['Close'] < latest['Open']  # 收盘价低于开盘价
                                    )
                                    
                                    # 主力吃单特征：
                                    # 1. 价格上涨
                                    # 2. 成交量放大
                                    # 3. 换手率显著增加
                                    # 4. 收盘价高于开盘价
                                    # 5. 收盘价接近最高价
                                    is_buying = (
                                        price_change > 0 and  # 价格上涨
                                        volume_change > 1.5 and  # 成交量放大
                                        turnover_change > 1.5 and  # 换手率显著增加
                                        latest['Close'] > latest['Open'] and  # 收盘价高于开盘价
                                        (latest['Close'] - latest['Low']) / (latest['High'] - latest['Low']) > 0.8  # 收盘价接近最高价
                                    )
                                    
                                    # 显示分析结果
                                    st.subheader("主力行为分析结果")
                                    
                                    if is_selling:
                                        st.error("主力出货特征明显")
                                        st.write("""
                                        ### 主力出货特征：
                                        1. 价格下跌
                                        2. 成交量放大
                                        3. 换手率显著增加
                                        4. 收盘价低于开盘价
                                        """)
                                    elif is_buying:
                                        st.success("主力吃单特征明显")
                                        st.write("""
                                        ### 主力吃单特征：
                                        1. 价格上涨
                                        2. 成交量放大
                                        3. 换手率显著增加
                                        4. 收盘价高于开盘价
                                        5. 收盘价接近最高价
                                        """)
                                    else:
                                        st.info("无明显主力行为特征")
                                    
                                    # 显示详细数据
                                    st.subheader("详细数据")
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("价格变化", f"{price_change:.2%}")
                                        st.metric("成交量变化", f"{volume_change:.2f}")
                                    with col2:
                                        st.metric("换手率变化", f"{turnover_change:.2f}")
                                        st.metric("收盘价", format_price(latest['Close'], market_type))
                                    with col3:
                                        st.metric("开盘价", format_price(latest['Open'], market_type))
                                        st.metric("最高价", format_price(latest['High'], market_type))
                                        st.metric("最低价", format_price(latest['Low'], market_type))
                                    
                                    # 显示K线图
                                    st.subheader("K线图")
                                    fig = go.Figure()
                                    fig.add_trace(go.Candlestick(
                                        x=df.index,
                                        open=df['Open'],
                                        high=df['High'],
                                        low=df['Low'],
                                        close=df['Close'],
                                        name='K线'
                                    ))
                                    fig.update_layout(
                                        title='K线图',
                                        yaxis_title='价格',
                                        xaxis_title='日期',
                                        height=500,
                                        xaxis_rangeslider_visible=False
                                    )
                                    st.plotly_chart(fig, use_container_width=True)
                                else:
                                    st.error("计算技术指标失败")
                            else:
                                st.error("获取股票数据失败")
                    else:
                        st.info('点击侧边栏的"主力行为分析"按钮开始分析')

except Exception as e:
    st.error(f"程序运行出错: {str(e)}") 
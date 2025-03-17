import pandas as pd
import numpy as np
import baostock as bs
import talib
import threading
from queue import Queue
import time

class StrategyAnalyzer:
    """
    股票战法分析器类
    """
    def __init__(self):
        """
        初始化战法分析器
        """
        self.stop_flag = False
        self.progress = 0
        self.total_stocks = 0
        self.analyzed_stocks = 0
        self.results = []
        self._lock = threading.Lock()
    
    def stop_analysis(self):
        """
        停止分析
        """
        self.stop_flag = True
    
    def update_progress(self, value):
        """
        更新进度
        
        Args:
            value (int): 进度值
        """
        with self._lock:
            self.progress = value
    
    def get_stock_list(self):
        """
        获取A股股票列表
        
        Returns:
            pd.DataFrame: 股票列表
        """
        try:
            # 登录系统
            bs.login()
            # 获取证券信息
            rs = bs.query_stock_basic(code_name="")
            if rs.error_code != '0':
                print(f'获取股票列表失败: {rs.error_msg}')
                return []
                
            # 获取数据
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
                
            # 转换为DataFrame
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 只保留主板股票（以6或0开头的股票）
            df = df[df['code'].str.startswith(('6', '0'))]
            
            # 登出系统
            bs.logout()
            
            return df['code'].tolist()
            
        except Exception as e:
            print(f'获取股票列表出错: {str(e)}')
            return []
    
    def get_stock_data(self, stock_code):
        """
        获取股票历史数据
        
        Args:
            stock_code (str): 股票代码
            
        Returns:
            pd.DataFrame: 股票数据
        """
        try:
            # 登录系统
            bs.login()
            
            # 获取股票数据
            rs = bs.query_history_k_data_plus(
                stock_code,
                "date,open,high,low,close,volume,amount,turn",
                start_date='2023-01-01',
                frequency="d"
            )
            
            if rs.error_code != '0':
                print(f'获取股票数据失败: {rs.error_msg}')
                return None
                
            # 获取数据
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
                
            # 转换为DataFrame
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn']:
                df[col] = pd.to_numeric(df[col])
                
            # 登出系统
            bs.logout()
            
            return df
            
        except Exception as e:
            print(f'获取股票数据出错: {str(e)}')
            return None
    
    def analyze_stock(self, stock_code, strategy_func):
        """
        分析单个股票
        
        Args:
            stock_code (str): 股票代码
            strategy_func (function): 策略函数
        """
        if self.stop_flag:
            return
            
        try:
            # 获取股票数据
            df = self.get_stock_data(stock_code)
            if df is None or len(df) < 60:
                return
                
            # 计算技术指标
            df['MA5'] = talib.MA(df['close'], timeperiod=5)
            df['MA10'] = talib.MA(df['close'], timeperiod=10)
            df['MA20'] = talib.MA(df['close'], timeperiod=20)
            df['MA60'] = talib.MA(df['close'], timeperiod=60)
            
            # 计算MACD
            macd, macd_signal, macd_hist = talib.MACD(df['close'])
            df['MACD'] = macd
            df['MACD_SIGNAL'] = macd_signal
            df['MACD_HIST'] = macd_hist
            
            # 计算RSI
            df['RSI'] = talib.RSI(df['close'], timeperiod=14)
            
            # 计算布林带
            upper, middle, lower = talib.BBANDS(df['close'], timeperiod=20)
            df['BB_UPPER'] = upper
            df['BB_MIDDLE'] = middle
            df['BB_LOWER'] = lower
            
            # 计算KDJ
            slowk, slowd = talib.STOCH(df['high'], df['low'], df['close'])
            df['KDJ_K'] = slowk
            df['KDJ_D'] = slowd
            df['KDJ_J'] = 3 * slowk - 2 * slowd
            
            # 计算成交量指标
            df['VOL_MA5'] = talib.MA(df['volume'], timeperiod=5)
            df['VOL_MA10'] = talib.MA(df['volume'], timeperiod=10)
            
            # 计算换手率指标
            df['TURN_MA5'] = talib.MA(df['turn'], timeperiod=5)
            df['TURN_MA10'] = talib.MA(df['turn'], timeperiod=10)
            
            # 应用策略
            if strategy_func(df):
                self.results.append({
                    'code': stock_code,
                    'name': stock_code,  # 这里可以添加获取股票名称的逻辑
                    'price': df['close'].iloc[-1],
                    'rsi': df['RSI'].iloc[-1],
                    'volume_ratio': df['volume'].iloc[-1] / df['VOL_MA5'].iloc[-1],
                    'turnover_rate': df['turn'].iloc[-1],
                    'action': '主力出货' if df['close'].iloc[-1] < df['close'].iloc[-2] else '主力吃单'
                })
                
        except Exception as e:
            print(f'分析股票 {stock_code} 时出错: {str(e)}')
            
        finally:
            with self._lock:
                self.analyzed_stocks += 1
                self.update_progress(int(self.analyzed_stocks / self.total_stocks * 100))
                
    def analyze_stocks_parallel(self, stock_list, strategy_func, max_threads=3):
        """
        并行分析多个股票
        
        Args:
            stock_list (list): 股票列表
            strategy_func (function): 策略函数
            max_threads (int): 最大线程数
            
        Returns:
            list: 分析结果
        """
        self.results = []
        self.analyzed_stocks = 0
        self.total_stocks = len(stock_list)
        self.stop_flag = False
        
        # 创建线程池
        threads = []
        for i in range(0, len(stock_list), max_threads):
            if self.stop_flag:
                break
                
            batch = stock_list[i:i + max_threads]
            for stock_code in batch:
                if self.stop_flag:
                    break
                    
                thread = threading.Thread(
                    target=self.analyze_stock,
                    args=(stock_code, strategy_func)
                )
                thread.start()
                threads.append(thread)
                
            # 等待当前批次完成
            for thread in threads:
                thread.join()
                
            threads = []
            
    def low_suction_strategy(self):
        """
        低吸战法
        
        Returns:
            list: 符合低吸战法的股票列表
        """
        def strategy(df):
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 条件1：价格在布林带下轨附近
            price_near_lower = latest['close'] <= latest['BB_LOWER'] * 1.02
            
            # 条件2：RSI超卖
            rsi_oversold = latest['RSI'] < 30
            
            # 条件3：MACD金叉
            macd_golden_cross = (prev['MACD'] < prev['MACD_SIGNAL'] and 
                               latest['MACD'] > latest['MACD_SIGNAL'])
            
            # 条件4：成交量放大
            volume_increase = latest['volume'] > latest['VOL_MA5'] * 1.5
            
            return price_near_lower and rsi_oversold and macd_golden_cross and volume_increase
            
        # 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return []
            
        # 分析股票
        self.analyze_stocks_parallel(stock_list, strategy)
        return self.results
    
    def leader_strategy(self):
        """
        龙头战法
        
        Returns:
            list: 符合龙头战法的股票列表
        """
        def strategy(df):
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 条件1：价格创历史新高
            price_new_high = latest['close'] > df['close'].max()
            
            # 条件2：RSI强势
            rsi_strong = latest['RSI'] > 70
            
            # 条件3：MACD强势
            macd_strong = latest['MACD'] > latest['MACD_SIGNAL']
            
            # 条件4：成交量放大
            volume_increase = latest['volume'] > latest['VOL_MA5'] * 1.2
            
            return price_new_high and rsi_strong and macd_strong and volume_increase
            
        # 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return []
            
        # 分析股票
        self.analyze_stocks_parallel(stock_list, strategy)
        return self.results
    
    def first_board_strategy(self):
        """
        首板战法
        
        Returns:
            list: 符合首板战法的股票列表
        """
        def strategy(df):
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 条件1：涨停
            price_limit_up = (latest['close'] - prev['close']) / prev['close'] > 0.095
            
            # 条件2：成交量放大
            volume_increase = latest['volume'] > latest['VOL_MA5'] * 2
            
            # 条件3：RSI强势
            rsi_strong = latest['RSI'] > 60
            
            return price_limit_up and volume_increase and rsi_strong
            
        # 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return []
            
        # 分析股票
        self.analyze_stocks_parallel(stock_list, strategy)
        return self.results
    
    def relay_strategy(self):
        """
        接力战法
        
        Returns:
            list: 符合接力战法的股票列表
        """
        def strategy(df):
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 条件1：连续上涨
            price_up = latest['close'] > prev['close']
            
            # 条件2：RSI强势
            rsi_strong = latest['RSI'] > 50
            
            # 条件3：MACD强势
            macd_strong = latest['MACD'] > latest['MACD_SIGNAL']
            
            # 条件4：成交量放大
            volume_increase = latest['volume'] > latest['VOL_MA5'] * 1.3
            
            return price_up and rsi_strong and macd_strong and volume_increase
            
        # 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return []
            
        # 分析股票
        self.analyze_stocks_parallel(stock_list, strategy)
        return self.results
    
    def volume_analysis_strategy(self):
        """
        通过成交量和换手率分析主力行为
        
        Returns:
            list: 符合主力行为特征的股票列表
        """
        def strategy(df):
            # 获取最新数据
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 计算价格变化
            price_change = (latest['close'] - prev['close']) / prev['close']
            
            # 计算成交量变化
            volume_change = latest['volume'] / latest['VOL_MA5']
            
            # 计算换手率变化
            turnover_change = latest['turn'] / latest['TURN_MA5']
            
            # 主力出货特征：
            # 1. 价格下跌
            # 2. 成交量放大
            # 3. 换手率显著增加
            # 4. 收盘价低于开盘价
            is_selling = (
                price_change < 0 and  # 价格下跌
                volume_change > 1.5 and  # 成交量放大
                turnover_change > 1.5 and  # 换手率显著增加
                latest['close'] < latest['open']  # 收盘价低于开盘价
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
                latest['close'] > latest['open'] and  # 收盘价高于开盘价
                (latest['close'] - latest['low']) / (latest['high'] - latest['low']) > 0.8  # 收盘价接近最高价
            )
            
            return is_selling or is_buying
            
        # 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return []
            
        # 分析股票
        self.analyze_stocks_parallel(stock_list, strategy)
        return self.results 
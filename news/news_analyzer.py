import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
import baostock as bs
import json
import time
import random

class NewsAnalyzer:
    """
    股票新闻分析器类
    """
    def __init__(self, symbol, market_type="A股"):
        """
        初始化新闻分析器
        
        Args:
            symbol (str): 股票代码
            market_type (str): 市场类型
        """
        self.symbol = symbol
        self.market_type = market_type
        if market_type == "A股":
            self.stock = None  # A股新闻将通过其他方式获取
        else:
            self.stock = yf.Ticker(symbol)
        
        # 设置请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        }
        
        # 初始化会话
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_eastmoney_news(self, days=7):
        """
        从东方财富网获取新闻
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            pd.DataFrame: 新闻数据
        """
        try:
            url = f"http://np-anotice-stock.eastmoney.com/api/security/announcement/getAnnList"
            params = {
                "cb": "jQuery",
                "sr": -1,
                "page_size": 50,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "f_node": 0,
                "s_node": 0,
                "stock": self.symbol
            }
            
            response = self.session.get(url, params=params)
            text = response.text
            
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                try:
                    start_idx = text.find('{')
                    end_idx = text.rfind('}') + 1
                    if start_idx != -1 and end_idx != -1:
                        json_str = text[start_idx:end_idx]
                        data = json.loads(json_str)
                    else:
                        return pd.DataFrame()
                except:
                    return pd.DataFrame()
            
            if not isinstance(data, dict) or 'data' not in data or 'list' not in data['data']:
                return pd.DataFrame()
                
            news_list = data['data']['list']
            if not news_list:
                return pd.DataFrame()
                
            df = pd.DataFrame(news_list)
            
            if 'notice_date' in df.columns:
                df['datetime'] = pd.to_datetime(df['notice_date'])
            else:
                df['datetime'] = pd.to_datetime('now')
            
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df['datetime'] >= cutoff_date]
            
            if 'title' not in df.columns:
                df['title'] = '无标题'
            
            df['source'] = '东方财富网'
            df = df[['title', 'datetime', 'source']]
            
            return df
            
        except Exception as e:
            print(f"从东方财富网获取新闻时出错: {str(e)}")
            return pd.DataFrame()
    
    def get_sina_news(self, days=7):
        """
        从新浪财经获取新闻
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            pd.DataFrame: 新闻数据
        """
        try:
            # 新浪财经新闻API
            url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
            params = {
                "symbol": self.symbol,
                "scale": 240,
                "ma": "no",
                "datalen": 1
            }
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            if not data:
                return pd.DataFrame()
            
            # 获取新闻列表
            news_url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getNewsList"
            news_params = {
                "symbol": self.symbol,
                "page": 1,
                "num": 50
            }
            
            response = self.session.get(news_url, params=news_params)
            news_data = response.json()
            
            if not news_data:
                return pd.DataFrame()
            
            df = pd.DataFrame(news_data)
            if 'time' in df.columns:
                df['datetime'] = pd.to_datetime(df['time'])
            else:
                df['datetime'] = pd.to_datetime('now')
            
            if 'title' in df.columns:
                df['title'] = df['title']
            else:
                df['title'] = '无标题'
            
            df['source'] = '新浪财经'
            
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df['datetime'] >= cutoff_date]
            
            return df[['title', 'datetime', 'source']]
            
        except Exception as e:
            print(f"从新浪财经获取新闻时出错: {str(e)}")
            return pd.DataFrame()
    
    def get_xueqiu_news(self, days=7):
        """
        从雪球获取新闻
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            pd.DataFrame: 新闻数据
        """
        try:
            # 首先获取cookie
            self.session.get('https://xueqiu.com')
            time.sleep(1)  # 等待一下
            
            # 雪球新闻API
            url = f"https://xueqiu.com/statuses/search.json"
            params = {
                "count": 50,
                "comment": 0,
                "symbol": self.symbol,
                "source": "all",
                "sort": "time",
                "page": 1
            }
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            if not data or 'list' not in data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data['list'])
            if 'created_at' in df.columns:
                df['datetime'] = pd.to_datetime(df['created_at'], unit='ms')
            else:
                df['datetime'] = pd.to_datetime('now')
            
            if 'text' in df.columns:
                df['title'] = df['text']
            else:
                df['title'] = '无标题'
            
            df['source'] = '雪球'
            
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df['datetime'] >= cutoff_date]
            
            return df[['title', 'datetime', 'source']]
            
        except Exception as e:
            print(f"从雪球获取新闻时出错: {str(e)}")
            return pd.DataFrame()
    
    def get_10jqka_news(self, days=7):
        """
        从同花顺获取新闻
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            pd.DataFrame: 新闻数据
        """
        try:
            # 同花顺新闻API
            url = f"http://news.10jqka.com.cn/tapp/news/push/stock/"
            params = {
                "page": 1,
                "tag": "news_stock",
                "track": "website",
                "num": 50,
                "list": self.symbol
            }
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            if not data or 'data' not in data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data['data'])
            
            # 处理时间字段
            if 'ctime' in df.columns:
                df['datetime'] = pd.to_datetime(df['ctime'])
            elif 'time' in df.columns:
                df['datetime'] = pd.to_datetime(df['time'])
            else:
                df['datetime'] = pd.to_datetime('now')
            
            # 处理标题字段
            if 'title' in df.columns:
                df['title'] = df['title']
            else:
                df['title'] = '无标题'
            
            df['source'] = '同花顺'
            
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df['datetime'] >= cutoff_date]
            
            return df[['title', 'datetime', 'source']]
            
        except Exception as e:
            print(f"从同花顺获取新闻时出错: {str(e)}")
            return pd.DataFrame()
    
    def get_news(self, days=7):
        """
        获取股票相关新闻
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            pd.DataFrame: 新闻数据
        """
        try:
            if self.market_type == "A股":
                # 从多个来源获取新闻
                dfs = []
                
                # 东方财富网
                df_eastmoney = self.get_eastmoney_news(days)
                if not df_eastmoney.empty:
                    dfs.append(df_eastmoney)
                    time.sleep(1)  # 添加延时避免请求过快
                
                # 新浪财经
                df_sina = self.get_sina_news(days)
                if not df_sina.empty:
                    dfs.append(df_sina)
                    time.sleep(1)
                
                # 雪球
                df_xueqiu = self.get_xueqiu_news(days)
                if not df_xueqiu.empty:
                    dfs.append(df_xueqiu)
                    time.sleep(1)
                
                # 同花顺
                df_10jqka = self.get_10jqka_news(days)
                if not df_10jqka.empty:
                    dfs.append(df_10jqka)
                
                if not dfs:
                    return pd.DataFrame()
                
                # 合并所有新闻源的数据
                df = pd.concat(dfs, ignore_index=True)
                
                # 去重
                df = df.drop_duplicates(subset=['title'])
                
                # 按时间排序
                df = df.sort_values('datetime', ascending=False)
                
                return df
            else:
                news = self.stock.news
                df = pd.DataFrame(news)
                df['datetime'] = pd.to_datetime(df['providerPublishTime'], unit='s')
                df['source'] = 'Yahoo Finance'
                
                cutoff_date = datetime.now() - timedelta(days=days)
                df = df[df['datetime'] >= cutoff_date]
                
                return df[['title', 'datetime', 'source']]
                
        except Exception as e:
            print(f"获取新闻时出错: {str(e)}")
            return pd.DataFrame()
    
    def analyze_sentiment(self, text):
        """
        简单的情绪分析
        
        Args:
            text (str): 新闻文本
            
        Returns:
            str: 情绪分析结果
        """
        # 扩展情绪词典
        positive_words = [
            '增长', '上涨', '突破', '创新', '利好', '突破', '成功', '盈利', '增长', '扩张',
            '突破', '创新高', '增长', '突破', '创新', '利好', '突破', '成功', '盈利', '增长',
            '扩张', '突破性', '突破性进展', '突破性创新', '突破性发展', '突破性成果',
            '突破性技术', '突破性产品', '突破性服务', '突破性解决方案', '突破性商业模式',
            '突破性市场', '突破性客户', '突破性合作', '突破性协议', '突破性订单',
            '突破性项目', '突破性工程', '突破性建设', '突破性投资', '突破性融资',
            '突破性并购', '突破性重组', '突破性改革', '突破性创新', '突破性发展',
            '突破性进步', '突破性提升', '突破性改善', '突破性优化', '突破性升级',
            '突破性转型', '突破性升级', '突破性改造', '突破性创新', '突破性发展'
        ]
        
        negative_words = [
            '下跌', '风险', '问题', '危机', '下滑', '失败', '亏损', '下降', '收缩',
            '下跌', '风险', '问题', '危机', '下滑', '失败', '亏损', '下降', '收缩',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示',
            '风险提示', '风险预警', '风险警示', '风险提示', '风险预警', '风险警示'
        ]
        
        text = text.lower()
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        
        if pos_count > neg_count:
            return '利好'
        elif neg_count > pos_count:
            return '利空'
        else:
            return '中性'
    
    def get_news_summary(self, days=7):
        """
        获取新闻摘要
        
        Args:
            days (int): 获取最近几天的新闻
            
        Returns:
            dict: 新闻摘要统计
        """
        try:
            df = self.get_news(days)
            
            if df.empty:
                return {
                    'total_news': 0,
                    'sentiment_distribution': {'利好': 0, '利空': 0, '中性': 0},
                    'latest_news': [],
                    'source_distribution': {}
                }
            
            # 添加情绪分析
            df['sentiment'] = df['title'].apply(self.analyze_sentiment)
            
            # 统计情绪分布
            sentiment_counts = df['sentiment'].value_counts()
            
            # 统计新闻来源分布
            source_counts = df['source'].value_counts()
            
            # 获取最新新闻
            latest_news = df[['title', 'datetime', 'sentiment', 'source']].head(5).to_dict('records')
            
            return {
                'total_news': len(df),
                'sentiment_distribution': sentiment_counts.to_dict(),
                'latest_news': latest_news,
                'source_distribution': source_counts.to_dict()
            }
        except Exception as e:
            print(f"生成新闻摘要时出错: {str(e)}")
            return {
                'total_news': 0,
                'sentiment_distribution': {'利好': 0, '利空': 0, '中性': 0},
                'latest_news': [],
                'source_distribution': {}
            } 
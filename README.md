# 股票分析应用

基于Streamlit开发的股票分析工具，提供实时行情、技术分析和主力资金分析等功能。

## 功能特点

- K线图展示
- 技术指标分析
- 主力资金分析
- 分析报告生成
- 战法分析
- 实时数据更新

## 部署说明

1. 环境要求
   - Python 3.9+
   - 依赖包见`requirements.txt`

2. 配置说明
   - 需要配置Tushare API Token
   - 支持自定义主题设置

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 在线访问

应用已部署在Streamlit Cloud上，访问地址：[您的应用URL]

## 注意事项

- 确保已正确配置API密钥
- 建议使用Chrome浏览器访问
- 数据更新频率为5秒 
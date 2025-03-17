import os
import sys
import subprocess
import webbrowser
import time

def run_app():
    """
    启动股票分析系统
    """
    try:
        # 启动Streamlit应用
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待应用启动
        time.sleep(3)
        
        # 打开浏览器
        webbrowser.open('http://localhost:8501')
        
        # 等待进程结束
        process.wait()
        
    except Exception as e:
        print(f"启动应用时出错: {str(e)}")
        input("按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    run_app() 
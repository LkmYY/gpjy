from subprocess import Popen
import os

def handler(event, context):
    if not os.environ.get("STREAMLIT_STARTED"):
        os.environ["STREAMLIT_STARTED"] = "1"
        process = Popen(
            ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
        )
        
    return {
        "statusCode": 200,
        "body": "Streamlit app is running"
    } 
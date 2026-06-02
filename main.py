from flask import Flask

import threading

app = Flask(__name__)

@app.route("/")

def home():

    return "Bot đang chạy!"

def run_web():

    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web).start()

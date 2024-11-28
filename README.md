# Server Side Setup

```shell
# wget https://github.com/Azure-Samples/aoai-realtime-audio-sdk/releases/download/py%2Fv0.5.2/rtclient-0.5.2-py3-none-any.whl

# Optional
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install rtclient-0.5.2-py3-none-any.whl

python app.py

# or
fastapi dev main.py
```

# Frontend Setup

> 打开`client.html`

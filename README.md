# Configuration

> Create `.env` file and then fill out fields

# Server Side Setup

```shell
# wget https://github.com/Azure-Samples/aoai-realtime-audio-sdk/releases/download/py%2Fv0.5.2/rtclient-0.5.2-py3-none-any.whl

# Optional
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install rtclient-0.5.2-py3-none-any.whl

# dev mode
uvicorn main:app --reload

# prod mode
uvicorn main:app
```

# Frontend

> open `http://127.0.0.1:8000/`

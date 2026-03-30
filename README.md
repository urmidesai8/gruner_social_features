# gruner_social_features

FastAPI image-chatbot demo.

## Setup
1. Install deps
   - `pip install -r requirements.txt`
2. Set your Hugging Face token
   - `export HF_TOKEN="..."`

## Run
1. Start the server
   - `python main.py`
2. Open the dummy UI
   - `http://localhost:8000/`

## API
- `GET /api/models` - list available models
- `POST /api/chat` - generate an image from the last user message
  - body: `{ "model": "...", "messages": [{"role":"user","content":"..."}] }`
- `POST /api/generate-image` - generate image directly
  - body: `{ "model": "...", "prompt": "..." }`
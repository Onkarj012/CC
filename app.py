import os, json, random, requests
from flask import Flask, render_template, request, jsonify
import boto3

app = Flask(__name__)

# Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CHARACTER_MODEL = os.getenv("CHARACTER_MODEL", "openrouter/anthropic/claude-3.5-sonnet")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# Load characters
with open("characters.json") as f:
    characters = json.load(f)

# S3 client
s3_client = boto3.client("s3", region_name=AWS_REGION)

def fetch_avatar_url(key):
    try:
        return s3_client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": key}, ExpiresIn=3600)
    except Exception:
        return None

@app.route("/")
def index():
    chars = []
    for c in characters:
        avatar_url = fetch_avatar_url(c["avatar"]) if S3_BUCKET else None
        chars.append({**c, "avatar_url": avatar_url})
    return render_template("index.html", characters=chars)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message", "")
    char_name = data.get("character", "Naruto")
    char = next((c for c in characters if c["name"] == char_name), characters[0])

    if DEMO_MODE:
        return jsonify({"reply": f"As {char['name']}: {random.choice(['Believe it!', 'Let’s train harder!', 'You can do it!'])}"})

    prompt = f"""
        You are {char['name']} from {char['universe']}.
        Stay in character and answer like {char['name']} would.
        """


    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json={
        "model": CHARACTER_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    })

    if resp.status_code == 200:
        reply = resp.json()["choices"][0]["message"]["content"]
    else:
        reply = f"[Error from OpenRouter: {resp.text}]"

    return jsonify({"reply": reply})

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

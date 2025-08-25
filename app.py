import os, json, random, requests, time
from flask import Flask, render_template, request, jsonify
import boto3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Config
CHUTES_API_KEY = os.getenv("CHUTES_API_KEY")
CHUTES_BASE_URL = os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1/chat/completions")

S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CHARACTER_MODEL = os.getenv("CHARACTER_MODEL", "deepseek-ai/DeepSeek-V3-0324")  # update to your desired model
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
        return jsonify({"reply": f"As {char['name']}: {random.choice(['Believe it!', 'Lets train harder!', 'You can do it!'])}"})

    # System prompt
    system_prompt = f"""You are {char['name']}. You possess the following traits: {char['traits']}
    Your communication style is: {char['style']}
    Respond naturally, staying in character at all times.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ]

    headers = {
    "Authorization": f"Bearer {CHUTES_API_KEY}",
    "Content-Type": "application/json"
}


    payload = {
        "model": CHARACTER_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 500
    }

    try:
        resp = requests.post(CHUTES_BASE_URL, headers=headers, json=payload, timeout=30)

        if resp.status_code == 200:
            resp_json = resp.json()
            reply = resp_json["choices"][0]["message"]["content"]
            return jsonify({"reply": reply})

        elif resp.status_code == 429:  # rate limit
            return jsonify({"reply": "Too many requests. Please try again later."})

        else:
            try:
                error_msg = resp.json().get("error", {}).get("message", f"Error {resp.status_code}")
            except:
                error_msg = f"Error: {resp.status_code}"
            return jsonify({"reply": f"Sorry, there was an error: {error_msg}"})

    except requests.exceptions.RequestException:
        return jsonify({"reply": "Network error. Please try again."})


@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

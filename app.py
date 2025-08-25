import os, json, random, requests, time, uuid
from flask import Flask, render_template, request, jsonify, make_response
import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Custom template filter for timestamps
@app.template_filter('datetime')
def format_datetime(timestamp):
    return time.strftime('%I:%M %p', time.localtime(timestamp))

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

# S3 client initialization with error handling
try:
    s3_client = boto3.client("s3", region_name=AWS_REGION)
    # Test the connection by listing buckets
    s3_client.list_buckets()
except Exception as e:
    print(f"Warning: Failed to initialize S3 client: {e}")
    print("Chat history will not be saved.")
    s3_client = None

def fetch_avatar_url(key):
    try:
        return s3_client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": key}, ExpiresIn=3600)
    except Exception:
        return None

def load_chat_history(user_id):
    if not S3_BUCKET:
        return []
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=f"chat_history/{user_id}.json")
        history = json.loads(response['Body'].read().decode('utf-8'))
        return history
    except ClientError as e:
        error_code = e.response['Error'].get('Code', '')
        if error_code == 'NoSuchKey':
            # This is normal for new users
            return []
        elif error_code == 'NoSuchBucket':
            print(f"Error: The S3 bucket '{S3_BUCKET}' does not exist")
        elif error_code == 'AccessDenied':
            print("Error: Access denied to S3 bucket. Please check your AWS credentials and permissions")
        else:
            print(f"AWS Error: {error_code} - {e}")
        return []
    except EndpointConnectionError as e:
        print(f"S3 Connection Error: Please check your AWS_REGION configuration. {e}")
        return []
    except Exception as e:
        print(f"Error loading chat history: {e}")
        return []

def save_chat_history(user_id, history):
    if not S3_BUCKET:
        return
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"chat_history/{user_id}.json",
            Body=json.dumps(history, ensure_ascii=False),
            ContentType='application/json'
        )
    except ClientError as e:
        error_code = e.response['Error'].get('Code', '')
        if error_code == 'NoSuchBucket':
            print(f"Error: The S3 bucket '{S3_BUCKET}' does not exist")
        elif error_code == 'AccessDenied':
            print("Error: Access denied to S3 bucket. Please check your AWS credentials and permissions")
        else:
            print(f"AWS Error: {error_code} - {e}")
    except EndpointConnectionError as e:
        print(f"S3 Connection Error: Please check your AWS_REGION configuration. {e}")
    except Exception as e:
        print(f"Error saving chat history: {e}")

@app.route("/get_character_image", methods=['POST'])
def get_character_image():
    data = request.get_json()
    character = data.get('character')
    if not character:
        return jsonify({'error': 'Character name is required'}), 400

    # Generate the image key - convert to lowercase and replace spaces with underscores
    image_key = f"character_images/{character.lower().replace(' ', '_')}.jpg"

    try:
        if s3_client and S3_BUCKET:
            # Check if image exists in S3
            try:
                s3_client.head_object(Bucket=S3_BUCKET, Key=image_key)
                # Generate a pre-signed URL for the image
                image_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': image_key},
                    ExpiresIn=3600  # URL expires in 1 hour
                )
                return jsonify({'image_url': image_url})
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Image doesn't exist
                    return jsonify({'image_url': None}), 404
                else:
                    print(f"S3 error: {e}")
                    return jsonify({'error': 'Failed to fetch image'}), 500
        else:
            return jsonify({'error': 'S3 not configured'}), 500
    except Exception as e:
        print(f"Error handling character image: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/")
def index():
    # Generate a simple user ID (in production, use proper user authentication)
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
    
    chars = []
    for c in characters:
        avatar_url = fetch_avatar_url(c["avatar"]) if S3_BUCKET else None
        chars.append({**c, "avatar_url": avatar_url})
    
    # Load chat history
    chat_history = load_chat_history(user_id) if S3_BUCKET else []
    
    response = make_response(render_template("index.html", characters=chars, chat_history=chat_history))
    if not request.cookies.get('user_id'):
        response.set_cookie('user_id', user_id, max_age=31536000)  # 1 year expiry
    return response

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message", "")
    char_name = data.get("character", "Naruto")
    char = next((c for c in characters if c["name"] == char_name), characters[0])
    user_id = request.cookies.get('user_id')

    # Load existing chat history
    chat_history = load_chat_history(user_id) if S3_BUCKET and user_id else []
    
    if DEMO_MODE:
        reply = f"As {char['name']}: {random.choice(['Believe it!', 'Lets train harder!', 'You can do it!'])}"
        
    else:
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
            
            elif resp.status_code == 429:  # rate limit
                reply = "Too many requests. Please try again later."
            
            else:
                try:
                    error_msg = resp.json().get("error", {}).get("message", f"Error {resp.status_code}")
                except:
                    error_msg = f"Error: {resp.status_code}"
                reply = f"Sorry, there was an error: {error_msg}"

        except requests.exceptions.RequestException:
            reply = "Network error. Please try again."
    
    # Add to chat history
    if S3_BUCKET and user_id:
        chat_history.append({
            "role": "user",
            "content": user_msg,
            "timestamp": time.time()
        })
        chat_history.append({
            "role": "assistant",
            "content": reply,
            "character": char_name,
            "timestamp": time.time()
        })
        # Keep only last 50 messages
        if len(chat_history) > 50:
            chat_history = chat_history[-50:]
        save_chat_history(user_id, chat_history)
    
    return jsonify({"reply": reply})


@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

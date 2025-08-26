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

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=AWS_REGION
)

def setup_s3_bucket():
    """Configure S3 bucket with CORS and public read access"""
    if not S3_BUCKET:
        print("No S3 bucket configured")
        return
    
    try:
        # Configure CORS
        cors_configuration = {
            'CORSRules': [{
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['GET', 'HEAD'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': ['ETag'],
                'MaxAgeSeconds': 3000
            }]
        }
        
        # Set CORS configuration
        s3_client.put_bucket_cors(Bucket=S3_BUCKET, CORSConfiguration=cors_configuration)
        print(f"Successfully configured CORS for bucket: {S3_BUCKET}")

        # Set bucket policy for public read access
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadForGetBucketObjects",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{S3_BUCKET}/character_images/*"
                }
            ]
        }
        
        # Convert policy to JSON string
        bucket_policy_string = json.dumps(bucket_policy)
        
        # Set the bucket policy
        s3_client.put_bucket_policy(Bucket=S3_BUCKET, Policy=bucket_policy_string)
        print(f"Successfully set bucket policy for: {S3_BUCKET}")
        
    except Exception as e:
        print(f"Error configuring S3 bucket: {e}")

# Set up S3 bucket when app starts
setup_s3_bucket()

def configure_s3_cors():
    """Configure CORS for S3 bucket to allow image access"""
    if not S3_BUCKET:
        print("No S3 bucket configured")
        return
    
    try:
        cors_configuration = {
            'CORSRules': [{
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['GET', 'HEAD'],
                'AllowedOrigins': ['*'],  # In production, replace with specific origins
                'ExposeHeaders': ['ETag'],
                'MaxAgeSeconds': 3000
            }]
        }
        
        s3_client.put_bucket_cors(Bucket=S3_BUCKET, CORSConfiguration=cors_configuration)
        print(f"Successfully configured CORS for bucket: {S3_BUCKET}")
    except Exception as e:
        print(f"Error configuring CORS: {e}")

# Configure CORS when app starts
configure_s3_cors()

# S3 and AWS Configuration
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")  # Default to us-east-1 if not specified
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
        print("No S3 bucket configured")
        return []
    try:
        print(f"Loading chat history for user {user_id} from bucket {S3_BUCKET}")
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=f"chat_history/{user_id}.json")
        history = json.loads(response['Body'].read().decode('utf-8'))
        print(f"Successfully loaded {len(history)} messages from chat history")
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
        print("No S3 bucket configured, skipping chat history save")
        return
    try:
        print(f"Saving {len(history)} messages for user {user_id} to bucket {S3_BUCKET}")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"chat_history/{user_id}.json",
            Body=json.dumps(history, ensure_ascii=False),
            ContentType='application/json'
        )
        print("Successfully saved chat history")
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
    print(f"Looking for image: {image_key} in bucket: {S3_BUCKET}")

    try:
        if not s3_client:
            print("S3 client not initialized")
            return jsonify({'error': 'S3 client not initialized'}), 500
        
        if not S3_BUCKET:
            print("S3 bucket not configured")
            return jsonify({'error': 'S3 bucket not configured'}), 500

        # Check if image exists in S3
        try:
            print("Checking if image exists in S3...")
            s3_client.head_object(Bucket=S3_BUCKET, Key=image_key)
            print("Image found, generating URL...")
            
            # Generate a pre-signed URL with longer expiration
            image_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': S3_BUCKET,
                    'Key': image_key,
                    'ResponseContentType': 'image/jpeg'
                },
                ExpiresIn=86400  # URL expires in 24 hours
            )
            
            print(f"Generated URL: {image_url}")
            
            # Verify URL is accessible
            try:
                requests.head(image_url)
                print("URL is accessible")
            except requests.exceptions.RequestException as e:
                print(f"Warning: URL may not be accessible: {e}")
            
            return jsonify({
                'image_url': image_url,
                'bucket': S3_BUCKET,
                'key': image_key,
                'expires_in': '24 hours'
            })
            
        except ClientError as e:
            error_code = e.response['Error'].get('Code', '')
            error_message = e.response['Error'].get('Message', '')
            print(f"S3 error: {error_code} - {error_message}")
            
            if error_code == '404':
                return jsonify({
                    'image_url': None,
                    'error': 'Image not found',
                    'key': image_key
                }), 404
            else:
                return jsonify({
                    'error': f'S3 error: {error_code}',
                    'message': error_message,
                    'key': image_key
                }), 500
                
    except Exception as e:
        print(f"Error handling character image: {type(e).__name__} - {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e),
            'key': image_key
        }), 500

@app.route("/")
def index():
    # Generate a simple user ID (in production, use proper user authentication)
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
    
    print(f"Handling request for user: {user_id}")
    
    # Prepare characters
    chars = []
    try:
        for c in characters:
            avatar_url = fetch_avatar_url(c["avatar"]) if S3_BUCKET else None
            chars.append({**c, "avatar_url": avatar_url})
        print(f"Prepared {len(chars)} characters")
    except Exception as e:
        print(f"Error preparing characters: {e}")
        chars = []
    
    # Load chat history
    chat_history = []
    try:
        if S3_BUCKET:
            chat_history = load_chat_history(user_id)
            print(f"Loaded {len(chat_history)} messages from history")
            
            # Clean message content of any control characters
            for msg in chat_history:
                if 'content' in msg and isinstance(msg['content'], str):
                    msg['content'] = ''.join(char for char in msg['content'] 
                                           if char.isprintable() or char in ['\n', '\t'])
        else:
            print("S3 bucket not configured, skipping chat history load")
    except Exception as e:
        print(f"Error loading chat history: {e}")
        chat_history = []
    
    # Group chat history
    grouped_history = {}
    try:
        for msg in chat_history:
            chat_id = msg.get('chatId')
            if not chat_id:  # Skip messages without chat ID
                continue
                
            if chat_id not in grouped_history:
                # Find the character for this chat
                character = msg.get('character')
                if not character or character == 'Unknown':
                    character = next((c['name'] for c in chars if c['name']), chars[0]['name'] if chars else 'Unknown')
                
                print(f"Creating new chat group: {chat_id} with character: {character}")
                grouped_history[chat_id] = {
                    'id': chat_id,
                    'character': character,
                    'messages': [],
                    'lastActivity': float(msg.get('timestamp', time.time()))
                }
            
            # Add message to chat
            grouped_history[chat_id]['messages'].append(msg)
            
            # Update lastActivity
            msg_time = float(msg.get('timestamp', time.time()))
            grouped_history[chat_id]['lastActivity'] = max(
                grouped_history[chat_id]['lastActivity'],
                msg_time
            )
        
        print(f"Grouped messages into {len(grouped_history)} chats")
    except Exception as e:
        print(f"Error grouping chat history: {e}")
        grouped_history = {}
            
        grouped_history[chat_id]['messages'].append(msg)
        grouped_history[chat_id]['lastActivity'] = max(
            grouped_history[chat_id]['lastActivity'], 
            msg.get('timestamp', time.time())
        )

    # Clean and encode the grouped history for the template
    clean_history = {}
    try:
        for chat_id, chat in grouped_history.items():
            clean_chat = {
                'id': chat_id,
                'character': chat.get('character', 'Unknown'),
                'messages': [],
                'lastActivity': chat.get('lastActivity', time.time())
            }
            
            # Clean and validate each message
            for msg in chat.get('messages', []):
                clean_msg = {
                    'chatId': chat_id,
                    'content': msg.get('content', '').strip(),
                    'type': msg.get('type', msg.get('role', 'user')),
                    'character': msg.get('character', chat.get('character', 'Unknown')),
                    'timestamp': msg.get('timestamp', time.time())
                }
                if clean_msg['content']:  # Only add non-empty messages
                    clean_chat['messages'].append(clean_msg)
            
            if clean_chat['messages']:  # Only add chats with messages
                clean_history[chat_id] = clean_chat
        
        print(f"Prepared {len(clean_history)} clean chats for template")
    except Exception as e:
        print(f"Error cleaning chat history: {e}")
        clean_history = {}
    
    # Pass clean_history instead of grouped_history
    response = make_response(render_template(
        "index.html",
        characters=chars,
        chat_history=clean_history
    ))

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
            "timestamp": time.time(),
            "chatId": data.get('chatId', 'default')

        })
        chat_history.append({
            "role": "assistant",
            "content": reply,
            "character": char_name,
            "timestamp": time.time(),
            "chatId": data.get('chatId', 'default')
        })
        # Keep only last 50 messages
        if len(chat_history) > 50:
            chat_history = chat_history[-50:]
        save_chat_history(user_id, chat_history)
    
    return jsonify({"reply": reply})


@app.route("/health")
def health():
    return "OK", 200

@app.route("/check_s3")
def check_s3():
    """Check S3 configuration and test image access"""
    try:
        # Test bucket access
        s3_client.head_bucket(Bucket=S3_BUCKET)
        
        # Check CORS configuration
        try:
            cors = s3_client.get_bucket_cors(Bucket=S3_BUCKET)
            cors_status = "Configured"
        except ClientError as e:
            cors_status = f"Not configured: {str(e)}"
        
        # Check bucket policy
        try:
            policy = s3_client.get_bucket_policy(Bucket=S3_BUCKET)
            policy_status = "Configured"
        except ClientError as e:
            policy_status = f"Not configured: {str(e)}"
        
        # Test character image access
        test_images = ['naruto.jpg', 'iron_man.jpg']
        image_status = {}
        
        for img in test_images:
            try:
                key = f"character_images/{img}"
                url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': key},
                    ExpiresIn=3600
                )
                image_status[img] = {
                    "status": "Available",
                    "url": url
                }
            except Exception as e:
                image_status[img] = {
                    "status": "Error",
                    "error": str(e)
                }
        
        return jsonify({
            "status": "success",
            "bucket": S3_BUCKET,
            "region": os.getenv('AWS_REGION', 'ap-southeast-2'),
            "cors_status": cors_status,
            "policy_status": policy_status,
            "images": image_status
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "bucket": S3_BUCKET
        }), 500

@app.route("/check_s3_config")
def check_s3_config():
    """Check S3 configuration and permissions"""
    if not s3_client or not S3_BUCKET:
        return jsonify({
            "status": "error",
            "message": "S3 not configured",
            "bucket": S3_BUCKET,
            "client": bool(s3_client)
        })
    
    try:
        # Check if bucket exists and is accessible
        s3_client.head_bucket(Bucket=S3_BUCKET)
        
        # Try to get bucket CORS configuration
        try:
            cors = s3_client.get_bucket_cors(Bucket=S3_BUCKET)
            cors_configured = True
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchCORSConfiguration':
                cors_configured = False
            else:
                raise e
        
        # Check bucket policy
        try:
            policy = s3_client.get_bucket_policy(Bucket=S3_BUCKET)
            has_policy = True
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucketPolicy':
                has_policy = False
            else:
                raise e
        
        # Test image access
        test_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': 'character_images/naruto.jpg'},
            ExpiresIn=3600
        )
        
        return jsonify({
            "status": "success",
            "bucket": S3_BUCKET,
            "cors_configured": cors_configured,
            "has_policy": has_policy,
            "test_image_url": test_url,
            "region": os.getenv('AWS_REGION', 'ap-southeast-2')
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "bucket": S3_BUCKET,
            "region": os.getenv('AWS_REGION', 'ap-southeast-2')
        })

@app.route("/test_s3")
def test_s3():
    """Debug endpoint to test S3 connectivity"""
    if not s3_client or not S3_BUCKET:
        return jsonify({
            "status": "error",
            "message": "S3 not configured",
            "bucket": S3_BUCKET,
            "client": bool(s3_client)
        })
    
    try:
        # List objects in character_images/
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='character_images/',
            MaxKeys=10
        )
        
        # Test listing chat_history/
        chat_response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='chat_history/',
            MaxKeys=10
        )
        
        return jsonify({
            "status": "success",
            "bucket": S3_BUCKET,
            "character_images": [obj['Key'] for obj in response.get('Contents', [])],
            "chat_histories": [obj['Key'] for obj in chat_response.get('Contents', [])],
            "cors": bool(s3_client.get_bucket_cors(Bucket=S3_BUCKET))
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "bucket": S3_BUCKET
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

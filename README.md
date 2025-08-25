# Anime/Superhero GPT (OpenRouter + EC2 + S3)

## Features
- Chat with anime/superhero characters powered by OpenRouter LLMs
- Character profiles & avatars stored in S3
- Flask backend + Tailwind chat UI
- EC2 deploy ready

## Setup
1. Clone repo & install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure `.env` (see `.env.example`)

3. Upload character avatars (e.g., naruto.jpg, goku.jpg, ironman.jpg) to your S3 bucket.

4. Run locally:
   ```bash
   gunicorn --bind 0.0.0.0:8000 app:app
   ```

5. Deploy to EC2, configure Nginx reverse proxy.

## IAM Policy Example
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::your_s3_bucket_name/*"
    }
  ]
}
```

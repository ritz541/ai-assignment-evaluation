import base64
import json
import os
import requests
import time
from retrying import retry
from PIL import Image
import io

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

def _prepare_image_data(images):
    """Encodes PIL images to base64 for API payload."""
    image_parts = []
    for img in images:
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        image_parts.append({
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": encoded_image
            }
        })
    return image_parts


def call_gemini_api_for_evaluation(prompt_text, images):
    """
    Calls the Gemini API to evaluate a student's submission.
    """
    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=5)
    def _call_with_retry():
        headers = {'Content-Type': 'application/json'}
        
        # Prepare parts for the prompt: text + images
        parts = [
            {'text': prompt_text}
        ]
        parts.extend(_prepare_image_data(images))
        
        payload = {
            'contents': [{'parts': parts}],
            'generationConfig': {
                'candidateCount': 1,
                'maxOutputTokens': 2048,
                'responseMimeType': 'application/json'
            },
            'safetySettings': [
                {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
            ]
        }
            
        api_key = os.environ.get("GEMINI_API_KEY", "")
        params = {'key': api_key}
        
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, params=params)
        response.raise_for_status()
        return response.json()

    try:
        result = _call_with_retry()
        if result and 'candidates' in result and result['candidates'] and \
           'content' in result['candidates'][0] and 'parts' in result['candidates'][0]['content']:
            text_response = result['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return None

# # Dormant code for DeepSeek API
# def call_deepseek_api_for_evaluation(prompt_text, images):
#     """
#     Calls the DeepSeek API for evaluation. This code is dormant.
#     """
#     api_key = os.environ.get("DEEPSEEK_API_KEY", "")
#     headers = {
#         'Content-Type': 'application/json',
#         'Authorization': f'Bearer {api_key}'
#     }
    
#     # In a real implementation, you would need to adjust the payload
#     # to match DeepSeek's API structure for multimodal input.
#     # This is a placeholder for a future implementation.
#     # Example payload structure:
#     # {
#     #     "model": "deepseek-v2",
#     #     "messages": [
#     #         {"role": "user", "content": [
#     #             {"type": "text", "text": prompt_text},
#     #             {"type": "image_url", "image_url": {"url": "base64_encoded_image"}}
#     #         ]}
#     #     ]
#     # }
#     # response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
#     
#     print("DeepSeek API call is dormant and not implemented.")
#     return None

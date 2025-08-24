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


def call_deepseek_api_for_summarization(text_content):
    """
    Calls the DeepSeek API to summarize the reference answer text.
    """
    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=5)
    def _call_with_retry():
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        prompt = f"""
        Summarize the following reference answer text into a concise, well-structured json format that can be used for automated grading.
        The summary should retain all key points and facts.
        
        Reference Text:
        {text_content}
        """

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that summarizes reference materials for grading."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "response_format": {"type": "json_object"}
        }
        
        print("--- Sending to DeepSeek API for Summarization ---")
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        
        print("--- DeepSeek API Response Status Code ---")
        print(response.status_code)
        print("--- DeepSeek API Response Body ---")
        print(response.text)
        
        response.raise_for_status()
        return response.json()

    try:
        result = _call_with_retry()
        if result and 'choices' in result and result['choices']:
            return result['choices'][0]['message']['content']
        
        print("--- Failed to get a valid response from DeepSeek AI. ---")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling DeepSeek API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        return None

def call_gemini_api_for_evaluation(prompt_text, text_content):
    """
    Calls the Gemini API to evaluate a student's submission using only text.
    """
    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=5)
    def _call_with_retry():
        headers = {'Content-Type': 'application/json'}
        
        parts = [
            {'text': prompt_text},
            {'text': text_content}
        ]
        
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
        
        print("--- Sending to Gemini API for Evaluation ---")
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, params=params)
        
        print("--- Gemini API Response Status Code ---")
        print(response.status_code)
        print("--- Gemini API Response Body ---")
        print(response.text)
        
        response.raise_for_status()
        return response.json()

    try:
        result = _call_with_retry()
        if result and 'candidates' in result and result['candidates'] and \
           'content' in result['candidates'][0] and 'parts' in result['candidates'][0]['content']:
            text_response = result['candidates'][0]['content']['parts'][0]['text']
            print("--- Final AI Text Response (before JSON parsing) ---")
            print(text_response)
            return json.loads(text_response)
        
        print("--- Failed to get a valid response from AI. Check the raw response body above. ---")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response: {e}")
        return None

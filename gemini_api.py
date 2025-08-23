import json, os
import requests
import time
from retrying import retry

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"

def call_gemini_api(prompt, stream=False, response_mime_type=None, response_schema=None):
    """
    Helper function to call the Gemini API with exponential backoff.
    """
    
    @retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=5)
    def _call_with_retry():
        headers = {'Content-Type': 'application/json'}
        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'candidateCount': 1,
                'maxOutputTokens': 2048,
            }
        }
        
        if response_mime_type:
            payload['generationConfig']['responseMimeType'] = response_mime_type
        if response_schema:
            payload['generationConfig']['responseSchema'] = response_schema
            
        api_key = os.environ.get("GEMINI_API_KEY", "")
        params = {'key': api_key}
        
        response = requests.post(API_URL, headers=headers, json=payload, params=params)
        response.raise_for_status()
        return response.json()

    try:
        result = _call_with_retry()
        if result and 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text']
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return None


def generate_assignment_prompt(title, subject, difficulty):
    """
    Generates an assignment prompt for the Gemini API.
    """
    prompt_text = f"""
    Create a new assignment for a college-level student.
    
    Subject: {subject}
    Topic: {title}
    Difficulty: {difficulty}
    
    The assignment should include a detailed description and 3-5 open-ended questions. 
    The questions should be thought-provoking and require critical thinking. 
    The tone should be professional and encouraging.

    Return the output in a JSON format with the following keys:
    "description": "The assignment description",
    "questions": ["Question 1", "Question 2", "Question 3"]
    """
    return call_gemini_api(prompt_text, response_mime_type="application/json")


def evaluate_submission_with_gemini(question, reference_answer, student_answer):
    """
    Evaluates a student's submission using the Gemini API and returns a score and remarks.
    """
    prompt = f"""
    You are an AI grading assistant. Your task is to evaluate a student's answer against a reference answer.
    
    Question: {question}
    Reference Answer: {reference_answer}
    Student's Answer: {student_answer}

    Your evaluation must be structured as follows:
    1. Score the student's answer on a scale of 0 to 100.
    2. Provide constructive feedback (remarks) of 1-2 sentences on how the student's answer could be improved.
    
    Return the output in a JSON format with the following keys:
    "score": "A number from 0 to 100",
    "remarks": "Constructive feedback"
    """
    return call_gemini_api(prompt, response_mime_type="application/json")

import os
import requests
from retrying import retry
    
@retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=5)
def _call_webhook_with_retry(url, payload):
        """
        Sends a POST request to a given webhook URL with exponential backoff.
        """
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response
    
def send_notification(event_type, data):
        """
        Sends a JSON payload to the appropriate n8n webhook URL.
        """
        try:
            if event_type == 'new_assignment':
                webhook_url = os.environ.get('NOTIFICATION_NEW_ASSIGNMENT_WEBHOOK')
            elif event_type == 'evaluation_complete':
                webhook_url = os.environ.get('NOTIFICATION_EVALUATION_COMPLETE_WEBHOOK')
            else:
                return False, 'Invalid event type'
    
            if not webhook_url:
                print(f"Warning: Webhook URL for {event_type} not found in .env file.")
                return False, 'Webhook URL not configured'
    
            _call_webhook_with_retry(webhook_url, data)
            return True, 'Notification sent successfully'
        except requests.exceptions.RequestException as e:
            print(f"Error sending notification to webhook: {e}")
            return False, str(e)
    
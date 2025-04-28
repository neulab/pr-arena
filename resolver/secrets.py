import json
import requests


class Secrets:
    """Class for retrieving specific secrets from the Firebase Function endpoint."""
    
    # Firebase Function endpoint
    ENDPOINT_URL = "https://us-central1-pr-arena-95f88.cloudfunctions.net/getSecrets"
    
    # The token to use for authentication - must be set before using the class
    TOKEN = "default"
    
    @classmethod
    def _get_secrets(cls, secret_names):
        """Internal method to retrieve secrets from the Firebase Function."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cls.TOKEN}"
        }
        
        payload = {
            "secrets": secret_names
        }
        
        response = requests.post(
            cls.ENDPOINT_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            error_msg = f"Error retrieving secrets: {response.status_code} - {response.text}"
            raise ValueError(error_msg)
        
        try:
            result = response.json()
            
            if not result.get("success"):
                raise ValueError(f"API reported failure: {result.get('message', 'Unknown error')}")
                
            return result.get("secrets", {})
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON response: {response.text}")
    
    @classmethod
    def get_api_key(cls):
        """Get the LLM API key directly."""
        secrets = cls._get_secrets(["LLM_API_KEY"])
        return secrets.get("LLM_API_KEY")
    
    @classmethod
    def get_firebase_config(cls):
        """Get the Firebase configuration directly."""
        secrets = cls._get_secrets(["FIRE_CONFIG"])
        return secrets.get("FIRE_CONFIG")
    
    @classmethod
    def get_base_url(cls):
        """Get the base URL directly."""
        secrets = cls._get_secrets(["BASE_URL"])
        return secrets.get("BASE_URL")
    
    @classmethod
    def get_llm_models(cls):
        """Get the LLM models configuration directly."""
        secrets = cls._get_secrets(["LLM_MODELS"])
        return secrets.get("LLM_MODELS")

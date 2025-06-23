import requests
import time

BASE_URL = "https://api.bannerbear.com/v2"

def list_templates(api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(f"{BASE_URL}/templates", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error fetching templates: {e}")
        return None

def get_template_details(api_key: str, template_uid: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(f"{BASE_URL}/templates/{template_uid}", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error fetching template details for {template_uid}: {e}")
        return None

def create_image(api_key: str, template_id: str, modifications: list):
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "template": template_id,
        "modifications": modifications
    }
    try:
        response = requests.post(f"{BASE_URL}/images", headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error creating image: {e}")
        return None

def poll_for_image(api_key: str, image_object: dict):
    headers = {"Authorization": f"Bearer {api_key}"}
    polling_url = image_object.get("self")
    if not polling_url:
        return None

    while image_object['status'] != 'completed':
        time.sleep(1)
        try:
            response = requests.get(polling_url, headers=headers)
            response.raise_for_status()
            image_object = response.json()
            if image_object['status'] == 'failed':
                print("Image generation failed.")
                return None
        except requests.exceptions.RequestException as e:
            print(f"API Error polling for image: {e}")
            return None
    
    return image_object
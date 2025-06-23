import requests
import base64

def upload_image_to_freeimage(image_bytes: bytes):
    """
    Uploads an image from bytes to freeimage.host and returns the direct URL.
    This uses the public API key provided.
    """
    FREEIMAGE_API_URL = "https://freeimage.host/api/1/upload"
    API_KEY = "6d207e02198a847aa98d0a2a901485a5"

    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            'key': API_KEY,
            'action': 'upload',
            'source': base64_image,
            'format': 'json'
        }

        response = requests.post(FREEIMAGE_API_URL, data=payload, timeout=30)
        response.raise_for_status()

        result = response.json()

        if result.get("status_code") == 200 and result.get("image"):
            image_url = result["image"]["url"]
            print(f"Image uploaded successfully to freeimage.host: {image_url}")
            return image_url
        else:
            error_message = result.get("status_txt", "Unknown error from freeimage.host API.")
            print(f"Failed to upload image. API Error: {error_message}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the request to freeimage.host: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during image upload: {e}")
        return None
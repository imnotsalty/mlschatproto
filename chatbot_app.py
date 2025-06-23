import streamlit as st
import os
import requests
from dotenv import load_dotenv

from pathlib import Path

from bannerbear_helpers import get_template_details, create_image, poll_for_image
from gemini_helpers import get_gemini_model, generate_gemini_response
from image_uploader import upload_image_to_freeimage
from ui_helpers import inject_css, typing_indicator

st.set_page_config(page_title="ROA AI Designer", layout="centered")
inject_css()

image_path = Path(__file__).parent / "roa.png"
st.image(str(image_path), width=200)
st.title("AI Design Assistant")
st.caption("Powered by Realty of America")

load_dotenv()
BB_API_KEY, GEMINI_API_KEY, RESO_API_KEY, RESO_API_ENDPOINT = os.getenv("BANNERBEAR_API_KEY"), os.getenv("GEMINI_API_KEY"), os.getenv("RESO_API_KEY"), os.getenv("RESO_API_ENDPOINT")


@st.cache_resource(show_spinner="Loading design templates...")
def load_all_template_details():
    try:
        if not BB_API_KEY: return None
        summary_url = "https://api.bannerbear.com/v2/templates"
        headers = {"Authorization": f"Bearer {BB_API_KEY}"}
        response = requests.get(summary_url, headers=headers, timeout=15)
        response.raise_for_status()
        summary = response.json()
        return [get_template_details(BB_API_KEY, t['uid']) for t in summary if t]
    except Exception as e:
        st.error(f"Error loading templates: {e}", icon="🚨")
        return None

def initialize_session_state():
    defaults = {
        "messages": [{"role": "assistant", "content": "Hello! I'm your design assistant. Just tell me what you need to create."}],
        "gemini_model": get_gemini_model(GEMINI_API_KEY),
        "rich_templates_data": load_all_template_details(),
        "design_context": {"template_uid": None, "modifications": []},
        "staged_file": None,
        "awaiting_mls_id": False
    }
    for key, default_value in defaults.items():
        if key not in st.session_state: st.session_state[key] = default_value


def fetch_reso_property_details(mls_id: str):
    """Fetches property details from the RESO API using the MLS ID."""
    try:
        # Construct the OData query URL
        query_url = f"{RESO_API_ENDPOINT}/Property?$filter=PropertyID eq '{mls_id}'"

        headers = {
            "Authorization": f"Bearer {RESO_API_KEY}",  # Use your API key here
            "Accept": "application/json"  # Specify JSON response format
        }

        response = requests.get(query_url, headers=headers, timeout=10)  # Adjust timeout as needed
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        data = response.json()

        # RESO APIs typically return data in an "value" array within the JSON response
        if "value" in data and len(data["value"]) > 0:
            return data["value"][0]  # Return the first property found
        else:
            print(f"No property found with MLS ID: {mls_id}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching RESO data: {e}")
        return None
    except (KeyError, ValueError) as e:  # Handle JSON parsing errors
        print(f"Error parsing RESO response: {e}")
        return None


def map_reso_to_modifications(reso_data: dict, template_details: dict) -> list:
    """
    Maps RESO property details to template modifications.
    Only creates modifications for fields available in the template.
    """
    modifications = []
    template_layers = {layer['name'].lower(): layer for layer in template_details.get('elements', [])}

    # Define a mapping of RESO fields to template layer names (lowercase for matching)
    field_mapping = {
        "StreetAddress": "address",
        "City": "city",
        "StateOrProvince": "state",
        "PostalCode": "zip",
        "ListPrice": "price",
        "BedroomsTotal": "bedrooms",
        "BathroomsTotalInteger": "bathrooms",
        "PublicRemarks": "description",
        # Add more mappings as needed
    }

    for reso_field, template_field in field_mapping.items():
        if template_field in template_layers and reso_field in reso_data:
            layer_name = template_layers[template_field]['name']
            value = reso_data[reso_field]

            #Format price
            if reso_field == "ListPrice":
                 value = f"${int(value):,}"

            modifications.append({"name": layer_name, "text": str(value)})

    return modifications


def handle_ai_decision(decision):
    """The central router that executes the AI's chosen action."""
    action = decision.get("action")
    response_text = decision.get("response_text", "I'm not sure how to proceed.")
    trigger_generation = False

    if action == "CONVERSE":
        return response_text

    if action == "MODIFY":
        new_template_uid = decision.get("template_uid")
        if new_template_uid and new_template_uid != st.session_state.design_context.get("template_uid"):
            if st.session_state.design_context.get("template_uid") is not None:
                trigger_generation = True
            st.session_state.design_context["template_uid"] = new_template_uid

        current_mods_dict = {mod['name']: mod for mod in st.session_state.design_context.get('modifications', [])}
        new_mods_from_ai = decision.get("modifications", [])
        for mod in new_mods_from_ai:
            current_mods_dict[mod['name']] = dict(mod)

        st.session_state.design_context["modifications"] = list(current_mods_dict.values())

    elif action == "GENERATE":
        trigger_generation = True

    elif action == "RESET":
        st.session_state.design_context = {"template_uid": None, "modifications": []}
        return response_text

    if trigger_generation:
        context = st.session_state.design_context
        if not context.get("template_uid"):
            return "I can't generate an image yet. Please describe the design you want first."

        with st.spinner("Generating your image... This may take a moment."):
            final_modifications = context.get("modifications", [])
            initial_response = create_image(BB_API_KEY, context['template_uid'], final_modifications)

            if not initial_response:
                response_text = "❌ **Error:** Failed to start image generation."
            else:
                final_image = poll_for_image(BB_API_KEY, initial_response)
                if final_image and final_image.get("image_url_png"):
                    response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
                else:
                    response_text = "❌ **Error:** Image generation failed during rendering."

    return response_text

initialize_session_state()

if not st.session_state.rich_templates_data:
    st.error("Application cannot start because design templates could not be loaded. Please ensure your BANNERBEAR_API_KEY is correct and restart.", icon="🛑")
    st.stop()

with st.sidebar:
    st.header("Upload Image")
    staged_file_bytes = st.file_uploader("Attach an image to your next message", type=["png", "jpg", "jpeg"])
    if staged_file_bytes:
        st.session_state.staged_file = staged_file_bytes.getvalue()
        st.success("✅ Image attached and ready!")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

if st.session_state.awaiting_mls_id:
    mls_id = st.chat_input("Please enter the MLS ID:")
    if mls_id:
        st.session_state.awaiting_mls_id = False
        with st.spinner("Fetching property details..."):
            reso_data = fetch_reso_property_details(mls_id)
            if reso_data:
                #Assuming user asked for a new image.
                template_details = st.session_state.rich_templates_data[0] #Pick the first one

                modifications = map_reso_to_modifications(reso_data, template_details)
                st.session_state.design_context["template_uid"] = template_details['uid']
                st.session_state.design_context["modifications"] = modifications

                initial_response = create_image(BB_API_KEY, st.session_state.design_context['template_uid'], st.session_state.design_context["modifications"])

                if not initial_response:
                    response_text = "❌ **Error:** Failed to start image generation."
                else:
                    final_image = poll_for_image(BB_API_KEY, initial_response)
                    if final_image and final_image.get("image_url_png"):
                        response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
                    else:
                        response_text = "❌ **Error:** Image generation failed during rendering."
                st.session_state.messages.append({"role": "assistant", "content": response_text})

            else:
                st.error("Failed to fetch property details with that MLS ID.", icon="❌")
                st.session_state.messages.append({"role": "assistant", "content": "Failed to fetch property details with that MLS ID."})

elif prompt := st.chat_input("Your message..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown(typing_indicator(), unsafe_allow_html=True)

        final_prompt_for_ai = prompt
        if st.session_state.staged_file:
            with st.spinner("Uploading your image..."):
                image_url = upload_image_to_freeimage(st.session_state.staged_file)
                st.session_state.staged_file = None
                if image_url:
                    final_prompt_for_ai = f"Image context: The user has just uploaded an image, available at {image_url}. Their text command is: '{prompt}'"
                else:
                    placeholder.error("Image upload failed.", icon="❌")
                    final_prompt_for_ai = None

        response_text = "I'm sorry, something went wrong. Could you please try rephrasing?"
        if final_prompt_for_ai:
            response = generate_gemini_response(
                model=st.session_state.gemini_model,
                chat_history=st.session_state.messages,
                user_prompt=final_prompt_for_ai,
                rich_templates_data=st.session_state.rich_templates_data,
                current_design_context=st.session_state.design_context
            )

            if response and response.candidates:
                part = response.candidates[0].content.parts[0]
                # Case 1: The AI returned a function call (the primary workflow).
                if hasattr(part, 'function_call') and part.function_call:
                    decision = dict(part.function_call.args)
                    response_text = handle_ai_decision(decision)
                # Case 2: The AI returned a direct text response for conversation.
                elif hasattr(part, 'text') and part.text:
                    response_text = part.text
                # Case 3: The response was malformed or empty.
                else:
                    response_text = "I'm having trouble connecting right now. Please try again in a moment."
            # Case 4: The API call itself failed or returned no candidates.
            else:
                response_text = "I'm having trouble connecting right now. Please try again in a moment."

        placeholder.markdown(response_text, unsafe_allow_html=True)
    st.session_state.messages.append({"role": "assistant", "content": response_text})
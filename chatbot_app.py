import streamlit as st
import os
import requests
from dotenv import load_dotenv
from pathlib import Path
import re

from bannerbear_helpers import get_template_details, create_image, poll_for_image
from gemini_helpers import get_gemini_model, generate_gemini_response, create_modifications_for_template, categorize_request
from image_uploader import upload_image_to_freeimage
from ui_helpers import inject_css, typing_indicator

# --- App Setup ---
st.set_page_config(page_title="ROA AI Designer", layout="centered")
inject_css()

image_path = Path(__file__).parent / "roa.png"
st.image(str(image_path), width=200)
st.title("AI Design Assistant")
st.caption("Powered by Realty of America")

# --- Load Environment Variables ---
load_dotenv()
BB_API_KEY = os.getenv("BANNERBEAR_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
REALTY_API_ENDPOINT = os.getenv("REALTY_API_ENDPOINT")

# --- Caching and Session State ---
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
        "awaiting_mls_id": False,
        "initial_request_prompt": None # NEW: Store the prompt that triggers MLS flow
    }
    for key, default_value in defaults.items():
        if key not in st.session_state: st.session_state[key] = default_value

# --- API and Data Mapping Functions (Unchanged) ---
def fetch_listing_details(mls_id: str):
    if not REALTY_API_ENDPOINT:
        print("REALTY_API_ENDPOINT is not configured in .env file.")
        return None
    headers = {'accept': 'application/json', 'Content-Type': 'application/json'}
    payload = {"size": 1, "mlses": [386], "mls_listings": [str(mls_id)], "view": "detailed"}
    try:
        response = requests.post(REALTY_API_ENDPOINT, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("data", {}).get("content", {}).get("listings"):
            return data["data"]["content"]["listings"][0]
        else:
            print(f"No property found with MLS ID: {mls_id}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Realty of America API data: {e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        print(f"Error parsing API response: {e}")
        return None

# --- Core AI and UI Logic (Unchanged) ---
def handle_ai_decision(decision):
    action = decision.get("action")
    response_text = decision.get("response_text", "I'm not sure how to proceed.")
    trigger_generation = False
    if action == "CONVERSE": return response_text
    if action == "MODIFY":
        new_template_uid = decision.get("template_uid")
        if new_template_uid and new_template_uid != st.session_state.design_context.get("template_uid"):
            if st.session_state.design_context.get("template_uid") is not None: trigger_generation = True
            st.session_state.design_context["template_uid"] = new_template_uid
        current_mods_dict = {mod['name']: mod for mod in st.session_state.design_context.get('modifications', [])}
        new_mods_from_ai = decision.get("modifications") or []
        for mod in new_mods_from_ai: current_mods_dict[mod['name']] = dict(mod)
        st.session_state.design_context["modifications"] = list(current_mods_dict.values())
    elif action == "GENERATE": trigger_generation = True
    elif action == "RESET":
        st.session_state.design_context = {"template_uid": None, "modifications": []}
        return response_text
    if trigger_generation:
        context = st.session_state.design_context
        if not context.get("template_uid"): return "I can't generate an image yet. Please describe the design you want first."
        with st.spinner("Generating your image... This may take a moment."):
            final_modifications = context.get("modifications", [])
            initial_response = create_image(BB_API_KEY, context['template_uid'], final_modifications)
            if not initial_response: response_text = "❌ **Error:** Failed to start image generation."
            else:
                final_image = poll_for_image(BB_API_KEY, initial_response)
                if final_image and final_image.get("image_url_png"): response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
                else: response_text = "❌ **Error:** Image generation failed during rendering."
    return response_text

# --- Main App Execution ---
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

if prompt := st.chat_input("Your message..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        if st.session_state.awaiting_mls_id:
            found_numbers = re.findall(r'\d+', prompt)
            if not found_numbers:
                response_text = f"I'm sorry, I couldn't find a valid numerical ID in '{prompt}'. Please provide the MLS ID."
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
            else:
                mls_id = found_numbers[0]
                with st.spinner(f"Fetching property details for MLS ID# {mls_id}..."):
                    listing_data = fetch_listing_details(mls_id)

                if listing_data:
                    with st.expander("✅ Fetched MLS Data (Debug View)"):
                        st.json(listing_data)
                    
                    # NEW: Categorize request to filter templates
                    category_keywords = []
                    initial_prompt = st.session_state.initial_request_prompt or prompt
                    with st.spinner("Categorizing your request..."):
                        category = categorize_request(st.session_state.gemini_model, initial_prompt)
                    
                    category_map = {
                        "just_listed": ["listed", "new"], "just_sold": ["sold"],
                        "open_house": ["open house", "openhouse"],
                        "general_property_ad": ["flyer", "ad", "listing", "property"]
                    }
                    category_keywords = category_map.get(category, category_map["general_property_ad"])
                    st.info(f"💡 Searching for templates matching: **{category.replace('_', ' ')}**")

                    all_templates = st.session_state.rich_templates_data
                    filtered_templates = [
                        t for t in all_templates 
                        if any(keyword in t.get('name', '').lower() for keyword in category_keywords)
                    ]

                    if not filtered_templates:
                        st.warning("No templates matched the category. Searching all available designs.")
                        filtered_templates = all_templates

                    # Template-driven mapping using the filtered list
                    best_template = None
                    best_modifications = []
                    highest_score = 0

                    with st.spinner(f"Analyzing {len(filtered_templates)} matching templates..."):
                        for template in filtered_templates:
                            mods = create_modifications_for_template(
                                model=st.session_state.gemini_model,
                                listing_data=listing_data,
                                template_details=template
                            )
                            if mods and len(mods) > highest_score:
                                highest_score = len(mods)
                                best_modifications = mods
                                best_template = template

                    if best_template:
                        st.session_state.awaiting_mls_id = False
                        st.session_state.initial_request_prompt = None # Reset prompt
                        modifications = best_modifications
                        template_details = best_template
                        
                        st.session_state.design_context["template_uid"] = template_details['uid']
                        st.session_state.design_context["modifications"] = modifications
                        
                        template_layer_names = {layer['name'].lower() for layer in template_details.get('elements', []) if layer.get('name')}
                        filled_layer_names = {mod['name'].lower() for mod in modifications}
                        missing_fields = [
                            layer['name'] for layer in template_details.get('elements', []) 
                            if layer['name'].lower() not in filled_layer_names and layer.get('type') == 'text'
                        ]
                        
                        response_text = f"Great! I've pulled the data for MLS ID# {mls_id} and selected the best template. "
                        
                        if missing_fields:
                            missing_list_str = ", ".join(f"**{f}**" for f in missing_fields)
                            response_text += f"\n\nTo complete the design, could you please provide the {missing_list_str}?"
                            st.markdown(response_text)
                            st.session_state.messages.append({"role": "assistant", "content": response_text})
                        else:
                            response_text += "\n\nAll required information was found! Generating your image now..."
                            st.markdown(response_text)
                            
                            with st.spinner("Creating your design..."):
                                initial_response = create_image(BB_API_KEY, template_details['uid'], modifications)
                                if initial_response and (final_image := poll_for_image(BB_API_KEY, initial_response)) and final_image.get("image_url_png"):
                                    image_generation_message = f"![Generated Image]({final_image['image_url_png']})"
                                    st.markdown(image_generation_message, unsafe_allow_html=True)
                                    st.session_state.messages.append({"role": "assistant", "content": image_generation_message})
                                else:
                                    st.error("❌ **Error:** Image generation failed.", icon="🚨")
                    else:
                        st.error("I reviewed all our templates but couldn't find one with enough matching layers for that MLS data.", icon="😕")

                else:
                    response_text = f"I'm sorry, I couldn't find any property details for MLS ID# {mls_id}. Please check the ID and try again."
                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
        else:
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
                    if hasattr(part, 'function_call') and part.function_call:
                        decision = dict(part.function_call.args)
                        is_gibberish = len(prompt) > 1 and ' ' not in prompt and len(prompt) > 15
                        is_short_convo = len(prompt.split()) < 3 and len(prompt) < 15
                        if decision.get("action") == "RESET" and (is_gibberish or is_short_convo):
                            response_text = "I'm sorry, I didn't quite understand. How can I help you create a design?"
                        else:
                            response_text = handle_ai_decision(decision)
                    elif hasattr(part, 'text') and part.text:
                        response_text = part.text
                    else: response_text = "I'm having trouble connecting right now. Please try again in a moment."
                else: response_text = "I'm having trouble connecting right now. Please try again in a moment."
            
            if "can you provide the MLS ID" in response_text:
                st.session_state.awaiting_mls_id = True
                # NEW: Store the prompt that initiated the request
                st.session_state.initial_request_prompt = final_prompt_for_ai

            placeholder.markdown(response_text, unsafe_allow_html=True)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
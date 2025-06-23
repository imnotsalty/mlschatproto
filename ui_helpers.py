import streamlit as st

def inject_css():
    """Injects minimal CSS needed ONLY for the custom typing indicator."""

    roa_dark_blue = "#003366"

    css = f"""
<style>
    /* The container for the typing indicator */
    .typing-indicator {{
        display: flex;
        padding: 10px;
        align-items: center;
        justify-content: flex-start;
        height: 2.5rem;
    }}

    /* The individual dots using the brand color */
    .typing-indicator span {{
        height: 0.5rem;
        width: 0.5rem;
        margin: 0 3px;
        background-color: {roa_dark_blue};
        border-radius: 50%;
        display: inline-block;
        animation: bounce 1.4s infinite ease-in-out both;
    }}

    /* Staggering the animation for each dot */
    .typing-indicator span:nth-of-type(2) {{
        animation-delay: -0.2s;
    }}
    .typing-indicator span:nth-of-type(3) {{
        animation-delay: -0.4s;
    }}

    /* Keyframes for the bounce animation */
    @keyframes bounce {{
        0%, 80%, 100% {{ 
            transform: scale(0);
        }}
        40% {{ 
            transform: scale(1.0);
        }}
    }}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)

def typing_indicator():
    """Returns the HTML for the typing indicator."""
    return """
<div class="typing-indicator">
<span></span>
<span></span>
<span></span>
</div>
"""
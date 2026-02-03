import json
import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build


CUISINES = [
    "Mexican",
    "Seafood",
    "Japanese",
    "Korean",
    "Chinese",
    "Vietnamese",
    "Thai",
    "Filipino",
    "Italian",
    "Greek",
    "Turkish",
    "Iranian",
    "Lebanese",
    "Indian",
    "Ethiopian",
    "Peruvian",
    "Hawaiian",
    "Barbeque",
    "Spanish",
    "Brazilian",
]

TIMEZONE = ZoneInfo("America/Los_Angeles")
MIN_RATING = 4.2
MIN_REVIEWS = 200


def load_service_account_info() -> dict:
    raw = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def get_next_monday_date() -> datetime.date:
    today = datetime.now(TIMEZONE).date()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def build_google_clients():
    credentials = service_account.Credentials.from_service_account_info(
        load_service_account_info(),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/calendar",
        ],
    )
    sheets_service = build("sheets", "v4", credentials=credentials)
    calendar_service = build("calendar", "v3", credentials=credentials)
    return sheets_service, calendar_service


def fetch_history_place_ids(sheets_service) -> set[str]:
    spreadsheet_id = st.secrets["SPREADSHEET_ID"]
    response = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="History!A:J")
        .execute()
    )
    rows = response.get("values", [])
    if not rows:
        return set()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    if "Google Place ID" not in df.columns:
        return set()
    return set(df["Google Place ID"].dropna().astype(str))


def append_history_row(sheets_service, row: list[str]) -> None:
    spreadsheet_id = st.secrets["SPREADSHEET_ID"]
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="History!A:J",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def search_places(cuisine: str) -> list[dict]:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "X-Goog-Api-Key": st.secrets["Maps_API_KEY"],
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.rating,places.userRatingCount,"
            "places.priceLevel,places.formattedAddress,places.googleMapsUri"
        ),
    }
    payload = {
        "textQuery": f"{cuisine} food near 92117",
        "minRating": MIN_RATING,
        "openNow": True,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    places = response.json().get("places", [])
    return places


def choose_place(places: list[dict], history_ids: set[str]) -> dict | None:
    eligible = []
    for place in places:
        place_id = place.get("id")
        rating = place.get("rating", 0)
        reviews = place.get("userRatingCount", 0)
        if not place_id or place_id in history_ids:
            continue
        if rating < MIN_RATING or reviews < MIN_REVIEWS:
            continue
        eligible.append(place)
    if not eligible:
        return None
    return random.choice(eligible)


def get_place_name(place: dict) -> str:
    return place.get("displayName", {}).get("text", "Unknown Restaurant")


def create_calendar_event(calendar_service, place: dict, event_date: datetime.date) -> None:
    calendar_id = st.secrets["CALENDAR_ID"]
    start_dt = datetime.combine(event_date, time(18, 0), tzinfo=TIMEZONE)
    end_dt = datetime.combine(event_date, time(20, 0), tzinfo=TIMEZONE)
    
    # We removed the 'attendees' logic here to fix the 403 error

    event = {
        "summary": f"Dinner @ {get_place_name(place)}",
        "location": place.get("formattedAddress", ""),
        "description": (
            f"{get_place_name(place)} | Rating: {place.get('rating', 'N/A')} "
            f"| Reviews: {place.get('userRatingCount', 'N/A')} | Link: {place.get('googleMapsUri', '')}"
        ),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE.key,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE.key,
        },
        # "attendees": ... <-- REMOVED THIS LINE
    }
    
    # Removed 'sendUpdates="all"' because we aren't emailing anyone anymore
    calendar_service.events().insert(
        calendarId=calendar_id, body=event
    ).execute()


def format_history_row(place: dict, cuisine: str, event_date: datetime.date) -> list[str]:
    timestamp = datetime.now(TIMEZONE).isoformat()
    return [
        timestamp,
        event_date.isoformat(),
        cuisine,
        get_place_name(place),
        place.get("id", ""),
        str(place.get("rating", "")),
        str(place.get("userRatingCount", "")),
        str(place.get("priceLevel", "")),
        place.get("formattedAddress", ""),
        place.get("googleMapsUri", ""),
    ]


# ============================================================================
# PREMIUM DARK MODE CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="Weekly New Restaurant Night",
    page_icon="🍽️",
    layout="centered"  # Mobile-first card layout
)

# ============================================================================
# EMBEDDED CSS STYLING - PREMIUM DARK MODE
# ============================================================================
st.markdown("""
<style>
    /* ===== GLOBAL DARK MODE THEME ===== */
    :root {
        --primary-gradient-start: #ff6b35;
        --primary-gradient-end: #f7931e;
        --bg-dark: #0a0a0a;
        --bg-card: #1a1a1a;
        --text-primary: #ffffff;
        --text-secondary: #b0b0b0;
        --shadow-glow: rgba(255, 107, 53, 0.3);
    }
    
    /* Dark background for entire app */
    .stApp {
        background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
        color: var(--text-primary);
    }
    
    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* ===== HERO TYPOGRAPHY WITH GRADIENT ===== */
    .hero-title {
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        background: linear-gradient(
            135deg,
            var(--primary-gradient-start) 0%,
            var(--primary-gradient-end) 100%
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 2rem 0 1rem 0;
        letter-spacing: -0.02em;
        line-height: 1.1;
        text-shadow: 0 0 40px var(--shadow-glow);
        animation: fadeInDown 0.8s ease-out;
    }
    
    .hero-subtitle {
        text-align: center;
        color: var(--text-secondary);
        font-size: 1.1rem;
        margin-bottom: 3rem;
        font-weight: 300;
        letter-spacing: 0.05em;
    }
    
    /* ===== BIG BUTTON THEORY ===== */
    /* Override Streamlit's default small button */
    .stButton > button {
        width: 100% !important;
        height: 75px !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        background: linear-gradient(
            135deg,
            var(--primary-gradient-start) 0%,
            var(--primary-gradient-end) 100%
        ) !important;
        color: white !important;
        border: none !important;
        border-radius: 16px !important;
        box-shadow: 
            0 8px 24px rgba(255, 107, 53, 0.4),
            0 4px 12px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        cursor: pointer !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 
            0 12px 32px rgba(255, 107, 53, 0.5),
            0 6px 16px rgba(0, 0, 0, 0.4) !important;
    }
    
    .stButton > button:active {
        transform: translateY(0px) !important;
    }
    
    /* ===== CONTENT CARDS ===== */
    .result-card {
        background: var(--bg-card);
        border-radius: 20px;
        padding: 2rem;
        margin: 2rem 0;
        box-shadow: 
            0 8px 32px rgba(0, 0, 0, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.05);
        animation: fadeInUp 0.6s ease-out;
    }
    
    .restaurant-name {
        font-size: 2rem;
        font-weight: 700;
        color: var(--text-primary);
        margin-bottom: 0.5rem;
        background: linear-gradient(
            135deg,
            #ffffff 0%,
            var(--primary-gradient-end) 100%
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .restaurant-details {
        color: var(--text-secondary);
        font-size: 1.1rem;
        margin: 1rem 0;
    }
    
    /* ===== STREAMLIT COMPONENT OVERRIDES ===== */
    .stMarkdown {
        color: var(--text-primary);
    }
    
    .stSuccess {
        background-color: rgba(34, 197, 94, 0.1) !important;
        border-left: 4px solid #22c55e !important;
        color: #86efac !important;
        border-radius: 8px !important;
    }
    
    .stWarning {
        background-color: rgba(251, 191, 36, 0.1) !important;
        border-left: 4px solid #fbbf24 !important;
        color: #fde047 !important;
        border-radius: 8px !important;
    }
    
    .stError {
        background-color: rgba(239, 68, 68, 0.1) !important;
        border-left: 4px solid #ef4444 !important;
        color: #fca5a5 !important;
        border-radius: 8px !important;
    }
    
    /* Links styling */
    a {
        color: var(--primary-gradient-end) !important;
        text-decoration: none !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    
    a:hover {
        color: var(--primary-gradient-start) !important;
        text-decoration: underline !important;
    }
    
    /* ===== METRICS STYLING ===== */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: var(--text-primary) !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
        font-size: 0.9rem !important;
        font-weight: 500 !important;
    }
    
    [data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.02) !important;
        padding: 1rem !important;
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    
    /* ===== LINK BUTTON STYLING ===== */
    .stLinkButton > a {
        background: linear-gradient(
            135deg,
            var(--primary-gradient-start) 0%,
            var(--primary-gradient-end) 100%
        ) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 14px 28px !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        text-decoration: none !important;
        box-shadow: 
            0 6px 20px rgba(255, 107, 53, 0.3),
            0 3px 10px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        display: inline-block !important;
        width: 100% !important;
        text-align: center !important;
    }
    
    .stLinkButton > a:hover {
        transform: translateY(-2px) !important;
        box-shadow: 
            0 8px 28px rgba(255, 107, 53, 0.4),
            0 4px 14px rgba(0, 0, 0, 0.3) !important;
        text-decoration: none !important;
    }
    
    /* ===== CONTAINER STYLING ===== */
    [data-testid="stVerticalBlock"] > div:has(> div[data-testid="stVerticalBlock"]) {
        background: var(--bg-card) !important;
        border-radius: 20px !important;
        padding: 2rem !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 
            0 8px 32px rgba(0, 0, 0, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    
    /* ===== SPINNER STYLING ===== */
    .stSpinner > div {
        border-top-color: var(--primary-gradient-end) !important;
    }
    
    /* ===== ANIMATIONS ===== */
    @keyframes fadeInDown {
        from {
            opacity: 0;
            transform: translateY(-20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* ===== MOBILE RESPONSIVENESS ===== */
    @media (max-width: 768px) {
        .hero-title {
            font-size: 2.5rem;
        }
        
        .stButton > button {
            height: 65px !important;
            font-size: 1.2rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# HERO SECTION
# ============================================================================
st.markdown("""
    <div class="hero-title">
        🍽️ Weekly New Restaurant Night
    </div>
    <div class="hero-subtitle">
        Discover your next culinary adventure
    </div>
""", unsafe_allow_html=True)

if st.button("Roll the Dice"):
    # ============================================================================
    # GAMIFIED UX - SLOT MACHINE EXPERIENCE
    # ============================================================================
    
    # Fun loading messages for latency masking
    loading_messages = [
        "🎰 Spinning the culinary wheel...",
        "🍜 Consulting the foodie gods...",
        "🎲 Rolling for flavor...",
        "🔮 Divining your next meal...",
        "🌟 Searching for deliciousness...",
        "🎯 Hunting down the perfect spot...",
    ]
    
    try:
        with st.spinner(random.choice(loading_messages)):
            # Perform all API calls inside spinner
            cuisine_choice = random.choice(CUISINES)
            monday_date = get_next_monday_date()

            sheets_service, calendar_service = build_google_clients()
            history_ids = fetch_history_place_ids(sheets_service)
            places = search_places(cuisine_choice)
            chosen_place = choose_place(places, history_ids)

            if not chosen_place:
                st.warning(
                    "🎰 No eligible restaurants found for that cuisine. Try rolling again!"
                )
                st.stop()

            history_row = format_history_row(chosen_place, cuisine_choice, monday_date)
            append_history_row(sheets_service, history_row)
            create_calendar_event(calendar_service, chosen_place, monday_date)
        
        # ============================================================================
        # 🎉 CELEBRATION - Trigger balloons immediately on success!
        # ============================================================================
        st.balloons()
        
        # ============================================================================
        # THE REVEAL - Dramatic result card with border
        # ============================================================================
        with st.container(border=True):
            # Restaurant name with gradient styling
            st.markdown(f"""
                <div class="restaurant-name" style="text-align: center; margin-bottom: 1rem;">
                    {get_place_name(chosen_place)}
                </div>
            """, unsafe_allow_html=True)
            
            # Cuisine badge
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span style="
                        background: linear-gradient(135deg, var(--primary-gradient-start), var(--primary-gradient-end));
                        color: white;
                        padding: 8px 20px;
                        border-radius: 20px;
                        font-weight: 600;
                        font-size: 1rem;
                        letter-spacing: 0.05em;
                    ">
                        🍴 {cuisine_choice}
                    </span>
                </div>
            """, unsafe_allow_html=True)
            
            # ============================================================================
            # METRICS OVER TEXT - Use st.metric for rating and reviews
            # ============================================================================
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label="⭐ Rating",
                    value=f"{chosen_place.get('rating', 'N/A')}"
                )
            
            with col2:
                reviews_count = chosen_place.get('userRatingCount', 0)
                st.metric(
                    label="💬 Reviews",
                    value=f"{reviews_count:,}" if isinstance(reviews_count, int) else reviews_count
                )
            
            with col3:
                price_level = chosen_place.get('priceLevel', 'N/A')
                price_display = '💰' * len(price_level) if isinstance(price_level, str) and price_level != 'N/A' else price_level
                st.metric(
                    label="💵 Price",
                    value=price_display
                )
            
            # Spacer
            st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)
            
            # ============================================================================
            # CALL TO ACTION - Primary action button for Google Maps
            # ============================================================================
            maps_uri = chosen_place.get("googleMapsUri")
            if maps_uri:
                st.link_button(
                    label="📍 View on Google Maps",
                    url=maps_uri,
                    use_container_width=True,
                    type="primary"
                )
        
        # Success messages with spacing
        st.markdown("<div style='margin: 1.5rem 0;'></div>", unsafe_allow_html=True)
        
        col_success1, col_success2 = st.columns(2)
        with col_success1:
            st.success("✅ History Updated")
        with col_success2:
            st.success("📅 Calendar Invite Sent")
            
    except requests.HTTPError as exc:
        st.error(f"🚨 Places API error: {exc}")
    except Exception as exc:
        st.error(f"🚨 Something went wrong: {exc}")

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


st.set_page_config(page_title="Weekly New Restaurant Night", page_icon="🍽️")
st.header("Weekly New Restaurant Night")

if st.button("Roll the Dice"):
    try:
        cuisine_choice = random.choice(CUISINES)
        monday_date = get_next_monday_date()

        sheets_service, calendar_service = build_google_clients()
        history_ids = fetch_history_place_ids(sheets_service)
        places = search_places(cuisine_choice)
        chosen_place = choose_place(places, history_ids)

        if not chosen_place:
            st.warning(
                "No eligible restaurants found for that cuisine. Try rolling again."
            )
            st.stop()

        history_row = format_history_row(chosen_place, cuisine_choice, monday_date)
        append_history_row(sheets_service, history_row)
        create_calendar_event(calendar_service, chosen_place, monday_date)

        st.subheader(get_place_name(chosen_place))
        st.write(
            f"{cuisine_choice} | {chosen_place.get('rating', 'N/A')} ⭐"
        )
        maps_uri = chosen_place.get("googleMapsUri")
        if maps_uri:
            st.markdown(f"[View on Google Maps]({maps_uri})")

        st.success("History Updated")
        st.success("Calendar Invite Sent")
    except requests.HTTPError as exc:
        st.error(f"Places API error: {exc}")
    except Exception as exc:
        st.error(f"Something went wrong: {exc}")

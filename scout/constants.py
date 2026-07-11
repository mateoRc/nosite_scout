"""Shared application constants and the canonical lead schema."""

DEFAULT_KEYWORDS = [
    "restaurants", "cafes", "apartments", "plumbers", "electricians",
    "beauty_salon", "massage", "wellness_spa", "physiotherapy", "mechanics",
    "dentists", "private_clinics", "small_shops", "local_services",
]

LEAD_COLUMNS = [
    "place_id", "name", "category", "address", "city", "phone",
    "formatted_phone_number", "international_phone_number", "phone_preferred",
    "mobile_phone", "has_phone", "website", "google_maps_url", "rating",
    "review_count", "no_website", "likely_small_business",
    "prospect_probability", "prospect_tier", "source", "status", "assigned_to",
    "next_follow_up_at", "last_contacted_at", "do_not_contact", "estimated_value",
    "notes", "email", "contact_page_url", "facebook_url", "instagram_url",
    "whatsapp_url", "created_at", "updated_at",
]

PROFILE_DOMAINS = (
    "facebook.com", "instagram.com", "linktr.ee", "booking.com", "tripadvisor.",
    "whatsapp.com", "wa.me", "google.com/maps", "business.site",
)

CHAIN_WORDS = (
    "mcdonald", "burger king", "kfc", "lidl", "kaufland", "spar", "dm", "bipa",
    "zara", "h&m", "tommy", "konzum", "plodine",
)

LOCAL_CITIES = (
    "istria", "istra", "croatia", "hrvatska", "pula", "rovinj", "porec", "poreč",
    "umag", "novigrad", "labin", "pazin", "buzet", "motovun", "medulin",
    "vodnjan", "fažana", "fazana",
)

LOCAL_CATEGORIES = (
    "restaurant", "cafe", "lodging", "apartment", "plumber", "electrician",
    "beauty", "massage", "spa", "physiotherapist", "fitness_centre", "mechanic",
    "dentist", "clinic", "doctors", "veterinary", "photographer", "store", "shop",
    "local_service",
)

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_RETRY_STATUSES = {429, 502, 503, 504}
DEFAULT_OSM_RADIUS_KM = 25.0
DETAIL_FIELDS = ",".join(
    ["place_id", "name", "formatted_address", "formatted_phone_number",
     "international_phone_number", "website", "url", "rating",
     "user_ratings_total", "types"]
)

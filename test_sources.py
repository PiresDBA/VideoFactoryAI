import requests
import json

PIXABAY_KEY = "58184749-b92df4cd039274d2c7a6aac7a"

def get_pixabay_video(query):
    url = "https://pixabay.com/api/videos/"
    params = {"key": PIXABAY_KEY, "q": query, "per_page": 3, "safesearch": "true"}
    try:
        r = requests.get(url, params=params, timeout=10)
        hits = r.json().get("hits", [])
        if hits:
            vids = hits[0].get("videos", {})
            for q in ["large", "medium", "small"]:
                if q in vids and vids[q].get("url"):
                    return vids[q]["url"], hits[0].get("tags")
    except Exception as e:
        pass
    return None, None

def get_wikimedia_image(query):
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 3,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json"
    }
    headers = {"User-Agent": "HistoricalDocumentaryBot/2.0 (research-bot; agent@antigravity.dev)"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        for pid, p in pages.items():
            ii = p.get("imageinfo", [{}])[0]
            mime = ii.get("mime", "")
            if mime in ["image/jpeg", "image/png"]:
                return ii.get("url"), p.get("title")
    except Exception as e:
        pass
    return None, None

# Test the historical archival images on Wikimedia Commons
archival_tests = [
    ("Mohammad Mossadegh 1953 trial", "Scene 06 - 1953 Coup"),
    ("Mohammad Reza Pahlavi Shah portrait", "Scene 07 - Shah Pahlavi"),
    ("Ruhollah Khomeini 1979 portrait", "Scene 08 - Khomeini 1979"),
    ("Iran hostage crisis Tehran 1979 embassy", "Scene 09 - Hostage Crisis"),
    ("Azadi Tower Tehran Iran", "Scene 15 - Tehran Landmark"),
    ("Iranian Parliament Majlis Tehran", "Scene 18 - Iranian Majlis Government")
]

print("--- TESTING WIKIMEDIA ARCHIVAL SOURCES ---")
for q, desc in archival_tests:
    url, title = get_wikimedia_image(q)
    print(f"[{desc}] '{q}' -> {title}")
    if url:
        print(f"   URL: {url[:80]}...")

print("\n--- TESTING PIXABAY VIDEO SOURCES ---")
video_tests = [
    ("american flag waving", "Scene 01 - USA Flag"),
    ("military warship naval ocean", "Scene 02 - Military / Sanctions"),
    ("news broadcast studio television", "Scene 03 - News"),
    ("world map rotating globe", "Scene 04 - Geopolitics Map"),
    ("oil pump jack desert oilfield", "Scene 05 - Oil Cold War"),
    ("white house washington dc", "Scene 10 - White House"),
    ("desert military tank convoy", "Scene 11 - Middle East Allies"),
    ("nuclear power plant cooling towers", "Scene 12 - Nuclear Program"),
    ("diplomats meeting table negotiation", "Scene 13 - Nuclear Treaty"),
    ("oil tanker cargo ship sea", "Scene 14 - Strait of Hormuz"),
    ("aircraft carrier ocean military", "Scene 16 - US Military Presence"),
    ("money counting cash inflation", "Scene 17 - Sanctions Inflation"),
    ("laboratory scientist microscope research", "Scene 19 - Science / Technology"),
    ("oil refinery industrial plant sunset", "Scene 20 - Global Energy Market"),
    ("gas station fuel pump car", "Scene 21 - Fuel Inflation"),
    ("cyber attack digital data screen", "Scene 22 - Proxy Cyber Wars"),
    ("refugee camp humanitarian crisis", "Scene 23 - Humanitarian Crisis"),
    ("chess board strategy game", "Scene 24 - Global Chessboard"),
    ("military smoke explosion war", "Scene 25 - War Destruction Costs"),
    ("united nations flags international", "Scene 26 - UN Diplomacy"),
    ("youtube subscribe bell button", "Scene 27 - Call to Action")
]

for q, desc in video_tests:
    url, tags = get_pixabay_video(q)
    print(f"[{desc}] '{q}' -> Tags: {tags}")
    if url:
        print(f"   URL: {url[:80]}...")

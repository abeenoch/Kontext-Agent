import requests

def translate_text(payload: dict):
    text = payload.get("text")
    target = payload.get("target", "fr")
    url = "https://libretranslate.com/translate"
    resp = requests.post(url, data={"q": text, "source": "auto", "target": target, "format": "text"})
    if resp.ok:
        return {"ok": True, "translated": resp.json().get("translatedText")}
    return {"ok": False, "error": resp.text}

#!/usr/bin/env python3
"""data_probe.py — sinais REAIS realtime, GRATIS, keyless, SEM limite de token.
Google Trends RSS publico por geo (nao raspa painel autenticado nenhum). -> SIGNALS.json"""
import json, time, re, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (aether-probe)"}
GEOS = ["US", "BR", "GB"]
def get(url):
    try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read().decode("utf-8", "replace")
    except Exception: return ""
def trends(geo):
    xml = get("https://trends.google.com/trending/rss?geo=%s" % geo)
    out = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", item, re.S)
        tr = re.search(r"approx_traffic>(.*?)<", item, re.S)
        news = re.findall(r"<ht:news_item_title>(.*?)</ht:news_item_title>", item, re.S)
        if t: out.append({"term": re.sub(r"<.*?>", "", t.group(1)).strip(),
                          "traffic": (tr.group(1).strip() if tr else ""),
                          "news": [re.sub(r"<.*?>", "", n).strip() for n in news[:2]]})
    return out[:20]
def main():
    sig = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "geos": {}, "hot_terms": []}
    seen = set()
    for g in GEOS:
        tr = trends(g); sig["geos"][g] = tr
        for t in tr:
            k = t["term"].lower()
            if k and k not in seen: seen.add(k); sig["hot_terms"].append(t["term"])
    json.dump(sig, open("SIGNALS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DATA_PROBE: %d termos quentes reais | ex: %s" % (len(sig["hot_terms"]), ", ".join(sig["hot_terms"][:6])))
if __name__ == "__main__": main()

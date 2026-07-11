"""results_collector.py — fecha o loop de aprendizado do governador: coleta RESULTADOS REAIS
(views por video publicado no YouTube + inscritos/views do canal + vendas AWIN do state) e grava
RESULTS.json/.md. O governador le isso p/ priorizar o que de fato gera views/dinheiro."""
import os, json, time, urllib.request, urllib.parse, urllib.error

def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def yt_token():
    rt = os.environ.get("YT_RT_GLOBALSUP", "")
    cid = os.environ.get("YOUTUBE_CLIENT_ID") or os.environ.get("YT_CLIENT_ID")
    cs = os.environ.get("YOUTUBE_CLIENT_SECRET") or os.environ.get("YT_CLIENT_SECRET")
    if not (rt and cid and cs):
        return ""
    try:
        d = urllib.parse.urlencode({"client_id": cid, "client_secret": cs, "refresh_token": rt,
                                    "grant_type": "refresh_token"}).encode()
        return json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=d, timeout=25).read())["access_token"]
    except Exception:
        return ""

def yt_get(at, path, params):
    url = "https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(params)
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + at}), timeout=30).read())
    except Exception:
        return {}

def collect():
    res = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "videos": [], "channel": {}, "vendas": {}}
    # videos publicados (produto + short)
    vids = {}
    for f in ["data/products_published.json", "data/shorts_published.json"]:
        for it in (load(f, {}) or {}).get("published", []):
            if isinstance(it, dict) and it.get("video_id"):
                vids[it["video_id"]] = {"slug": it.get("slug"), "name": it.get("name", ""),
                                        "niche": it.get("niche", ""), "kind": "short" if "shorts" in f else "product"}
    at = yt_token()
    if at and vids:
        ids = list(vids.keys())
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            data = yt_get(at, "videos", {"part": "statistics,snippet", "id": ",".join(chunk)})
            for v in data.get("items", []):
                vid = v["id"]; st = v.get("statistics", {})
                vids[vid]["views"] = int(st.get("viewCount", 0) or 0)
                vids[vid]["likes"] = int(st.get("likeCount", 0) or 0)
                vids[vid]["title"] = v.get("snippet", {}).get("title", "")
        if at:
            ch = yt_get(at, "channels", {"part": "statistics", "mine": "true"})
            if ch.get("items"):
                s = ch["items"][0].get("statistics", {})
                res["channel"] = {"subs": int(s.get("subscriberCount", 0) or 0),
                                  "views": int(s.get("viewCount", 0) or 0),
                                  "videos": int(s.get("videoCount", 0) or 0)}
    res["videos"] = sorted(vids.values(), key=lambda x: -int(x.get("views", 0)))
    # vendas do state.json (AWIN ja coletado; ClickBank so ID)
    res["vendas"] = (load("state.json", {}) or {}).get("vendas", {})
    return res

def main():
    res = collect()
    json.dump(res, open("RESULTS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot_views = sum(int(v.get("views", 0)) for v in res["videos"])
    with open("RESULTS.md", "w", encoding="utf-8") as f:
        f.write("# RESULTADOS REAIS (o governador aprende com isso)\n\n")
        f.write("Atualizado: %s\n\n" % res["ts"])
        ch = res.get("channel", {})
        f.write("Canal: %s inscritos | %s views totais | %s videos | VIEWS somadas dos posts: %d\n\n"
                % (ch.get("subs", "?"), ch.get("views", "?"), ch.get("videos", "?"), tot_views))
        f.write("## Videos por VIEWS (o que funciona)\n\n")
        for v in res["videos"][:40]:
            f.write("- %d views | %s | %s | %s\n" % (int(v.get("views", 0)), v.get("kind"), v.get("slug"), v.get("title", v.get("name", ""))[:60]))
        f.write("\n## Vendas\n\n- %s\n" % json.dumps(res.get("vendas", {}), ensure_ascii=False))
    print("RESULTS: %d videos | views totais=%d | canal=%s" % (len(res["videos"]), tot_views, res.get("channel")))

if __name__ == "__main__":
    main()

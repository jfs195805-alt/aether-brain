"""publish_shorts.py — publicador AUTÔNOMO de SHORTS VERTICAIS 9:16 (afiliado) para o canal
"Global Supplements" (inglês), rodando HEADLESS no GitHub Actions (ubuntu).

Reaproveita os MESMOS padrões de publish_products.py (fonte de produtos REAIS do site do usuário,
imagem OFICIAL REAL e INALTERADA, fundo premium via OpenAI gpt-image-1, TTS Gemini, OAuth/upload
do YouTube, convenções de env vars, saída graciosa e NUNCA imprimir segredos), mas:

  • Formato VERTICAL 9:16 (1080x1920), duração < 45s — vira YouTube Short automaticamente.
  • Estado rotacionado INDEPENDENTE em data/shorts_published.json (os shorts rotacionam os produtos
    separadamente dos vídeos longos de publish_products.py).
  • Roteiro PUNCHY ~90-130 palavras com HOOK na primeira frase (Gemini gemini-2.5-flash) + fallback.
  • LEGENDAS grandes queimadas no vídeo (drawtext animado, terço inferior, contorno preto).
  • Fundo gpt-image-1 PORTRAIT (1024x1536, quality high) — SÓ o cenário premium do nicho, sem produto
    e sem texto. Fallback: gradiente vertical premium via Pillow. Produto REAL composto por cima.
  • DISTRIBUIÇÃO dupla: (1) upload PUBLIC no YouTube (categoryId 26) via YT_RT_GLOBALSUP; (2) cópia do
    mp4 final para out/shorts/<slug>.mp4 (commitado pelo workflow p/ cross-post TikTok/Reels).
  • Se YT_RT_GLOBALSUP ausente, AINDA produz o mp4 (p/ TikTok/Reels) e sai gracioso (exit 0).

Reaproveita de publish_products.py: scrape_product_slugs, fetch_product_image_and_cta, pick_product
(rotação de ofertas), gen_voice/wav_duration (TTS que funciona), token()/api_upload() (OAuth+upload).
NUNCA imprime valores de segredos. NUNCA quebra o run (fallbacks em toda etapa de rede).
"""
import os
import json
import subprocess
import time, sys, json, base64, re, subprocess, time, math
import urllib.request, urllib.parse, urllib.error  # noqa: F401

# Importa os helpers REAIS já testados de publish_products.py (mesmo diretório).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_products as pp  # noqa: E402

# ── Config específica dos SHORTS ──────────────────────────────────────────────────────────────
CHANNEL_NAME = "GLOBAL SUPPLEMENTS"
STATE_FILE = os.environ.get("SHORTS_STATE_FILE", os.path.join("data", "shorts_published.json"))
OUT_DIR = os.path.join("out", "shorts")
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
OPENAI_IMAGE_MODEL = "gpt-image-1"
PRODUCT_BASE = pp.PRODUCT_BASE  # https://globalsupplements.site/
YEAR = "2026"
VW, VH = 1080, 1920          # vertical 9:16
MAX_SECS = 45                # cap duro de duração do short
ACCENT = pp.ACCENT

DISCLOSURE = ("Affiliate disclosure: some links are affiliate links and we may earn a commission "
              "at no extra cost to you.")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ESTADO — INDEPENDENTE dos vídeos longos (data/shorts_published.json)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("published", [])
                return d
    except Exception:
        pass
    return {"published": []}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("aviso: nao consegui salvar estado dos shorts:", str(e)[:80])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1) ROTEIRO PUNCHY com HOOK (Gemini gemini-2.5-flash) + fallback template
# ══════════════════════════════════════════════════════════════════════════════════════════════
def gen_short_script(name, niche, subkw):
    """Roteiro falado ~90-130 palavras, PUNCHY, com HOOK forte na 1ª frase (curiosity gap / POV /
    '3 things nobody tells you...'). Inglês, sem claim médico. Fallback template se a API falhar."""
    key = os.environ.get("GEMINI_API_KEY")
    prompt = (
        "You are writing a VERY PUNCHY vertical short-video voiceover script in ENGLISH about the "
        f"supplement product \"{name}\" (niche: {niche}). STRICT RULES:\n"
        "- 90 to 130 words total (spoken in UNDER 40 seconds).\n"
        "- The FIRST sentence MUST be a scroll-stopping HOOK: use a curiosity gap, a 'POV:' framing, "
        "or a pattern like '3 things nobody tells you about " + name + "...'.\n"
        "- Fast, conversational, high-energy, TikTok/Shorts style. Short sentences.\n"
        "- Honest and balanced. NO medical claims, NO promises to cure/treat/prevent, NO dosages.\n"
        "- End with a soft call to action to check the honest review in the link.\n"
        "- Output ONLY the spoken words. No headings, no stage directions, no emojis, no markdown.\n"
        f"PROVEN viral hooks/angles mined from top creators across 591 channels (ADAPT, never copy): "
        f"{pp.strategy_snippets(name + ' ' + niche)}. Use ONE as the hook style.\n"
        f"Naturally weave in a few of: {', '.join(subkw)}."
    )
    try:
        import ai_providers
        txt = (ai_providers.ask(prompt, max_tokens=400) or "").strip()
        if txt:
            words = txt.split()
            if len(words) > 135:
                txt = " ".join(words[:135])
            if len(txt) > 60:
                return txt
    except Exception as e:
        print("aviso: IA roteiro (short) falhou, usando template:", str(e)[:80])
    sk0 = subkw[0] if subkw else "wellness"
    sk1 = subkw[1] if len(subkw) > 1 else "energy"
    return (
        f"Three things nobody tells you about {name}. "
        f"First, most people pick it for {sk0}, but the label is what really matters. "
        "Check the form, the amount per serving, and whether it's third-party tested. "
        "Second, clean ingredients beat fancy marketing every single time, so skip the fillers. "
        f"Third, it works best with real sleep, real food, and movement, not on its own, and results "
        f"vary from person to person around {sk1}. "
        "This is general info, not medical advice. "
        "Want the honest, no-hype breakdown? The full review is in the link below."
    )


def make_hook_line(script, name):
    """Extrai a 1ª frase do roteiro como HOOK curto p/ título/descrição."""
    first = re.split(r"(?<=[.!?])\s+", script.strip())[0] if script.strip() else name
    first = re.sub(r"\s+", " ", first).strip().rstrip(".!?")
    return first[:70]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2) FUNDO VERTICAL premium — OpenAI gpt-image-1 (1024x1536) -> 1080x1920; fallback Pillow
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _bg_prompt_vertical(niche):
    palette = {
        "sleep": "calming deep blue and soft violet tones",
        "focus": "cool electric blue and clean white tones",
        "energy": "vibrant warm amber and orange sunrise tones",
        "weight loss": "fresh green and bright airy tones",
        "blood sugar": "balanced teal and green tones",
        "prostate": "confident deep navy blue tones",
        "tinnitus": "soft calming aqua and blue tones",
        "dental": "fresh mint and clean bright white tones",
        "nail": "warm beige and soft rose tones",
        "gut": "fresh green and clean airy white tones",
    }.get((niche or "").lower(), "premium brand-color tones")
    return (
        f"A premium, cinematic, high-converting VERTICAL 9:16 advertising BACKGROUND scene for a "
        f"{niche} wellness supplement short-form ad, {palette}. Studio product-photography lighting, "
        "soft depth of field, luxurious clean surface with subtle glow and elegant bokeh, generous "
        "empty space in the upper-center to place a product later. NO product, NO bottle, NO text, "
        "NO watermark, NO logos, NO people. Tall vertical composition, ultra sharp, photorealistic, "
        "advertising quality."
    )


def gen_background_openai_vertical(niche, out_png):
    """PRIMÁRIO: fundo VERTICAL premium via OpenAI gpt-image-1 (REST /v1/images/generations).
    model='gpt-image-1', size '1024x1536' (portrait), quality 'high'. Resposta b64 -> PIL -> 1080x1920.
    Requer OPENAI_API_KEY; se vazio, PULA. Nunca lança; degrada graciosamente."""
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return False
    try:
        url = "https://api.openai.com/v1/images/generations"
        body = json.dumps({
            "model": OPENAI_IMAGE_MODEL,
            "prompt": _bg_prompt_vertical(niche),
            "size": "1024x1536",
            "quality": "high",
            "n": 1,
        }).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        data0 = (r.get("data") or [{}])[0]
        b64 = data0.get("b64_json")
        raw = None
        if b64:
            raw = base64.b64decode(b64)
        elif data0.get("url"):
            raw = pp.http_get(data0["url"], timeout=60, binary=True)
        if raw:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(raw)).convert("RGB").resize((VW, VH))
            im.save(out_png, "PNG")
            print("[IMG] fundo vertical IA gerado via OpenAI " + OPENAI_IMAGE_MODEL + " (primario)")
            return True
    except urllib.error.HTTPError as e:
        print("aviso: OpenAI " + OPENAI_IMAGE_MODEL + " HTTP " + str(e.code) + " — fallback")
    except Exception as e:
        print("aviso: OpenAI " + OPENAI_IMAGE_MODEL + " (vertical) falhou:", str(e)[:70])
    return False


def premium_gradient_bg_vertical(niche, out_png):
    """Fallback GARANTIDO: fundo vertical premium (navy escuro + glow de acento) via Pillow. 1080x1920."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return False
    W, H = VW, VH
    img = Image.new("RGB", (W, H), (8, 12, 20))
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(8 + 20 * t), int(12 + 28 * t), int(20 + 36 * t)))
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - 620, int(H * 0.30) - 620, W // 2 + 620, int(H * 0.30) + 620], fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    tint = Image.new("RGB", (W, H), ACCENT)
    img = Image.composite(tint, img, glow.point(lambda x: int(x * 0.42)))
    img.save(out_png, "PNG")
    print("[IMG] fundo vertical premium (Pillow fallback) gerado")
    return True


def composite_vertical_key_frame(bg_png, product_png, out_png, has_product):
    """Compoe o PRODUTO REAL grande, centralizado-superior, INTACTO, sobre o fundo vertical 1080x1920.
    Adiciona sombra suave. Pixels do produto nunca alterados. Retorna True se salvou."""
    try:
        from PIL import Image, ImageDraw, ImageFilter  # noqa: F401
    except Exception:
        return False
    try:
        bg = Image.open(bg_png).convert("RGBA").resize((VW, VH))
    except Exception:
        return False
    if has_product and product_png and os.path.exists(product_png):
        try:
            prod = Image.open(product_png).convert("RGBA")
            # produto GRANDE: ~46% da altura do frame vertical
            target_h = int(VH * 0.46)
            ratio = target_h / prod.height
            new_w = max(1, int(prod.width * ratio))
            if new_w > int(VW * 0.86):  # não deixar transbordar na largura
                new_w = int(VW * 0.86)
                ratio = new_w / prod.width
                target_h = max(1, int(prod.height * ratio))
            prod = prod.resize((new_w, target_h))
            # centralizado horizontalmente, na porção SUPERIOR (centro-superior)
            px = (VW - prod.width) // 2
            py = int(VH * 0.16)
            # sombra suave
            shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            sh = Image.new("RGBA", prod.size, (0, 0, 0, 150))
            sh.putalpha(prod.split()[-1])
            shadow.paste(sh, (px + 16, py + 26), sh)
            shadow = shadow.filter(ImageFilter.GaussianBlur(30))
            bg = Image.alpha_composite(bg, shadow)
            bg.paste(prod, (px, py), prod)
        except Exception as e:
            print("aviso: composicao vertical do produto falhou:", str(e)[:60])
    bg.convert("RGB").save(out_png, "PNG")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3) LEGENDAS — burn-in de subtítulos grandes, animados, terço inferior, contorno preto
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _caption_font_file():
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return p
    return None


def _ff_escape_path(path):
    """Escapa um caminho p/ uso dentro de opção de filtro do ffmpeg (drawtext fontfile/textfile)."""
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def split_caption_chunks(script, max_chars=16):
    """Blocos curtos por CARACTERE (<=16) para caber em 1 linha sem cortar na borda."""
    words = re.sub(r"\s+", " ", (script or "").strip()).split()
    chunks, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            chunks.append(cur); cur = w
    if cur:
        chunks.append(cur)
    return chunks or ["Global Supplements"]


_CAP_QA = {}


def _ffdur(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                              "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def qa_short_video(vpath, apath, has_product, bg_ai):
    """Pontua 0-100: legendas cabem (30) + sync voz/legenda (30) + fundo IA (20) + produto (20)."""
    score = 0; issues = []
    if _CAP_QA.get("fits", True):
        score += 30
    else:
        issues.append("legenda pode cortar (maxlen=%s F=%s)" % (_CAP_QA.get("maxlen"), _CAP_QA.get("fontsize")))
    ad = _ffdur(apath); vd = _ffdur(vpath); span = _CAP_QA.get("sum_spans", vd)
    if ad > 0 and abs(span - ad) <= 1.3 and abs(vd - ad) <= 1.6:
        score += 30
    else:
        issues.append("sync audio=%.1f video=%.1f legendas=%.1f" % (ad, vd, span))
    if bg_ai:
        score += 20
    else:
        issues.append("fundo caiu no gradiente (nao-IA)")
    if has_product:
        score += 20
    else:
        issues.append("sem produto real")
    return score, issues


def build_caption_drawtext_filters(script, secs, tmpdir):
    """Legendas grandes, centralizadas, terco inferior, SEMPRE cabendo (fonte dinamica).
    Timing proporcional ao tamanho do texto. Guarda QA em _CAP_QA."""
    global _CAP_QA
    fontfile = _caption_font_file()
    if not fontfile:
        print("aviso: fonte DejaVu ausente — short seguira SEM legendas")
        _CAP_QA = {"fits": False, "maxlen": 0, "fontsize": 0, "sum_spans": 0.0, "n": 0}
        return []
    chunks = split_caption_chunks(script, max_chars=14)
    n = len(chunks)
    maxlen = max(len(ch) for ch in chunks)
    avail = VW - 180
    fontsize = int(avail / (0.62 * max(1, maxlen)))
    fontsize = max(32, min(48, fontsize))
    fits = (maxlen * 0.62 * fontsize) <= avail
    weights = [max(1, len(ch)) for ch in chunks]
    tot = float(sum(weights)) or 1.0
    spans, acc = [], 0.0
    for w in weights:
        d = float(secs) * (w / tot)
        spans.append((acc, min(float(secs), acc + d))); acc += d
    ff_font = _ff_escape_path(fontfile)
    filters = []
    for i, chunk in enumerate(chunks):
        start = round(spans[i][0], 3); end = round(spans[i][1], 3)
        if end <= start:
            end = round(start + 0.3, 3)
        cap_path = os.path.join(tmpdir, "gs_short_cap_%03d.txt" % i)
        try:
            with open(cap_path, "w", encoding="utf-8") as f:
                f.write(chunk.upper())
        except Exception:
            continue
        ff_txt = _ff_escape_path(cap_path)
        dt = ("drawtext=fontfile='%s':textfile='%s':"
              "fontcolor=white:fontsize=%d:borderw=5:bordercolor=black:"
              "box=1:boxcolor=black@0.42:boxborderw=16:"
              "x=(w-text_w)/2:y=h*0.72:"
              "enable='between(t,%s,%s)'" % (ff_font, ff_txt, fontsize, start, end))
        filters.append(dt)
    _CAP_QA = {"fits": fits, "maxlen": maxlen, "fontsize": fontsize,
               "sum_spans": round(acc, 2), "n": n}
    return filters


def make_short_video(bg_path, audio_path, out_path, duration, script, product_path=None):
    """Vertical 1080x1920: FUNDO VIRAL em movimento (zoompan) + (opcional) PRODUTO flutuando por cima
    + LEGENDAS queimadas sincronizadas. Se product_path dado, usa filter_complex (produto anima). H.264/AAC."""
    secs = max(5, min(MAX_SECS, int(math.ceil(duration))))
    frames = secs * 30
    tmpdir = os.path.dirname(os.path.abspath(out_path)) or "."
    up_w, up_h = int(VW * 1.2), int(VH * 1.2)
    zoom = ("zoompan=z='min(zoom+0.0004,1.10)':d=%d:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=30"
            % (frames, VW, VH))
    caps = build_caption_drawtext_filters(script, secs, tmpdir)
    if product_path and os.path.exists(product_path):
        ph = int(VH * 0.42); amp = max(8, int(VH * 0.02)); per = 3.0
        caps_chain = ("," + ",".join(caps)) if caps else ""
        fc = ("[0:v]scale=%d:%d,%s,format=yuv420p[bg];"
              "[1:v]scale=-1:%d,format=rgba[pp];"
              "[bg][pp]overlay=x='(W-w)/2':y='H*0.16+%d*sin(2*PI*t/%s)':eval=frame:shortest=1%s,format=yuv420p[v]"
              % (up_w, up_h, zoom, ph, amp, per, caps_chain))
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", bg_path, "-loop", "1", "-i", product_path,
               "-i", audio_path, "-t", str(secs), "-filter_complex", fc, "-map", "[v]", "-map", "2:a",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-shortest", "-movflags", "+faststart", out_path]
    else:
        vf = ",".join(["scale=%d:%d" % (up_w, up_h), zoom] + caps + ["format=yuv420p"])
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", bg_path, "-i", audio_path, "-t", str(secs),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-vf", vf,
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               "-shortest", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return secs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4) VIRAL — título keyword-first + hook, descrição hook + CTA + disclosure + hashtags
# ══════════════════════════════════════════════════════════════════════════════════════════════
def viral_short_title(name, hook):
    """Título keyword-first (nome REAL do produto primeiro) + hook. < 80 chars."""
    base = f"{name}: {hook}".strip().rstrip(":")
    cand = (base + f" #shorts").strip()
    if len(cand) >= 80:
        cand = f"{name}: Honest Truth ({YEAR}) #shorts"
    if len(cand) >= 80:
        cand = f"{name} — Honest Review #shorts"
    return cand[:79]


def _niche_hashtags(niche):
    m = {
        "weight loss": ["weightloss", "fatloss"],
        "blood sugar": ["bloodsugar", "glucose"],
        "tinnitus": ["tinnitus", "hearinghealth"],
        "prostate": ["menshealth", "prostatehealth"],
        "focus": ["focus", "brainhealth"],
        "sleep": ["sleep", "sleepaid"],
        "dental": ["dentalhealth", "oralcare"],
        "nail": ["nailhealth", "beauty"],
        "gut": ["guthealth", "probiotics"],
    }.get((niche or "").lower(), ["healthtips"])
    return m


def short_description(name, niche, hook, cta_url, retailer_url=None):
    tags = ["supplements", "tiktokmademebuyit", "wellness"] + _niche_hashtags(niche) + ["shorts"]
    # 3-5 hashtags principais (dedupe, cap 5) + garante minimo 3
    seen, hashtags = set(), []
    for t in tags:
        tt = re.sub(r"[^a-z0-9]", "", t.lower())
        if tt and tt not in seen:
            seen.add(tt)
            hashtags.append("#" + tt)
        if len(hashtags) >= 5:
            break
    lines = [f"{hook}."]
    lines += ["", "Full honest review & best price:", f"-> {cta_url}"]
    if retailer_url:
        lines += ["", "Check current price:", "-> " + retailer_url]
    lines += ["", DISCLOSURE]
    lines += ["", " ".join(hashtags)]
    desc = "\n".join(lines)
    return desc.replace("<", "").replace(">", "")[:4990]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main():
    state = load_state()

    # 1) FONTE DE PRODUTOS — próximo produto REAL não publicado nos SHORTS (rotação independente).
    #    Reaproveita pick_product() de publish_products.py (usa scrape_product_slugs + rotação),
    #    porém alimentado pelo NOSSO estado (data/shorts_published.json).
    # REGRA ZERO: so publica Short de produto com FOTO HD REAL na pagina de review.
    prod_png = pp._tmp("gs_short_product.png")
    slug = offer = info = None
    has_product = False
    noimg = []
    for _ in range(30):
        s, o = pp.pick_product(state, exclude=noimg)
        if not s:
            break
        i = pp.fetch_product_image_and_cta(s, prod_png)
        if i.get("has_image"):
            slug, offer, info, has_product = s, o, i, True
            break
        print(f"[REGRA-ZERO] {s}: SEM foto HD real na review — pulando (proibido publicar sem foto).")
        noimg.append(s)
    if not has_product:
        print("[REGRA-ZERO] nenhum produto com foto HD neste ciclo — nada publicado (exit 0).")
        return
    if info.get("title"):
        offer["name"] = info["title"]
    offer["image_url"] = info.get("image_url")
    offer["retailer_url"] = info.get("retailer_url")
    offer["affiliate_url"] = info["cta_url"]        # CTA = página de review REAL (nunca a raiz)
    offer["official_page_url"] = info["cta_url"]
    cta_url = info["cta_url"]

    name = offer["name"]
    niche = offer["niche"]
    print(f"[SHORTS] produto REAL: {name} | slug={slug} | nicho={niche} | CTA={cta_url} "
          f"| imagem_oficial={'sim' if has_product else 'nao'}")

    # roteiro PUNCHY com HOOK + locução (TTS Gemini reaproveitado de publish_products.py)
    import random as _rnd
    mhook = pp.magnetic_hook(name, niche)
    SILENT = (os.environ.get("SHORTS_SILENT", "") == "1") or (_rnd.random() < float(os.environ.get("SILENT_PCT", "0.25")))
    apath = pp._tmp("gs_short_voice.wav")
    if SILENT:
        # MODO SEM FALA (PDF Provador Omni Flash): ganchos magneticos + movimento + musica, ZERO voz
        # (evita risco de voz-IA desmonetizar). As legendas SAO o conteudo.
        hks = [h for h in ([mhook] + [pp.magnetic_hook(name, niche) for _ in range(2)]) if h]
        script = "  ".join(hks) or (name + " - honest review")
        hook = mhook or script[:60]
        dur = 12.0
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                            "-t", "12", "-c:a", "pcm_s16le", apath], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pp.gen_voice(" ", apath)
        print("[SHORTS] MODO SILENCIOSO (sem fala): ganchos magneticos + musica")
    else:
        script = gen_short_script(name, niche, offer["subkw"])
        if mhook:
            script = mhook + " " + script  # abre com gancho magnetico
        hook = make_hook_line(script, name)
        if not pp.gen_voice(script, apath):
            raise SystemExit("erro: nao foi possivel gerar locucao nem silencio de fallback")
        dur = min(pp.wav_duration(apath), MAX_SECS)
    print(f"[SHORTS] roteiro: {len(script.split())} palavras | hook='{hook}' | silent={SILENT}")

    # produto real intacto -> opcional matte -> fundo IA vertical -> composição vertical
    if has_product:
        prod_png = pp.maybe_remove_bg(prod_png)

    bg_png = pp._tmp("gs_short_bg.png")
    bg_ai = False
    if pp.gen_background_pollinations(niche, bg_png, W=VW, H=VH):
        bg_ai = True
    elif gen_background_openai_vertical(niche, bg_png):
        bg_ai = True
    elif premium_gradient_bg_vertical(niche, bg_png):
        bg_ai = False
    else:
        raise SystemExit("erro: Pillow indisponivel para gerar fundo vertical")

    vpath = pp._tmp("gs_short_out.mp4")
    if has_product and prod_png and os.path.exists(prod_png):
        try:
            real_secs = make_short_video(bg_png, apath, vpath, dur, script, product_path=prod_png)
        except Exception as e:
            print("aviso: short dinamico falhou, usando estatico:", str(e)[:70])
            key_png = pp._tmp("gs_short_key.png")
            if not composite_vertical_key_frame(bg_png, prod_png, key_png, has_product):
                key_png = bg_png
            real_secs = make_short_video(key_png, apath, vpath, dur, script)
    else:
        key_png = pp._tmp("gs_short_key.png")
        if not composite_vertical_key_frame(bg_png, prod_png, key_png, has_product):
            key_png = bg_png
        real_secs = make_short_video(key_png, apath, vpath, dur, script)
    print(f"[SHORTS] video {os.path.getsize(vpath) / 1e6:.1f}MB @1080x1920 | {real_secs}s "
          f"(Ken Burns + legendas)")

    # MUSICA DE FUNDO automatica (CC-BY, gratis) sob a locucao
    vpath = pp.mix_bg_music(vpath, niche)

    # ── QA + NOTA (teste antes de publicar): legendas cabem? sync? fundo IA? produto? ───────────
    score, issues = qa_short_video(vpath, apath, has_product, bg_ai)
    try:
        os.makedirs(os.path.join("data", "qa"), exist_ok=True)
        frame_png = os.path.join("data", "qa", slug + "_short.png")
        tsec = max(0.5, min(float(real_secs) - 0.3, float(real_secs) * 0.5))
        subprocess.run(["ffmpeg", "-y", "-ss", str(tsec), "-i", vpath, "-vframes", "1",
                        "-q:v", "2", frame_png], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(os.path.join("data", "qa", slug + "_short.json"), "w", encoding="utf-8") as f:
            json.dump({"slug": slug, "score": score, "issues": issues,
                       "cap": _CAP_QA, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
        print("[QA] frame salvo:", frame_png)
    except Exception as e:
        print("aviso: extracao de frame QA falhou:", str(e)[:70])
    print("[QA] nota=%d/100 | %s" % (score, "OK" if not issues else "; ".join(issues)))
    QA_MIN = int(os.environ.get("QA_MIN", "80"))
    if os.environ.get("SHORTS_DRY_RUN", "") == "1":
        print("[QA] DRY_RUN=1 — frame+nota salvos, NAO publicando (apenas teste).")
        return
    if score < QA_MIN:
        print("[QA] nota %d < %d — BLOQUEADO, nao publicando este video." % (score, QA_MIN))
        return

    # ── SALVA cópia do mp4 no repo (out/shorts/<slug>.mp4) p/ cross-post TikTok/Reels ───────────
    os.makedirs(OUT_DIR, exist_ok=True)
    repo_mp4 = os.path.join(OUT_DIR, slug + ".mp4")
    try:
        import shutil
        shutil.copyfile(vpath, repo_mp4)
        print("[SHORTS] mp4 salvo para cross-post: " + repo_mp4)
    except Exception as e:
        print("aviso: nao consegui copiar mp4 p/ out/shorts:", str(e)[:80])
        repo_mp4 = vpath

    # 3) VIRAL packaging
    title = viral_short_title(name, hook).replace("<", "").replace(">", "")[:100]
    desc = short_description(name, niche, hook, cta_url, offer.get("retailer_url"))
    desc = (desc or "") + "\n\n" + pp.AI_DISCLOSURE + "\n" + pp.MUSIC_ATTR
    tags = pp.build_tags(name, offer["subkw"], niche)

    # ── DISTRIBUIÇÃO (1): upload PUBLIC no YouTube (vira Short por ser vertical <60s) ────────────
    rt = os.environ.get("YT_RT_GLOBALSUP", "").strip()
    cid, cs = pp._client()
    vid = None
    if not rt or not cid or not cs:
        print("YT_RT_GLOBALSUP/CLIENT ausentes — pulei o upload no YouTube. "
              "mp4 PRONTO para TikTok/Reels. Saindo gracioso (exit 0).")
    else:
        try:
            at = pp.token(rt)
            meta = {"snippet": {"title": title, "description": desc, "tags": tags,
                                "categoryId": "26", "defaultLanguage": "en"},
                    "status": {"privacyStatus": os.environ.get("PRIVACY", "public").strip(),
                               "selfDeclaredMadeForKids": False, "madeForKids": False}}
            out = pp.api_upload(at, meta, vpath)
            vid = out.get("id")
            print("[SHORTS] PUBLICADO (YouTube Short) https://youtube.com/shorts/" + str(vid))
        except Exception as e:
            print("aviso: upload YouTube falhou (mp4 ainda disponivel p/ TikTok/Reels):", str(e)[:120])

    # registra short publicado (rotação independente por slug)
    record = {"slug": slug, "name": name, "niche": niche, "affiliate_url": cta_url,
              "official_page_url": offer.get("official_page_url"),
              "retailer_url": offer.get("retailer_url"),
              "image_url": offer.get("image_url") if has_product else None,
              "mp4": repo_mp4, "video_id": vid,
              "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    state.setdefault("published", []).append(record)
    state["last"] = record
    save_state(state)

    # DISTRIBUIÇÃO (2): imprime caminho do mp4 + link da CTA (p/ cross-post manual/Postiz)
    print("[SHORTS] MP4 PRONTO (TikTok/Reels): " + repo_mp4)
    print("[SHORTS] CTA / review link: " + cta_url)
    print("[SHORTS] concluido | slug=" + slug + " | yt_id=" + str(vid)
          + " | publicados=" + str(len(state["published"])))


if __name__ == "__main__":
    main()
# regra-zero shorts publisher v1 (produtos REAIS do site + imagem OFICIAL intacta; vertical 9:16
# <45s; fundo OpenAI gpt-image-1 portrait -> Pillow; Ken Burns + legendas queimadas; YouTube Short
# PUBLIC + mp4 out/shorts/<slug>.mp4 p/ TikTok/Reels)
# EOF

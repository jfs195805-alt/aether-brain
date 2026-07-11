"""publish_products.py — publicador AUTÔNOMO de vídeos de PRODUTO (afiliado) para o canal
"Global Supplements" (inglês), rodando HEADLESS no GitHub Actions (ubuntu).

REGRA ZERO ETERNA implementada aqui (ver REGRA_ZERO_ETERNA.md + AETHER_PRODUCT_RANKING.md):

  1. FONTE DE PRODUTOS = produtos REAIS do site do usuario. Raspa
     https://globalsupplements.site/products/ e coleta os slugs das paginas de review
     (https://globalsupplements.site/<slug>/). Se o fetch falhar, cai para uma lista fixa de slugs.
     Estado rotacionado em data/products_published.json (rastreado por SLUG — nao repete produto).

  2. PRODUTO ESCOLHIDO: busca a pagina de review e extrai TITLE (og:title/h1), a IMAGEM OFICIAL REAL
     (og:image) e a CTA = a propria URL da review (NUNCA a raiz do site). Amazon/ClickBank ficam so
     se ja presentes na pagina. IMAGEM: baixa a og:image REAL, NITIDA e INALTERADA (pixels intactos,
     nunca um produto inventado por IA). A IA gera SOMENTE o FUNDO premium (1024x1024 -> 1920x1080)
     via OpenAI gpt-image-1 (REST /v1/images/generations, OPENAI_API_KEY) — PRIMARIO. Fallbacks:
     Gemini image (opt-in) -> FLUX/HF (legacy) -> gradiente Pillow. Composicao do produto REAL
     grande/centralizado (com sombra suave) sobre o fundo via Pillow.

  3. MOVIMENTO: o key visual ganha Ken Burns (zoom/pan lento) via ffmpeg zoompan — nao fica estatico.

  4. VIRAL: titulo keyword-first (nome real do produto) + curiosidade + ano; descricao SEO
     multi-idioma com a CTA da pagina de review + disclosure de afiliado + inscricao;
     tags <= ~450 chars; thumbnail 1280x720 com a imagem REAL do produto + texto legivel + badge.

  5. INALTERADO: locucao Gemini TTS, refresh->access token do YouTube, upload resumable
     videos.insert (YT_RT_GLOBALSUP + YOUTUBE_CLIENT_ID/SECRET), thumbnails.set em try/except,
     categoryId "26", privacyStatus "public", saida graciosa (exit 0) se YT_RT_GLOBALSUP ausente.

Env: OPENAI_API_KEY (fundo), GEMINI_API_KEY (roteiro/TTS), YT_RT_GLOBALSUP,
     YOUTUBE_CLIENT_ID/SECRET (fallback YT_CLIENT_ID/SECRET), CLICKBANK_ID, AWIN_AFFID,
     AWIN_API_TOKEN, AMAZON_US_TAG, PRIVACY, STATE_FILE.
NUNCA imprime valores de segredos. NUNCA quebra o run (fallbacks em toda etapa de rede).
"""
import os
import json
import subprocess
import time
import re, sys, json, base64, wave, re, html, subprocess, time
import urllib.request, urllib.parse, urllib.error  # noqa: F401

# ENV: OPENAI_API_KEY (fundo premium gpt-image-1) | GEMINI_API_KEY (roteiro/TTS) | HF_TOKEN (opcional legacy)
#      YT_RT_GLOBALSUP | YOUTUBE_CLIENT_ID/SECRET | CLICKBANK_ID | AWIN_AFFID | AWIN_API_TOKEN | AMAZON_US_TAG
CHANNEL_NAME = "GLOBAL SUPPLEMENTS"
STATE_FILE = os.environ.get("STATE_FILE", os.path.join("data", "products_published.json"))
GEMINI_TEXT_MODEL = "gemini-2.5-flash"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
# Fundo premium — PRIMÁRIO agora é OpenAI gpt-image-1 (REST /v1/images/generations).
OPENAI_IMAGE_MODEL = "gpt-image-1"
# Modelo de imagem Gemini (fallback opcional, pago ~$0.039/img). O antigo gemini-2.0 flash image foi desligado.
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
# FLUX.1-schnell (grátis) via Hugging Face Inference API — apenas ÚLTIMO recurso legacy de fundo.
HF_FLUX_MODEL = "black-forest-labs/FLUX.1-schnell"
# Site REAL de reviews/afiliado do usuário — fonte dos produtos REAIS e imagens OFICIAIS.
PRODUCTS_LIST_URL = "https://globalsupplements.site/products/"
PRODUCT_BASE = "https://globalsupplements.site/"
TTS_VOICE = "Charon"  # voz MASCULINA (Gemini fallback)
TTS_RATE = 24000  # PCM 24kHz mono, 16-bit

YEAR = "2026"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ── sub-keywords do roteiro por nicho (usadas no script/tags) ─────────────────────────────────
NICHE_SUBKW = {
    "weight loss": ["weight", "metabolism", "appetite", "lean", "wellness"],
    "blood sugar": ["blood sugar", "glucose", "balance", "metabolic health", "diet"],
    "tinnitus": ["hearing", "ear health", "ringing relief", "wellness", "calm"],
    "prostate": ["prostate", "mens health", "vitality", "wellness", "energy"],
    "focus": ["focus", "brain health", "clarity", "cognition", "memory"],
    "sleep": ["sleep", "rest", "relaxation", "night routine", "calm"],
    "dental": ["dental health", "teeth", "gums", "oral care", "fresh breath"],
    "nail": ["nail health", "skin", "keratin", "beauty", "wellness"],
    "gut": ["gut health", "digestion", "skin", "probiotics", "wellness"],
}

# ── PRODUTOS REAIS do site do usuário (globalsupplements.site) ────────────────────────────────
# Lista de fallback (usada só se o scraping da /products/ falhar). Também guarda o
# display-name, o nicho (p/ paleta do fundo + roteiro) e o label da thumbnail por slug.
# slug -> (display_name, niche, thumb_label)
PRODUCT_META = {
    "prodentim":      ("ProDentim", "dental", "DENTAL\nHEALTH"),
    "java-burn":      ("Java Burn", "weight loss", "JAVA\nBURN"),
    "mitolyn":        ("Mitolyn", "weight loss", "MITOLYN"),
    "leanbiome":      ("LeanBiome", "weight loss", "LEAN\nBIOME"),
    "gluco6":         ("Gluco6", "blood sugar", "BLOOD\nSUGAR"),
    "teaburn":        ("Tea Burn", "weight loss", "TEA\nBURN"),
    "zencortex":      ("ZenCortex", "tinnitus", "EAR &\nHEARING"),
    "alpilean":       ("Alpilean", "weight loss", "ALPI-\nLEAN"),
    "exipure":        ("Exipure", "weight loss", "EXIPURE"),
    "fitspresso":     ("Fitspresso", "weight loss", "FIT-\nSPRESSO"),
    "endopump":       ("EndoPump", "prostate", "MALE\nVITALITY"),
    "okinawa":        ("Okinawa Flat Belly Tonic", "weight loss", "FLAT\nBELLY"),
    "ikariajuice":    ("Ikaria Lean Belly Juice", "weight loss", "LEAN\nBELLY"),
    "amiclear":       ("Amiclear", "blood sugar", "BLOOD\nSUGAR"),
    "citrusbburn":    ("Citrus Burn", "weight loss", "CITRUS\nBURN"),
    "pronailcomplex": ("ProNail Complex", "nail", "NAIL\nHEALTH"),
    "synaptigen":     ("Synaptigen", "focus", "BRAIN\nFOCUS"),
    "audifort":       ("Audifort", "tinnitus", "EAR &\nHEARING"),
    "yusleep":        ("YuSleep", "sleep", "SLEEP\nAID"),
    "nagano":         ("Nagano Tonic", "weight loss", "NAGANO\nTONIC"),
    "aquasculpt":     ("AquaSculpt", "weight loss", "AQUA\nSCULPT"),
    "primebiome":     ("PrimeBiome", "gut", "GUT &\nSKIN"),
    "prostive":       ("Prostive", "prostate", "PROSTATE\nHEALTH"),
    "sumatra":        ("Sumatra Slim Belly Tonic", "weight loss", "SLIM\nBELLY"),
}
FALLBACK_SLUGS = list(PRODUCT_META.keys())
# slugs que NUNCA são produtos (páginas institucionais / infra do WordPress)
NON_PRODUCT_SLUGS = {
    "products", "product", "blog", "about", "about-us", "contact", "privacy",
    "privacy-policy", "terms", "terms-of-service", "disclaimer", "disclosure",
    "category", "categories", "tag", "author", "feed", "sitemap", "wp-content",
    "wp-admin", "wp-json", "wp-includes", "cart", "checkout", "shop", "home",
    "index", "page", "search", "reviews", "review", "affiliate",
}

# ── SEO multilíngue (frases genéricas por idioma p/ alcance mundial) ──────────────────────────
LANGS = [
    ("EN", "{t}: an honest, no-hype overview to help you choose. Not medical advice."),
    ("ES", "{t}: una guia honesta y sin exageraciones para ayudarte a elegir. No es consejo medico."),
    ("PT", "{t}: um panorama honesto e sem exageros para ajudar voce a escolher. Nao e conselho medico."),
    ("FR", "{t} : un apercu honnete et sans battage pour vous aider a choisir. Ce n'est pas un avis medical."),
    ("DE", "{t}: ein ehrlicher Ueberblick ohne Hype, der bei der Auswahl hilft. Keine medizinische Beratung."),
    ("IT", "{t}: una panoramica onesta e senza esagerazioni per aiutarti a scegliere. Non e un consiglio medico."),
    ("JA", "{t}: 誇張のない正直な概要で選びやすく。医療アドバイスではありません。"),
    ("HI", "{t}: सही चुनाव में मदद के लिए एक ईमानदार जानकारी। यह चिकित्सा सलाह नहीं है।"),
    ("AR", "{t}: نظرة صادقة وبدون مبالغة لمساعدتك على الاختيار. ليست نصيحة طبية."),
]
KW_ML = ["supplements", "suplementos", "complementos", "complements", "nahrungsergaenzung",
         "integratori", "サプリメント", "健康", "vitamins", "wellness", "review", f"best {YEAR}",
         "how to choose", "buying guide"]

DISCLOSURE = ("Affiliate disclosure: some links are affiliate links and we may earn a commission at "
              "no extra cost to you. As an Amazon Associate we earn from qualifying purchases.")
SUBSCRIBE = "Subscribe for weekly honest supplement reviews and deals."
# CTA/loja: SEMPRE a página de PRODUTOS (a raiz globalsupplements.site NÃO tem produtos — NUNCA linkar a raiz).
SHOP_URL = "https://globalsupplements.site/products/"
ACCENT = (58, 190, 150)  # verde "supplement/health"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ESTADO — ofertas já publicadas (json simples, rotativo)
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
        print("aviso: nao consegui salvar estado:", str(e)[:80])


def _published_names(state):
    names = []
    for x in state.get("published", []):
        if isinstance(x, dict):
            names.append(str(x.get("name", "")).lower())
        else:
            names.append(str(x).lower())
    return names


def _published_slugs(state):
    """Slugs de produtos já publicados (rotação — não repetir)."""
    slugs = []
    for x in state.get("published", []):
        if isinstance(x, dict):
            s = x.get("slug")
            if s:
                slugs.append(str(s).lower())
    return slugs


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REDE / HTTP helpers (sempre com try/except; nunca quebram o run)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def http_get(url, timeout=25, binary=False):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        return data if binary else data.decode("utf-8", "replace")
    except Exception as e:
        print("aviso: GET falhou (" + url.split("//")[-1][:40] + "...):", str(e)[:60])
        return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1) FONTE DE PRODUTOS — produtos REAIS do site do usuário (globalsupplements.site/products/)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _slug(s):
    return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()


def scrape_product_slugs():
    """Raspa a página de PRODUTOS (globalsupplements.site/products/) para descobrir os slugs das
    páginas de review por produto (links https://globalsupplements.site/<slug>/).
    Se o fetch falhar ou não achar nada, cai para a lista fixa FALLBACK_SLUGS.
    Nunca lança — sempre retorna uma lista de slugs."""
    slugs = []
    page = http_get(PRODUCTS_LIST_URL, timeout=25)
    if page:
        try:
            # âncoras para /<slug>/ (absolutas ou relativas ao domínio). Um único segmento => slug.
            found = re.findall(
                r'href=["\'](?:https?://globalsupplements\.site)?/([a-z0-9][a-z0-9-]{1,50})/?["\']',
                page, re.I)
            for raw in found:
                s = raw.lower().strip("/")
                if not s or s in NON_PRODUCT_SLUGS or s in slugs:
                    continue
                slugs.append(s)
        except Exception as e:
            print("aviso: parse da lista de produtos falhou:", str(e)[:60])
    if slugs:
        print(f"[PRODUTOS] {len(slugs)} slugs raspados de {PRODUCTS_LIST_URL}")
        return slugs
    print("[PRODUTOS] scraping falhou/vazio — usando lista fixa de slugs (fallback)")
    return list(FALLBACK_SLUGS)


def _product_display(slug):
    """Nome/nicho/label do slug — a partir de PRODUCT_META, ou derivado do próprio slug."""
    if slug in PRODUCT_META:
        name, niche, label = PRODUCT_META[slug]
        return name, niche, label
    pretty = slug.replace("-", " ").title()
    label = (pretty[:12].upper() + "\nREVIEW")
    return pretty, "weight loss", label


def pick_product(state, exclude=None):
    """Escolhe o PRÓXIMO produto REAL não publicado (rotaciona; não repete slug).
    A CTA primária é SEMPRE a própria página de review (https://globalsupplements.site/<slug>/) —
    NUNCA a raiz do site. Retorna (slug, offer_dict).
    Campos do offer: name, slug, network, niche, label, buys, subkw, affiliate_url,
    official_page_url, vendor, query."""
    done = _published_slugs(state)
    exclude = set(x.lower() for x in (exclude or []))
    slugs = scrape_product_slugs()

    chosen = None
    for s in slugs:
        if s.lower() not in done and s.lower() not in exclude:
            chosen = s
            break
    if not chosen:
        # nao ha slug nao-publicado e nao-excluido disponivel neste ciclo
        for s in slugs:
            if s.lower() not in exclude:
                chosen = s
                break
    if not chosen:
        return None, None

    name, niche, label = _product_display(chosen)
    subkw = NICHE_SUBKW.get(niche, ["wellness", "health", "supplement", "review", "energy"])
    buys = [f"{name} supplement", f"{name} reviews", name]
    # CTA PRIMÁRIA = a própria página de review do produto (nunca a raiz do site)
    review_url = PRODUCT_BASE + chosen + "/"

    offer = {"name": name, "slug": chosen, "network": "Global Supplements", "niche": niche,
             "label": label, "buys": buys, "subkw": subkw, "vendor": None,
             "affiliate_url": review_url, "official_page_url": review_url,
             "retailer_url": None, "image_url": None, "query": buys[0]}
    print(f"[PRODUTOS] escolhido slug='{chosen}' | produto='{name}' | nicho={niche}")
    return chosen, offer


def amazon_search(q):
    tag = (os.environ.get("AMAZON_US_TAG") or "globalsup-20").strip()
    return f"https://www.amazon.com/s?k={urllib.parse.quote(q)}&tag={tag}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2) IMAGEM DO PRODUTO — real intacto + FUNDO gerado por IA + composição
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fetch_product_image_and_cta(slug, out_png):
    """Busca a página de REVIEW REAL do produto (https://globalsupplements.site/<slug>/) e extrai:
      • TITLE   — og:title / twitter:title / <h1>
      • IMAGE   — og:image (a imagem OFICIAL/REAL do produto) com fallback twitter:image / maior <img>
      • CTA     — a própria URL da página de review (NUNCA a raiz do site)
      • RETAILER— link externo "check price" (ClickBank hop / Amazon / retailer) se já presente
    Baixa a imagem REAL do produto INTACTA (pixels não são recriados) para out_png.
    Retorna dict {slug, cta_url, title, image_url, retailer_url, has_image}. Nunca lança."""
    cta_url = PRODUCT_BASE + slug + "/"
    out = {"slug": slug, "cta_url": cta_url, "title": None, "image_url": None,
           "retailer_url": None, "has_image": False}
    page = http_get(cta_url, timeout=25)
    if not page:
        print("[IMG] pagina de review inacessivel — seguindo sem imagem oficial")
        return out
    candidates = []
    try:
        # ── TITLE (produto real) ──────────────────────────────────────────────────────────────
        for pat in (r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)',
                    r'<h1[^>]*>(.*?)</h1>'):
            m = re.search(pat, page, re.I | re.S)
            if m:
                t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
                if t:
                    out["title"] = t[:120]
                    break
        # ── IMAGE (og:image = imagem OFICIAL REAL do produto) ─────────────────────────────────
        candidates = []
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page, re.I)
        if m:
            candidates.append(m.group(1))
        m2 = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', page, re.I)
        if m2:
            candidates.append(m2.group(1))
        for src in re.findall(r'<img[^>]+src=["\']([^"\']+\.(?:png|jpg|jpeg|webp))', page, re.I):
            if not re.search(r"(sprite|icon|logo|pixel|blank|spacer|avatar|gravatar)", src, re.I):
                candidates.append(src)
        if candidates:
            out["image_url"] = candidates[0] if candidates[0].startswith("http") \
                else urllib.parse.urljoin(cta_url, candidates[0])
        # ── RETAILER (link externo "check price" já presente — ClickBank/Amazon/BuyGoods etc.) ─
        for href in re.findall(r'href=["\']([^"\']+)["\']', page, re.I):
            if re.search(r"(hop\.clickbank\.net|amazon\.|amzn\.|buygoods\.com|digistore24|clkbank)",
                         href, re.I):
                out["retailer_url"] = href if href.startswith("http") \
                    else urllib.parse.urljoin(cta_url, href)
                break
    except Exception as e:
        print("aviso: parse da pagina de review falhou:", str(e)[:60])

    # ── download da imagem REAL, INTACTA (sem alterar pixels) ─────────────────────────────────
    for raw in candidates[:8]:
        img_url = raw if raw.startswith("http") else urllib.parse.urljoin(cta_url, raw)
        data = http_get(img_url, timeout=25, binary=True)
        if data and len(data) > 5000:
            try:
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(data)).convert("RGBA")
                if im.width >= 200 and im.height >= 200:
                    im.save(out_png, "PNG")  # produto REAL preservado, nítido, sem edição
                    out["image_url"] = img_url
                    out["has_image"] = True
                    print(f"[IMG] imagem OFICIAL REAL do produto baixada {im.width}x{im.height}")
                    return out
            except Exception:
                continue
    # FALLBACK REGRA-ZERO: se a review nao tem foto real, pega a imagem OFICIAL do proprio vendor
    # (segue o hoplink ClickBank ate a pagina de vendas do produto). Continua sendo foto REAL, nao IA.
    if not out["has_image"] and out.get("retailer_url"):
        try:
            vend = http_get(out["retailer_url"], timeout=25)
        except Exception:
            vend = None
        if vend:
            vc = []
            mv = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', vend, re.I)
            if mv:
                vc.append(mv.group(1))
            for src in re.findall(r'<img[^>]+src=["\']([^"\']+\.(?:png|jpg|jpeg|webp))', vend, re.I):
                if not re.search(r"(sprite|icon|logo|pixel|blank|spacer|badge|guarantee|payment|visa|master|paypal|seal|star)", src, re.I):
                    vc.append(src)
            for raw in vc[:10]:
                iu = raw if raw.startswith("http") else urllib.parse.urljoin(out["retailer_url"], raw)
                data = http_get(iu, timeout=25, binary=True)
                if data and len(data) > 8000:
                    try:
                        from PIL import Image
                        import io
                        im = Image.open(io.BytesIO(data)).convert("RGBA")
                        if im.width >= 300 and im.height >= 300:
                            im.save(out_png, "PNG")
                            out["image_url"] = iu
                            out["has_image"] = True
                            print(f"[IMG] imagem OFICIAL do VENDOR (fallback real) {im.width}x{im.height}")
                            return out
                    except Exception:
                        continue
    print("[IMG] sem imagem oficial utilizavel — seguira com fundo + branding")
    return out


def maybe_remove_bg(png_path):
    """Remove o fundo do produto com rembg SE importável. Nunca hard-depende de rembg.
    Retorna caminho da imagem (com ou sem fundo) — produto sempre intacto."""
    try:
        from rembg import remove  # opcional
        from PIL import Image
        import io
        with open(png_path, "rb") as f:
            cut = remove(f.read())
        out = png_path.replace(".png", "_cut.png")
        with open(out, "wb") as f:
            f.write(cut)
        Image.open(out).convert("RGBA")  # valida
        print("[IMG] rembg removeu fundo do produto")
        return out
    except Exception:
        # rembg ausente ou falhou -> usa a imagem como está (matte suave na composição)
        return png_path


def _bg_prompt(niche):
    """Monta o prompt do FUNDO (cena/ad) para o nicho — descreve APENAS o cenário, NUNCA o produto
    (o PNG do produto REAL é composto por cima depois). Paleta viral por nicho."""
    palette = {
        "sleep": "calming deep blue and soft violet tones",
        "focus": "cool electric blue and clean white tones",
        "energy": "vibrant warm amber and orange sunrise tones",
        "weight loss": "fresh green and bright airy tones",
        "blood sugar": "balanced teal and green tones",
        "prostate": "confident deep navy blue tones",
        "hair": "warm golden and soft brown tones",
        "vision": "clear cyan and crisp bright tones",
        "tinnitus": "soft calming aqua and blue tones",
        "dental": "fresh mint and clean bright white tones",
        "nail": "warm beige and soft rose tones",
        "gut": "fresh green and clean airy white tones",
    }.get((niche or "").lower(), "premium brand-color tones")
    return (
        f"A premium, cinematic, high-converting advertising BACKGROUND scene for a {niche} wellness "
        f"supplement ad, {palette}. Studio product-photography lighting, soft depth of field, "
        "luxurious clean surface with subtle glow and elegant bokeh, empty center-right space to "
        "place a product later. NO product, NO bottle, NO text, NO watermark, NO logos, NO people. "
        "16:9, ultra sharp, photorealistic, advertising quality."
    )


def gen_background_openai(niche, out_png):
    """PRIMÁRIO (PADRÃO): fundo premium via OpenAI gpt-image-1 (REST /v1/images/generations).
    Requer OPENAI_API_KEY; se vazio, PULA. model='gpt-image-1', size '1024x1024', quality 'high'.
    O prompt descreve APENAS um cenário/fundo de anúncio premium do nicho — SEM produto, SEM texto.
    Resposta traz b64_json -> PIL -> 1920x1080. Nunca lança; degrada graciosamente."""
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return False
    try:
        url = "https://api.openai.com/v1/images/generations"
        body = json.dumps({
            "model": OPENAI_IMAGE_MODEL,
            "prompt": _bg_prompt(niche),
            "size": "1024x1024",
            "quality": "high",
            "n": 1,
        }).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        data0 = (r.get("data") or [{}])[0]
        b64 = data0.get("b64_json")
        raw = None
        if b64:
            raw = base64.b64decode(b64)
        elif data0.get("url"):
            raw = http_get(data0["url"], timeout=60, binary=True)
        if raw:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(raw)).convert("RGB").resize((1920, 1080))
            im.save(out_png, "PNG")
            print("[IMG] fundo IA gerado via OpenAI " + OPENAI_IMAGE_MODEL + " (primario)")
            return True
    except urllib.error.HTTPError as e:
        print("aviso: OpenAI " + OPENAI_IMAGE_MODEL + " HTTP " + str(e.code) + " — fallback")
    except Exception as e:
        print("aviso: OpenAI " + OPENAI_IMAGE_MODEL + " falhou:", str(e)[:70])
    return False


def gen_background_flux(niche, out_png):
    """ÚLTIMO RECURSO LEGACY (GRÁTIS): FLUX.1-schnell via Hugging Face Inference API (free tier).
    Requer HF_TOKEN; se vazio, PULA. Trata 503 'model loading' (lê estimated_time e re-tenta
    até 2x). Resposta = bytes de imagem crua -> PIL -> upscale 1920x1080. Nunca lança."""
    hf_token = (os.environ.get("HF_TOKEN") or "").strip()
    if not hf_token:
        return False
    url = "https://router.huggingface.co/hf-inference/models/" + HF_FLUX_MODEL
    body = json.dumps({
        "inputs": _bg_prompt(niche),
        "parameters": {"width": 1024, "height": 1024},  # schnell ignora guidance; 4 steps default
    }).encode()
    for attempt in range(3):  # 1 tentativa + até 2 re-tentativas em 503 (model loading)
        try:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Authorization": "Bearer " + hf_token,
                         "Content-Type": "application/json", "Accept": "image/png"})
            resp = urllib.request.urlopen(req, timeout=120)
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "application/json" in ctype or (data[:1] == b"{"):
                # não veio imagem — provavelmente modelo carregando; lê estimated_time e re-tenta
                try:
                    info = json.loads(data.decode("utf-8", "replace"))
                    wait = float(info.get("estimated_time", 8) or 8)
                except Exception:
                    wait = 8.0
                print("aviso: FLUX (HF) carregando modelo — retry em %.0fs" % min(max(wait, 3), 30))
                time.sleep(min(max(wait, 3), 30))
                continue
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB").resize((1920, 1080))
            im.save(out_png, "PNG")
            print("[IMG] fundo IA gerado via FLUX.1-schnell (Hugging Face, free)")
            return True
        except urllib.error.HTTPError as e:
            body_txt = ""
            try:
                body_txt = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 503:  # model loading
                wait = 8.0
                try:
                    wait = float(json.loads(body_txt).get("estimated_time", 8) or 8)
                except Exception:
                    pass
                print("aviso: FLUX (HF) 503 model loading — retry em %.0fs" % min(max(wait, 3), 30))
                time.sleep(min(max(wait, 3), 30))
                continue
            print("aviso: FLUX (HF) HTTP " + str(e.code) + " — pulando")
            return False
        except Exception as e:
            print("aviso: FLUX (HF) falhou:", str(e)[:70])
            return False
    return False


def gen_background_gemini(niche, out_png):
    """SECUNDÁRIO (PAGO, opt-in): fundo via Gemini image (generateContent REST). Só roda se
    GEMINI_IMAGE=1 E GEMINI_API_KEY definido. Usa gemini-2.5-flash-image (~$0.039/img) — o antigo
    gemini-2.0 flash image foi desligado (NÃO usar). Nunca lança; cai para o fallback Pillow."""
    if (os.environ.get("GEMINI_IMAGE") or "").strip() != "1":
        return False
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return False
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_IMAGE_MODEL}:generateContent?key={key}")
        body = {"contents": [{"parts": [{"text": _bg_prompt(niche)}]}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=120).read())
        b64 = None
        for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            inline = p.get("inlineData") or p.get("inline_data")
            if inline and inline.get("data"):
                b64 = inline["data"]
                break
        if b64:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB").resize((1920, 1080))
            im.save(out_png, "PNG")
            print("[IMG] fundo IA gerado via " + GEMINI_IMAGE_MODEL + " (pago)")
            return True
    except Exception as e:
        print("aviso: fundo Gemini (" + GEMINI_IMAGE_MODEL + ") falhou:", str(e)[:70])
    return False


def gen_background_pollinations(niche, out_png, W=1920, H=1080):
    """Fundo VIRAL foto-real e COERENTE com o produto via Pollinations (GRATIS, sem chave).
    Escolhe cena por palavra-chave do nicho (dental, weight loss, prostate...). Cadeia de
    modelos vivos 2026: gptimage -> flux -> turbo. enhance melhora; nologo remove marca."""
    import urllib.parse, random
    nl = (niche or "").lower()
    SCENES = [
        (("sleep", "insomnia", "rest", "noise"),
         "dreamy calm bedroom at night, soft moonlight through window, deep blue and violet bokeh, cozy pillows, peaceful"),
        (("dental", "teeth", "tooth", "oral", "gum"),
         "clean bright modern bathroom, fresh mint leaves and water splash, sparkling white and mint tones, fresh clean"),
        (("weight", "fat", "slim", "metabolism", "burn"),
         "fresh bright kitchen with green vegetables fruit and measuring tape, morning sunlight, healthy vibrant airy"),
        (("energy", "fatigue", "vitality", "mitochond"),
         "warm sunrise light rays, dynamic energetic morning, vibrant amber and gold, active healthy glow"),
        (("focus", "brain", "memory", "cognit", "clarity"),
         "futuristic glowing neural network, blue energy particles, mental clarity, premium clean tech mood"),
        (("blood sugar", "glucose", "diabet", "sugar"),
         "clean medical wellness lab, balanced teal and green energy flow, healthy circulation, professional premium"),
        (("blood pressure", "heart", "circul", "cardio"),
         "clean medical premium scene, soft red and crimson heart-health energy, professional wellness"),
        (("prostate", "men", "male", "testo"),
         "confident deep navy blue premium background, calm masculine clean studio, strong subtle glow"),
        (("tinnitus", "hearing", "ear"),
         "soft calming aqua and blue sound waves, quiet serene spa mood, gentle ripples"),
        (("nail", "fungus", "skin", "hair", "beauty"),
         "luxury spa marble with orchids and water droplets, soft rose gold light, elegant clean skincare mood"),
        (("gut", "digest", "probiotic", "bloat"),
         "fresh clean airy kitchen, green leaves and clear water, light white and green, healthy digestive vibe"),
        (("joint", "pain", "mobility", "bone"),
         "clean bright wellness studio, warm supportive light, active healthy lifestyle, soft premium"),
        (("money", "income", "wealth", "affiliate"),
         "luxury desk with laptop and coins, golden success light, entrepreneurial premium bokeh"),
    ]
    scene = "cinematic premium studio, luxury advertising background, soft golden light, elegant bokeh, 8k"
    for keys, sc in SCENES:
        if any(k in nl for k in keys):
            scene = sc; break
    prompt = urllib.parse.quote(scene + ", advertising background plate, generous empty center space, "
                                "no product, no bottle, no text, no words, no watermark, no people")
    seed = random.randint(1, 999999)
    for model in ("gptimage", "flux", "turbo"):
        url = ("https://image.pollinations.ai/prompt/%s?width=%d&height=%d&model=%s"
               "&nologo=true&enhance=true&seed=%d") % (prompt, W, H, model, seed)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aether"})
            data = urllib.request.urlopen(req, timeout=120).read()
            if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
                with open(out_png, "wb") as f:
                    f.write(data)
                print("[BG] fundo COERENTE Pollinations (%s | %s) %dx%d" % (model, nl or "generic", W, H))
                return True
        except Exception as e:
            print("aviso: Pollinations %s falhou: %s" % (model, str(e)[:60]))
    return False


def gen_background_ai(niche, out_png):
    """Gera SOMENTE o FUNDO 1920x1080 (nunca o produto). Cadeia, cada etapa em try/except:
      1) OpenAI gpt-image-1 (PADRÃO/PRIMÁRIO — requer OPENAI_API_KEY)
      2) Gemini image (fallback pago, opt-in via GEMINI_IMAGE=1 + GEMINI_API_KEY)
      3) FLUX.1-schnell (Hugging Face — último recurso legacy, requer HF_TOKEN)
    Retorna True se salvou um PNG. O fallback GARANTIDO (Pillow premium_gradient_bg) fica no main —
    o produto REAL nunca é tocado; ele é composto por cima do fundo depois."""
    if gen_background_openai(niche, out_png):
        return True
    if gen_background_pollinations(niche, out_png):
        return True
    if gen_background_flux(niche, out_png):
        return True
    if gen_background_gemini(niche, out_png):
        return True
    return False


def premium_gradient_bg(niche, out_png):
    """Fallback: fundo premium (navy escuro + glow de acento) via Pillow. 1920x1080."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return False
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (8, 12, 20))
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(8 + 18 * t), int(12 + 26 * t), int(20 + 34 * t)))
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - 820, H // 2 - 500, W // 2 + 820, H // 2 + 500], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    tint = Image.new("RGB", (W, H), ACCENT)
    img = Image.composite(tint, img, glow.point(lambda x: int(x * 0.42)))
    img.save(out_png, "PNG")
    print("[IMG] fundo premium (Pillow fallback) gerado")
    return True


def maybe_add_human_avatar(img):
    """TODO (hook): avatar humano fotorrealista apresentando o produto. Por ora retorna inalterado.
    Quando implementado, deve compor um apresentador realista SEM alterar os pixels do produto."""
    return img


def composite_key_frame(bg_png, product_png, out_png, has_product):
    """Compoe o PRODUTO REAL (grande, centro/direita) sobre o FUNDO. Pixels do produto intactos.
    Adiciona sombra suave. Retorna True se salvou. Se sem produto, apenas usa o fundo."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return False
    try:
        bg = Image.open(bg_png).convert("RGBA").resize((1920, 1080))
    except Exception:
        return False
    if has_product and product_png and os.path.exists(product_png):
        try:
            prod = Image.open(product_png).convert("RGBA")
            # produto GRANDE: ~72% da altura do frame
            target_h = int(1080 * 0.72)
            ratio = target_h / prod.height
            prod = prod.resize((max(1, int(prod.width * ratio)), target_h))
            # posição centro/direita
            px = int(1920 * 0.56) - prod.width // 2
            py = (1080 - prod.height) // 2
            px = max(40, min(px, 1920 - prod.width - 40))
            # sombra suave (drop shadow)
            shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            alpha = prod.split()[-1]
            sh = Image.new("RGBA", prod.size, (0, 0, 0, 150))
            sh.putalpha(alpha)
            shadow.paste(sh, (px + 18, py + 26), sh)
            shadow = shadow.filter(ImageFilter.GaussianBlur(28))
            bg = Image.alpha_composite(bg, shadow)
            bg.paste(prod, (px, py), prod)
        except Exception as e:
            print("aviso: composicao do produto falhou:", str(e)[:60])
    bg = maybe_add_human_avatar(bg)
    bg.convert("RGB").save(out_png, "PNG")
    return True


# ── PILLOW helpers de texto (mantidos do v1) ─────────────────────────────────────────────────
def _font(size, bold=True):
    from PIL import ImageFont
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


VW, VH = 1080, 1920  # VERTICAL 9:16 mobile (celular em pe) para YT Shorts/Reels/TikTok/FB


def overlay_title_vertical(bg_png, title, out_png):
    """Titulo CURTO e PEQUENO no TOPO (caixa escura, alto contraste) para video VERTICAL mobile."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return bg_png
    try:
        img = Image.open(bg_png).convert("RGBA")
    except Exception:
        return bg_png
    W, H = img.size
    d = ImageDraw.Draw(img, "RGBA")
    short = re.split(r"[:\-\u2014\(\[]", title)[0].strip()
    parts = short.split()
    if len(parts) > 5:
        short = " ".join(parts[:5])
    # canal pequeno no topo
    fch = _font(36, bold=True)
    d.text((40, 40), CHANNEL_NAME, font=fch, fill=(230, 248, 238))
    # titulo pequeno, no maximo 2 linhas, caixa escura
    fs = 54
    ft = _font(fs, bold=True)
    lines = _wrap(d, short, ft, int(W * 0.84))
    while len(lines) > 2 and fs > 34:
        fs -= 6
        ft = _font(fs, bold=True)
        lines = _wrap(d, short, ft, int(W * 0.84))
    lh = int(fs * 1.16)
    th = len(lines) * lh
    y0 = 96
    d.rectangle([22, y0 - 12, W - 22, y0 + th + 12], fill=(6, 12, 10, 150))
    y = y0
    for ln in lines:
        try:
            wln = d.textlength(ln, font=ft)
        except Exception:
            wln = W * 0.6
        x = int((W - wln) / 2)
        d.text((x + 3, y + 3), ln, font=ft, fill=(0, 0, 0))
        d.text((x, y), ln, font=ft, fill=(246, 252, 248))
        y += lh
    fsd = _font(28, bold=False)
    d.text((40, H - 66), "Honest overview - Not medical advice", font=fsd, fill=(206, 226, 218))
    img.convert("RGB").save(out_png, "PNG")
    return out_png


def make_video_vertical(bg_path, audio_path, out_path, duration, W=VW, H=VH):
    """Ken Burns VERTICAL 1080x1920 (fallback quando o dinamico falha)."""
    secs = max(int(round(duration)), 5)
    frames = secs * 30
    vf = ("scale=%d:%d,zoompan=z='min(zoom+0.00035,1.12)':d=%d:"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=30,format=yuv420p"
          % (int(W * 1.2), int(H * 1.2), frames, W, H))
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", bg_path, "-i", audio_path, "-t", str(secs),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-vf", vf,
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-shortest", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def composite_vertical(bg_png, product_png, out_png):
    """Compoe produto REAL centralizado sobre fundo vertical (fallback estatico)."""
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        bg = Image.open(bg_png).convert("RGBA").resize((VW, VH))
    except Exception:
        return False
    if product_png and os.path.exists(product_png):
        try:
            p = Image.open(product_png).convert("RGBA")
            th = int(VH * 0.50); r = th / p.height; nw = int(p.width * r)
            if nw > int(VW * 0.9):
                nw = int(VW * 0.9); r = nw / p.width; th = int(p.height * r)
            p = p.resize((nw, th))
            bg.alpha_composite(p, ((VW - nw) // 2, int(VH * 0.32)))
        except Exception:
            pass
    bg.convert("RGB").save(out_png, "PNG")
    return True


def overlay_title(key_png, title, out_png):
    """Nome do canal + titulo CURTO grande sobre PAINEL ESCURO a esquerda (alto contraste, nunca
    encosta no produto que fica a direita). Texto branco com sombra. Cabe sempre (fonte dinamica)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return key_png
    try:
        img = Image.open(key_png).convert("RGBA")
    except Exception:
        return key_png
    W, H = img.size
    # painel escuro translucido a esquerda -> garante leitura em qualquer fundo
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pw = int(W * 0.52)
    pd.rectangle([0, 0, pw, H], fill=(6, 12, 10, 150))
    img = Image.alpha_composite(img, panel)
    d = ImageDraw.Draw(img)
    # cabecalho canal
    fch = _font(46, bold=True)
    d.text((70, 66), CHANNEL_NAME, font=fch, fill=(214, 246, 230))
    try:
        cw = d.textlength(CHANNEL_NAME, font=fch)
    except Exception:
        cw = 420
    d.rectangle([70, 122, 70 + cw, 130], fill=ACCENT)
    # titulo curto (so nome + Review), sem titulo SEO gigante
    short = re.split(r"[:\-\u2014\(\[]", title)[0].strip()
    parts = short.split()
    if len(parts) > 5:
        short = " ".join(parts[:5])
    title = short
    ftsize = 88
    ft = _font(ftsize, bold=True)
    lines = _wrap(d, title, ft, int(W * 0.44))
    while len(lines) > 3 and ftsize > 50:
        ftsize -= 8
        ft = _font(ftsize, bold=True)
        lines = _wrap(d, title, ft, int(W * 0.44))
    lh = int(ftsize * 1.18)
    y = (H - len(lines) * lh) // 2 - 6
    for ln in lines:
        d.text((72, y + 4), ln, font=ft, fill=(0, 0, 0))
        d.text((68, y), ln, font=ft, fill=(246, 252, 248))
        y += lh
    fs = _font(34, bold=False)
    d.text((70, H - 74), "Honest overview - Not medical advice", font=fs, fill=(200, 222, 214))
    img.convert("RGB").save(out_png, "PNG")
    return out_png


def make_thumb(label, product_png, has_product, path):
    """Thumbnail 1280x720: produto real grande (se houver) + texto alto-contraste + badge."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        return False
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (8, 12, 16))
    d = ImageDraw.Draw(img)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(8 + ACCENT[0] * 0.05 * t), int(12 + ACCENT[1] * 0.08 * t),
                     int(16 + ACCENT[2] * 0.06 * t)))
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - 520, H // 2 - 340, W // 2 + 520, H // 2 + 340], fill=95)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    tint = Image.new("RGB", (W, H), ACCENT)
    img = Image.composite(tint, img, glow.point(lambda x: int(x * 0.45)))
    img = img.convert("RGBA")

    # produto real grande à direita
    if has_product and product_png and os.path.exists(product_png):
        try:
            prod = Image.open(product_png).convert("RGBA")
            th = int(H * 0.86)
            ratio = th / prod.height
            prod = prod.resize((max(1, int(prod.width * ratio)), th))
            px = W - prod.width - 40
            py = (H - prod.height) // 2
            shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            sh = Image.new("RGBA", prod.size, (0, 0, 0, 160))
            sh.putalpha(prod.split()[-1])
            shadow.paste(sh, (px + 14, py + 20), sh)
            shadow = shadow.filter(ImageFilter.GaussianBlur(22))
            img = Image.alpha_composite(img, shadow)
            img.paste(prod, (px, py), prod)
        except Exception as e:
            print("aviso: produto no thumb falhou:", str(e)[:50])

    d = ImageDraw.Draw(img)
    fch = _font(40, bold=True)
    d.text((48, 40), CHANNEL_NAME, font=fch, fill=(200, 240, 224))
    fb = _font(126, bold=True)
    lines = label.split("\n")[:3]
    lh = 132
    y = (H - len(lines) * lh) // 2 + 4
    for ln in lines:
        w = d.textlength(ln, font=fb)
        d.text((60 + 4, y + 4), ln, font=fb, fill=(0, 0, 0))
        d.text((60, y), ln, font=fb, fill=(245, 250, 247))
        y += lh
    sub = f"HONEST REVIEW - {YEAR}"
    fs = _font(42, bold=True)
    w = d.textlength(sub, font=fs)
    d.rectangle([56, y + 6, 56 + w + 44, y + 72], fill=ACCENT)
    d.text((78, y + 12), sub, font=fs, fill=(8, 16, 12))
    img.convert("RGB").save(path, "PNG")
    return True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# GEMINI — roteiro (texto) via REST, com fallback de template (INALTERADO do v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def strategy_snippets(query, maxn=6):
    """Le ideas_mined.jsonl (estrategia minerada das transcricoes COMPLETAS dos 591 canais) e
    devolve taticas/ganchos VIRAIS provados, priorizando os que casam com a consulta. Decisoes
    de roteiro passam a ser guiadas pelos dados minerados (nao generico). Nunca lanca."""
    try:
        import glob, random
        p = "ideas_mined.jsonl"
        if not os.path.exists(p):
            return ""
        q = (query or "").lower()
        qwords = [w for w in q.replace(",", " ").split() if len(w) > 3]
        tactics, ideas_hit, ideas_any = [], [], []
        for line in open(p, encoding="utf-8", errors="ignore"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            for t in (r.get("taticas") or []):
                if t: tactics.append(str(t))
            for it in (r.get("ideias") or []):
                s = str(it)
                if any(w in s.lower() for w in qwords):
                    ideas_hit.append(s)
                else:
                    ideas_any.append(s)
        random.shuffle(tactics); random.shuffle(ideas_any)
        picks = ideas_hit[:maxn // 2] + tactics[:maxn // 2] + ideas_any
        seen = set(); out = []
        for x in picks:
            k = x[:80]
            if k in seen:
                continue
            seen.add(k); out.append(x[:160])
            if len(out) >= maxn:
                break
        return " | ".join(out)
    except Exception:
        return ""


def magnetic_hook(name, niche=""):
    """Gancho magnetico (PDF POV: choque de preco/descoberta/provocativo/urgencia) adaptado ao produto."""
    try:
        import random
        h = json.load(open("magnetic_hooks.json", encoding="utf-8"))
        pool = []
        for cat in ["discovery", "provocative", "urgency", "price_shock", "pov"]:
            pool += h.get(cat, [])
        s = random.choice([x for x in pool if x]) if pool else ""
        core = name.split("\u2014")[0].split(" - ")[0].split("Review")[0].strip() or name
        return s.replace("{name}", core).replace("{price}", "a fraction of what you'd expect")
    except Exception:
        return ""


def gen_script(topic, subkw):
    key = os.environ.get("GEMINI_API_KEY")
    prompt = (
        "You are writing a short YouTube voiceover script in ENGLISH about the supplement topic: "
        f"\"{topic}\". Keep it 130-190 words (about 60-90 seconds spoken). "
        "Be informative, honest and balanced. Explain what it is, what people commonly use it for, "
        "what to look for when choosing, and a realistic expectation. "
        "IMPORTANT: no medical claims, no promises to cure/treat/prevent anything, no dosages as advice. "
        "Add a brief natural reminder that this is general info, not medical advice, and to consult a professional. "
        f"PROVEN viral hooks/angles mined from top creators (ADAPT, never copy): {strategy_snippets(topic + ' ' + ' '.join(subkw))}. "
        "Open with a scroll-stopping first line. "
        "Write ONLY the spoken words — no headings, no stage directions, no markdown, no emojis. "
        f"Naturally touch on: {', '.join(subkw)}."
    )
    try:
        import ai_providers
        txt = (ai_providers.ask(prompt, max_tokens=512) or "").strip()
        if len(txt) > 60:
            return txt
    except Exception as e:
        print("aviso: IA texto falhou, usando template:", str(e)[:80])
    return (
        f"Today we're taking an honest look at {topic}. "
        f"This is a popular option that many people add to their daily routine, and it often comes up "
        f"in conversations about {subkw[0]} and {subkw[1] if len(subkw) > 1 else 'general wellness'}. "
        "When you're comparing products, it helps to check the form and quality, the amount per serving, "
        "third-party testing, and clean ingredients without unnecessary fillers. "
        "Reviews and transparent labels can tell you a lot before you buy. "
        "Remember that supplements work best alongside good sleep, balanced nutrition, and regular movement, "
        "and results vary from person to person. "
        "This video is general information only, not medical advice, so please talk to a qualified "
        "healthcare professional before starting anything new. "
        "If this helped, check the links below for well-reviewed options, and thanks for watching."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# GEMINI TTS: PCM 24k mono -> WAV (REST); fallback silêncio (INALTERADO do v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pcm_to_wav(pcm_bytes, path, rate=TTS_RATE):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


def edge_tts_voice(script, path):
    """Voz MASCULINA neural via Edge TTS (Microsoft) — GRATIS, sem chave, sem cota, alta qualidade.
    Salva mp3 e converte p/ WAV mono no TTS_RATE. Nunca lanca."""
    try:
        import edge_tts, asyncio
        voice = os.environ.get("TTS_MALE_VOICE", "en-US-AndrewNeural")  # masculina, natural
        mp3 = path + ".mp3"
        async def _run():
            com = edge_tts.Communicate(script, voice, rate="+6%")
            await com.save(mp3)
        asyncio.run(_run())
        if os.path.exists(mp3) and os.path.getsize(mp3) > 2000:
            subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(TTS_RATE), "-ac", "1",
                            "-c:a", "pcm_s16le", path], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[TTS] voz MASCULINA neural (Edge TTS %s)" % voice)
            return True
    except Exception as e:
        print("aviso: Edge TTS falhou, tentando Gemini:", str(e)[:80])
    return False


def gen_voice(script, path):
    # PRIMARIO: Edge TTS masculino (gratis, sem cota)
    if edge_tts_voice(script, path):
        return True
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{GEMINI_TTS_MODEL}:generateContent?key={key}")
            body = {
                "contents": [{"parts": [{"text": script}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}
                    },
                },
            }
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            r = json.loads(urllib.request.urlopen(req, timeout=180).read())
            parts = r.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            for p in parts:
                inline = p.get("inlineData") or p.get("inline_data")
                if inline and inline.get("data"):
                    pcm = base64.b64decode(inline["data"])
                    rate = TTS_RATE
                    mt = inline.get("mimeType") or inline.get("mime_type") or ""
                    if "rate=" in mt:
                        try:
                            rate = int(mt.split("rate=")[1].split(";")[0])
                        except Exception:
                            rate = TTS_RATE
                    _pcm_to_wav(pcm, path, rate)
                    return True
            print("aviso: TTS sem audio na resposta — usando fallback silencio")
        except Exception as e:
            print("aviso: Gemini TTS falhou, usando fallback silencio:", str(e)[:80])
    secs = max(30, min(90, int(len(script.split()) / 2.6)))
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=r={TTS_RATE}:cl=mono", "-t", str(secs),
                        "-c:a", "pcm_s16le", path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print("erro: fallback de silencio falhou:", str(e)[:80])
        return False


def wav_duration(path):
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate() or TTS_RATE)
    except Exception:
        return 60.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# FFMPEG: imagem estática (loop) + locução -> mp4 1080p (INALTERADO do v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def make_video_dynamic(bg_path, product_path, audio_path, out_path, duration, W=1920, H=1080):
    """Fundo VIRAL em movimento (Ken Burns) + PRODUTO com movimento proprio (flutua/pulsa) por cima.
    Nao e so voz sobre imagem parada: o produto ganha vida sobre a cena. Cai para make_video se falhar."""
    secs = max(int(round(duration)), 5)
    frames = secs * 30
    up_w, up_h = int(W * 1.25), int(H * 1.25)
    ph = int(H * 0.60)                 # altura do produto
    amp = max(8, int(H * 0.035))       # amplitude do flutuar (px)
    per = 3.2                          # periodo do flutuar (s)
    fc = (
        "[0:v]scale=%d:%d,zoompan=z='min(zoom+0.00035,1.13)':d=%d:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=30,format=yuv420p[bg];"
        "[1:v]scale=-1:%d,format=rgba,"
        "scale='iw*(1+0.03*sin(2*PI*t/2.6))':'ih*(1+0.03*sin(2*PI*t/2.6))':eval=frame[pp];"
        "[bg][pp]overlay=x='(W-w)*0.60':y='(H-h)/2+%d*sin(2*PI*t/%s)':eval=frame:shortest=1,"
        "format=yuv420p[v]" % (up_w, up_h, frames, W, H, ph, amp, per)
    )
    cmd = ["ffmpeg", "-y",
           "-loop", "1", "-i", bg_path,
           "-loop", "1", "-i", product_path,
           "-i", audio_path,
           "-t", str(secs),
           "-filter_complex", fc, "-map", "[v]", "-map", "2:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-shortest", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_video(bg_path, audio_path, out_path, duration):
    """Monta o mp4 1080p com MOVIMENTO Ken Burns (zoom/pan lento) via ffmpeg zoompan — o key visual
    (fundo + produto REAL composto) ganha um zoom suave em vez de ficar estático. Limpo, sem tremor.
    Faz upsample para 2304x1296 antes do zoompan p/ evitar jitter, depois corta para 1920x1080."""
    secs = max(int(round(duration)), 5)
    frames = secs * 30
    # zoom lento até ~1.12x ao longo de todo o vídeo, centralizado (pan sutil pelo próprio zoom).
    vf = (
        "scale=2304:1296,"
        "zoompan=z='min(zoom+0.00035,1.12)':d=%d:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,"
        "format=yuv420p" % frames
    )
    cmd = ["ffmpeg", "-y",
           "-loop", "1", "-i", bg_path,
           "-i", audio_path,
           "-t", str(secs),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
           "-vf", vf,
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-shortest", "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3) VIRAL — título, descrição SEO multilíngue + afiliado + disclosure + CTA, tags
# ══════════════════════════════════════════════════════════════════════════════════════════════
def viral_title(name):
    """Título viral, keyword-first (nome REAL do produto primeiro) + curiosidade + ano."""
    label = (name or "This").strip()
    cand = f"{label} Review {YEAR}: Does It Really Work? (Honest)"
    if len(cand) >= 60:
        cand = f"{label}: The Honest Truth ({YEAR} Review)"
    if len(cand) >= 60:
        cand = f"{label} Review {YEAR} (Watch Before You Buy)"
    if len(cand) >= 60:
        cand = f"{label} — Honest {YEAR} Review"
    return cand[:59]


def description(topic, offer):
    parts = [t[1].format(t=topic) for t in LANGS]
    # CTA PRIMÁRIA = a página de review REAL do produto (nunca a raiz do site)
    aff = offer["affiliate_url"]
    block = ["", "⭐ FULL REVIEW & BEST PRICE:", f"→ {aff}"]
    # link do varejista (ClickBank/Amazon) SÓ se já estava presente na página de review
    if offer.get("retailer_url"):
        block += ["", "Check current price:", "→ " + offer["retailer_url"]]
    # opções extras Amazon (links de busca — ajudam SEO/CTR)
    block += ["", "More options:"]
    block += [f"→ {q.title()}: {amazon_search(q)}" for q in offer.get("buys", [])[:3]]
    # Loja da marca — SEMPRE a página de produtos (nunca a raiz, que não vende nada)
    block += ["", "🛒 Shop all our picks: " + SHOP_URL]
    block += ["", "🔔 " + SUBSCRIBE, "https://www.youtube.com/@Globalsuplements?sub_confirmation=1"]
    block += ["", DISCLOSURE, ""]
    allt = [topic.replace(",", ""), offer["niche"]] + KW_ML
    block.append(" ".join("#" + re.sub(r"[^A-Za-z0-9]", "", t) for t in allt[:14] if re.sub(r"[^A-Za-z0-9]", "", t)))
    desc = "\n\n".join(parts) + "\n" + "\n".join(block)
    return desc.replace("<", "").replace(">", "")[:4990]


def build_tags(topic, subkw, niche):
    base = [topic, niche, niche + " supplement"] + subkw + KW_ML + \
           ["supplements", "supplement review", "wellness", "health tips", f"best {YEAR}"]
    merged, used = [], 0
    for t in base:
        if not t:
            continue
        tl = t.lower()
        if tl in [x.lower() for x in merged]:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if used + cost > 450:
            continue
        merged.append(t)
        used += cost
    return merged


# ══════════════════════════════════════════════════════════════════════════════════════════════
# OAuth + UPLOAD resumable (INALTERADO do v1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _client():
    cid = os.environ.get("YOUTUBE_CLIENT_ID") or os.environ.get("YT_CLIENT_ID")
    cs = os.environ.get("YOUTUBE_CLIENT_SECRET") or os.environ.get("YT_CLIENT_SECRET")
    return cid, cs


def token(rt):
    cid, cs = _client()
    d = urllib.parse.urlencode({"client_id": cid, "client_secret": cs,
                                "refresh_token": rt, "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen(
        "https://oauth2.googleapis.com/token", data=d, timeout=25).read())["access_token"]


AI_DISCLOSURE = ("Disclosure: original honest review by Global Supplements. Uses AI-assisted "
                 "voice, visuals and script; product footage is the real product. Not medical advice.")
MUSIC_ATTR = ("Music: Kevin MacLeod (incompetech.com) - Licensed under Creative Commons: "
              "By Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/)")


def pick_music(niche):
    """Escolhe a trilha por MOOD do produto/video: energetico (weight/energy/money),
    foco (brain), calmo (sleep/tinnitus) ou quente/uplifting (dental/blood/prostate/nail/gut/beauty)."""
    import glob, random
    files = sorted(glob.glob(os.path.join("assets", "music", "*.mp3")))
    if not files:
        return None
    nl = (niche or "").lower()
    def has(*ks):
        return any(k in nl for k in ks)
    if has("weight", "fat", "slim", "burn", "metabol", "energy", "fatigue", "vitality",
           "mitochond", "money", "income", "affiliate", "coffee"):
        mood = ("ener_", "up_")
    elif has("brain", "memory", "focus", "cognit", "clarity", "nootrop", "hearing", "tinnitus-focus"):
        mood = ("focus_",)
    elif has("sleep", "insomnia", "noise", "tinnitus", "relax", "rest", "stress", "anxiet", "calm"):
        mood = ("calm_",)
    else:
        mood = ("calm_", "warm_")  # dental/blood/prostate/nail/skin/gut/joint/beauty -> calmo/uplifting
    pool = [f for f in files if any(os.path.basename(f).startswith(p) for p in mood)]
    return random.choice(pool or files)


def mix_bg_music(video_path, niche, vol=0.11):
    """Mistura musica de fundo CC-BY (loop, volume baixo) sob a locucao. Mantem o video (copy).
    Voz continua dominante (normalize=0). Se falhar, retorna o video original."""
    m = pick_music(niche)
    if not m:
        return video_path
    out = video_path.rsplit(".", 1)[0] + "_mus.mp4"
    fc = ("[0:a]volume=1.0[v0];[1:a]volume=%.3f[bg];"
          "[v0][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]" % vol)
    cmd = ["ffmpeg", "-y", "-i", video_path, "-stream_loop", "-1", "-i", m,
           "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-shortest", out]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[MUSIC] fundo: %s vol=%.2f (CC-BY Kevin MacLeod)" % (os.path.basename(m), vol))
        return out
    except Exception as e:
        print("aviso: mix de musica falhou:", str(e)[:70])
        return video_path


def api_upload(at, meta, path):
    body = json.dumps(meta).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=body, method="POST",
        headers={"Authorization": "Bearer " + at, "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4"})
    try:
        loc = urllib.request.urlopen(req, timeout=30).headers.get("Location")
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", "replace")
        if "exceeded the number of videos" in body_txt or "uploadLimitExceeded" in body_txt:
            print("[YT] LIMITE DIARIO de uploads atingido — pulando upload por hoje (mp4 pronto p/ TikTok/Reels). "
                  "Verifique o canal por telefone p/ aumentar o limite. Saindo limpo (exit 0).")
            raise SystemExit(0)
        raise SystemExit("UPLOAD INIT %s: %s" % (e.code, body_txt[:300]))
    data = open(path, "rb").read()
    put = urllib.request.Request(loc, data=data, method="PUT",
                                 headers={"Content-Type": "video/mp4", "Content-Length": str(len(data))})
    try:
        return json.loads(urllib.request.urlopen(put, timeout=1200).read())
    except urllib.error.HTTPError as e:
        raise SystemExit("UPLOAD erro: " + e.read().decode()[:300])


def set_thumb(at, vid, path):
    try:
        img = open(path, "rb").read()
        req = urllib.request.Request(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}&uploadType=media",
            data=img, method="POST",
            headers={"Authorization": "Bearer " + at, "Content-Type": "image/png"})
        urllib.request.urlopen(req, timeout=60)
        return "thumb OK"
    except urllib.error.HTTPError as e:
        return f"thumb pulado ({e.code} — canal talvez nao verificado p/ thumb custom)"
    except Exception as e:
        return f"thumb erro {str(e)[:40]}"


def _tmp(name):
    base = os.environ.get("RUNNER_TEMP") or ("/tmp" if os.path.isdir("/tmp") else ".")
    return os.path.join(base, name)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main():
    rt = os.environ.get("YT_RT_GLOBALSUP", "").strip()
    _dry = os.environ.get("PRODUCTS_DRY_RUN", "") == "1"
    if not rt and not _dry:
        print("YT_RT_GLOBALSUP ausente/vazio — nada a publicar. Saindo graciosamente (exit 0).")
        return
    cid, cs = _client()
    if (not cid or not cs) and not _dry:
        print("YOUTUBE_CLIENT_ID/SECRET ausentes — nao e possivel autenticar. Saindo (exit 0).")
        return

    state = load_state()

    # 1)+2) REGRA ZERO: so publica produto REAL com FOTO HD REAL na pagina de review.
    prod_png = _tmp("gs_product.png")
    slug = offer = info = None
    has_product = False
    noimg = []
    for _ in range(30):
        s, o = pick_product(state, exclude=noimg)
        if not s:
            break
        i = fetch_product_image_and_cta(s, prod_png)
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
    # CTA primária SEMPRE a página de review (garante mesmo que meta og:url divergisse)
    offer["affiliate_url"] = info["cta_url"]
    offer["official_page_url"] = info["cta_url"]

    topic = offer["name"]  # tópico REAL do produto (usado no roteiro/descrição/overlay)
    print(f"[GLOBALSUP] produto REAL: {offer['name']} | slug={slug} | nicho={offer['niche']} "
          f"| CTA={offer['affiliate_url']} | imagem_oficial={'sim' if has_product else 'nao'}")

    # roteiro + locução (Gemini — inalterado)
    script = gen_script(topic, offer["subkw"])
    print(f"[GLOBALSUP] roteiro: {len(script.split())} palavras")
    apath = _tmp("gs_voice.wav")
    if not gen_voice(script, apath):
        raise SystemExit("erro: nao foi possivel gerar locucao nem silencio de fallback")
    dur = wav_duration(apath)
    print(f"[GLOBALSUP] locucao: {dur:.1f}s")

    # produto real intacto -> opcional matte -> fundo IA (OpenAI primário) -> composição
    if has_product:
        prod_png = maybe_remove_bg(prod_png)

    bg_png = _tmp("gs_bg.png")
    bg_ai = False
    if gen_background_pollinations(offer["niche"], bg_png, W=VW, H=VH):
        bg_ai = True
    elif gen_background_ai(offer["niche"], bg_png):
        bg_ai = True
    elif premium_gradient_bg(offer["niche"], bg_png):
        bg_ai = False
    else:
        raise SystemExit("erro: Pillow indisponivel para gerar fundo")

    vpath = _tmp("gs_out.mp4")
    titled = overlay_title_vertical(bg_png, topic, _tmp("gs_final.png"))
    if has_product and prod_png and os.path.exists(prod_png):
        # VERTICAL 9:16 mobile: PRODUTO flutuando sobre FUNDO em movimento + titulo pequeno no topo
        try:
            make_video_dynamic(titled, prod_png, apath, vpath, dur, W=VW, H=VH)
        except Exception as e:
            print("aviso: video dinamico falhou, usando composicao estatica:", str(e)[:80])
            key_png = _tmp("gs_key.png")
            if not composite_vertical(titled, prod_png, key_png):
                key_png = titled
            make_video_vertical(key_png, apath, vpath, dur)
    else:
        make_video_vertical(titled, apath, vpath, dur)
    print(f"[GLOBALSUP] video {os.path.getsize(vpath) / 1e6:.1f}MB @1080x1920 VERTICAL mobile")

    # MUSICA DE FUNDO automatica (CC-BY, gratis) sob a locucao
    vpath = mix_bg_music(vpath, offer["niche"])

    # ── QA + NOTA antes de publicar (fundo IA + produto + voz + video ok) ───────────────────────
    _score = 0; _iss = []
    if bg_ai: _score += 25
    else: _iss.append("fundo nao-IA (gradiente)")
    if has_product: _score += 30
    else: _iss.append("sem produto real")
    if dur and dur > 3: _score += 25
    else: _iss.append("voz muito curta")
    if os.path.getsize(vpath) > 200000: _score += 20
    else: _iss.append("video suspeito (muito pequeno)")
    try:
        os.makedirs(os.path.join("data", "qa"), exist_ok=True)
        _frame = os.path.join("data", "qa", slug + "_product.png")
        _ts = max(0.5, min(float(dur) - 0.3, float(dur) * 0.5))
        subprocess.run(["ffmpeg", "-y", "-ss", str(_ts), "-i", vpath, "-vframes", "1", "-q:v", "2", _frame],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(os.path.join("data", "qa", slug + "_product.json"), "w", encoding="utf-8") as _f:
            json.dump({"slug": slug, "score": _score, "issues": _iss,
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, _f)
        print("[QA] frame salvo:", _frame)
    except Exception as _e:
        print("aviso: frame QA (produto) falhou:", str(_e)[:70])
    print("[QA] nota=%d/100 | %s" % (_score, "OK" if not _iss else "; ".join(_iss)))
    if os.environ.get("PRODUCTS_DRY_RUN", "") == "1":
        print("[QA] DRY_RUN=1 — frame+nota salvos, NAO publicando (apenas teste).")
        return
    if _score < int(os.environ.get("QA_MIN", "80")):
        print("[QA] nota baixa — BLOQUEADO, nao publicando.")
        return

    # thumbnail viral com a imagem REAL do produto
    tpath = _tmp("gs_thumb.png")
    has_thumb = make_thumb(offer["label"], prod_png, has_product, tpath)

    # 3) VIRAL packaging
    at = token(rt)
    title = viral_title(offer["name"]).replace("<", "").replace(">", "")[:100]
    desc = description(topic, offer)
    desc = (desc or "") + "\n\n" + AI_DISCLOSURE + "\n" + MUSIC_ATTR
    tags = build_tags(topic, offer["subkw"], offer["niche"])

    meta = {"snippet": {"title": title, "description": desc, "tags": tags,
                        "categoryId": "26", "defaultLanguage": "en"},
            "status": {"privacyStatus": os.environ.get("PRIVACY", "public").strip(),
                       "selfDeclaredMadeForKids": False, "madeForKids": False}}
    out = api_upload(at, meta, vpath)
    vid = out.get("id")
    tmsg = set_thumb(at, vid, tpath) if has_thumb else "sem thumb"

    # registra produto publicado (rotaciona pelo slug; não repete)
    record = {"slug": slug, "name": offer["name"], "network": offer["network"],
              "niche": offer["niche"], "affiliate_url": offer["affiliate_url"],
              "official_page_url": offer.get("official_page_url"),
              "retailer_url": offer.get("retailer_url"),
              "image_url": offer.get("image_url") if has_product else None,
              "video_id": vid, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    state.setdefault("published", []).append(record)
    state["last"] = record
    save_state(state)

    print("[GLOBALSUP] PUBLICADO https://youtu.be/" + str(vid)
          + " | slug=" + slug + " | tags=" + str(len(tags))
          + " | " + str(tmsg) + " | publicados=" + str(len(state["published"])))


if __name__ == "__main__":
    main()
# regra-zero publisher v3 (produtos REAIS do site + imagem OFICIAL intacta;
# background engine: OpenAI gpt-image-1 -> Gemini -> FLUX -> Pillow; Ken Burns via ffmpeg zoompan)
# EOF

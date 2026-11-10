"""
SK케미칼 PSM 이행상태평가 심사단 웰컴보드 생성기 (3종)

- 출력: 3840x2160 (가로형 2종), 2160x3840 (세로형 1종) PNG
- 컬러: SK Red  #EA002C (Pantone 186C, RGB 234/0/44)
        SK Orange #FF7A00 (Pantone 158C, RGB 255/122/0)
- 서체: Pretendard (OFL) — FONT_DIR 에 otf 파일 필요
- 실행: python make_boards.py  [FONT_DIR 환경변수로 폰트 경로 지정 가능]

현장 정보(사업장명, 일자 등)는 아래 CONFIG 만 수정하면 됩니다.
"""
import os
from PIL import Image, ImageDraw, ImageFont

# ───────────────────────── CONFIG ─────────────────────────
SITE = "SK케미칼 울산공장"
SITE_EN = "SK chemicals · Ulsan Plant"
DATE = "2026. 11."
HOSTS = "고용노동부  ·  한국산업안전보건공단"
FONT_DIR = os.environ.get("FONT_DIR", os.path.join(os.path.dirname(__file__), "fonts"))
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SS = 2  # 슈퍼샘플링 배율 (안티앨리어싱)

SK_RED = (234, 0, 44)
SK_ORANGE = (255, 122, 0)
INK = (28, 30, 34)
INK_2 = (88, 92, 100)
INK_3 = (150, 153, 160)
PAPER = (247, 246, 243)
RULE = (214, 212, 206)
WHITE = (255, 255, 255)

PSM12 = [
    ("공정안전자료", "PSI"),
    ("공정위험성평가", "PHA"),
    ("안전운전계획", "SOP"),
    ("설비점검·검사·보수", "MI"),
    ("안전작업허가", "PTW"),
    ("도급업체 안전관리", "CSM"),
    ("근로자 교육훈련", "TRN"),
    ("가동 전 점검", "PSSR"),
    ("변경요소 관리", "MOC"),
    ("자체감사", "AUD"),
    ("공정사고 조사", "INV"),
    ("비상조치계획", "ERP"),
]


# ───────────────────────── helpers ─────────────────────────
_font_cache = {}


def F(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            os.path.join(FONT_DIR, f"Pretendard-{weight}.otf"), int(size * SS)
        )
    return _font_cache[key]


def s(v):
    return int(round(v * SS))


def text(d, xy, t, font, fill, anchor="ls", tracking=0):
    """tracking: em 단위 자간 (예: 0.12). 0 이면 일반 렌더."""
    x, y = s(xy[0]), s(xy[1])
    if not tracking:
        d.text((x, y), t, font=font, fill=fill, anchor=anchor)
        return d.textlength(t, font=font) / SS
    gap = font.size * tracking
    total = sum(d.textlength(c, font=font) for c in t) + gap * (len(t) - 1)
    if anchor[0] == "r":
        x -= total
    elif anchor[0] == "m":
        x -= total / 2
    for c in t:
        d.text((x, y), c, font=font, fill=fill, anchor="l" + anchor[1])
        x += d.textlength(c, font=font) + gap
    return total / SS


def tlen(d, t, font, tracking=0):
    w = d.textlength(t, font=font)
    if tracking:
        w += font.size * tracking * (len(t) - 1)
    return w / SS


def rect(d, x0, y0, x1, y1, fill=None, outline=None, width=1, r=0):
    box = [s(x0), s(y0), s(x1), s(y1)]
    if r:
        d.rounded_rectangle(box, radius=s(r), fill=fill, outline=outline, width=s(width) if outline else 0)
    else:
        d.rectangle(box, fill=fill, outline=outline, width=s(width) if outline else 0)


def line(d, pts, fill, width=1):
    d.line([(s(x), s(y)) for x, y in pts], fill=fill, width=max(1, s(width)), joint="curve")


def hgrad(img, x0, y0, x1, y1, c0, c1):
    """가로 그라디언트 (블렌딩 영역 최소화를 위해 짧은 구간에만 사용)."""
    w, h = s(x1) - s(x0), s(y1) - s(y0)
    g = Image.new("RGB", (w, 1))
    for i in range(w):
        t = i / max(1, w - 1)
        g.putpixel((i, 0), tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3)))
    img.paste(g.resize((w, h)), (s(x0), s(y0)))


def wordmark(d, x, y, size, dark=True):
    """SK chemicals 워드마크 자리 (공식 로고 파일로 교체 권장)."""
    w = text(d, (x, y), "SK", F("Black", size), SK_RED)
    text(d, (x + w + size * 0.18, y), "chemicals", F("SemiBold", size),
         INK if dark else WHITE, tracking=-0.01)


def save(img, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    out = img.resize((img.width // SS, img.height // SS), Image.LANCZOS)
    path = os.path.join(OUT_DIR, name)
    out.save(path, dpi=(300, 300), optimize=True)
    print("saved", path, out.size)


# ───────────────────── Board A : Editorial / Light ─────────────────────
def board_a():
    W, H = 3840, 2160
    img = Image.new("RGB", (s(W), s(H)), PAPER)
    d = ImageDraw.Draw(img)
    M = 200                       # outer margin
    SPLIT = 2440                  # right panel start

    # right panel – SK Red
    rect(d, SPLIT, 0, W, H, fill=SK_RED)
    rect(d, SPLIT, 0, SPLIT + 14, H, fill=SK_ORANGE)

    # header
    wordmark(d, M, M + 40, 64)
    text(d, (SPLIT - 160, M + 40), "PROCESS SAFETY MANAGEMENT", F("SemiBold", 30), INK_2,
         anchor="rs", tracking=0.22)
    rect(d, M, M + 110, SPLIT - 160, M + 112, fill=RULE)

    # kicker
    y = 760
    rect(d, M, y - 30, M + 64, y - 22, fill=SK_ORANGE)
    text(d, (M + 92, y - 14), "2026 공정안전보고서 이행상태평가", F("SemiBold", 44), SK_ORANGE, anchor="ls")

    # title
    text(d, (M - 6, y + 190), "심사단 여러분의", F("Light", 150), INK, tracking=-0.03)
    text(d, (M - 6, y + 390), "방문을 환영합니다", F("ExtraBold", 150), INK, tracking=-0.035)

    # host line
    text(d, (M, y + 560), HOSTS, F("Medium", 52), INK_2)

    # statement
    yb = 1640
    rect(d, M, yb, M + 4, yb + 230, fill=SK_RED)
    text(d, (M + 50, yb + 72), "공정안전은 SHE 경영의 출발점이자 최우선 원칙입니다.", F("SemiBold", 54), INK)
    text(d, (M + 50, yb + 150), "12대 PSM 요소를 현장의 일상 업무로 실행하고,", F("Regular", 42), INK_2)
    text(d, (M + 50, yb + 214), "기록과 데이터로 그 이행을 증명하겠습니다.", F("Regular", 42), INK_2)

    # footer
    text(d, (M, H - 120), SITE, F("Bold", 40), INK)
    text(d, (SPLIT - 160, H - 120), DATE, F("Medium", 40), INK_2, anchor="rs", tracking=0.05)

    # right panel content – PSM 12 elements
    px = SPLIT + 150
    text(d, (px, M + 40), "PSM 12 ELEMENTS", F("Bold", 30), (255, 214, 214), tracking=0.24)
    text(d, (px, M + 190), "12개의 요소,", F("Light", 96), WHITE, tracking=-0.03)
    text(d, (px, M + 310), "하나의 원칙", F("ExtraBold", 96), WHITE, tracking=-0.03)

    top, rowh = 760, 102
    right = W - 150
    for i, (ko, en) in enumerate(PSM12):
        yy = top + i * rowh
        rect(d, px, yy, right, yy + 1.5, fill=(244, 110, 130))
        text(d, (px, yy + 68), f"{i + 1:02d}", F("SemiBold", 34), (255, 196, 160), tracking=0.06)
        text(d, (px + 110, yy + 68), ko, F("SemiBold", 46), WHITE)
        text(d, (right, yy + 68), en, F("Medium", 30), (255, 196, 196), anchor="rs", tracking=0.16)
    yy = top + 12 * rowh
    rect(d, px, yy, right, yy + 1.5, fill=(244, 110, 130))
    text(d, (px, H - 120), SITE_EN, F("Medium", 30), (255, 214, 214), tracking=0.08)

    save(img, "welcome_A_editorial_3840x2160.png")


# ───────────────────── Board B : P&ID / Dark ─────────────────────
def board_b():
    W, H = 3840, 2160
    BG = (20, 22, 27)
    GRID = (31, 34, 40)
    LINEC = (70, 76, 88)
    LABEL = (120, 126, 138)
    img = Image.new("RGB", (s(W), s(H)), BG)
    d = ImageDraw.Draw(img)
    M = 200

    # engineering grid
    for gx in range(0, W + 1, 80):
        line(d, [(gx, 0), (gx, H)], GRID, 1)
    for gy in range(0, H + 1, 80):
        line(d, [(0, gy), (W, gy)], GRID, 1)

    # ── schematic (P&ID style) lower right ──
    def valve(cx, cy, size=28, col=LINEC, vertical=False):
        if not vertical:
            d.polygon([(s(cx - size), s(cy - size * .6)), (s(cx), s(cy)), (s(cx - size), s(cy + size * .6))], outline=col, fill=BG, width=s(3))
            d.polygon([(s(cx + size), s(cy - size * .6)), (s(cx), s(cy)), (s(cx + size), s(cy + size * .6))], outline=col, fill=BG, width=s(3))
        else:
            d.polygon([(s(cx - size * .6), s(cy - size)), (s(cx), s(cy)), (s(cx + size * .6), s(cy - size))], outline=col, fill=BG, width=s(3))
            d.polygon([(s(cx - size * .6), s(cy + size)), (s(cx), s(cy)), (s(cx + size * .6), s(cy + size))], outline=col, fill=BG, width=s(3))

    def bubble(cx, cy, tag1, tag2, col=LINEC, tcol=LABEL, r=54):
        d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], outline=col, fill=BG, width=s(3))
        line(d, [(cx - r, cy), (cx + r, cy)], col, 2)
        text(d, (cx, cy - 12), tag1, F("SemiBold", 22), tcol, anchor="ms")
        text(d, (cx, cy + 32), tag2, F("Medium", 20), tcol, anchor="ms")

    def vessel(x0, y0, x1, y1, col=LINEC):
        r = (x1 - x0) / 2
        d.rounded_rectangle([s(x0), s(y0), s(x1), s(y1)], radius=s(r), outline=col, fill=BG, width=s(3))

    base = 1580
    # feed line with orange→red highlighted path
    hot = SK_ORANGE
    line(d, [(1680, base), (2060, base)], hot, 5)
    valve(1840, base, col=hot)
    text(d, (1700, base - 40), "FEED", F("SemiBold", 22), hot, tracking=0.2)

    # reactor
    vessel(2060, 1180, 2360, 1960)
    for k in range(1, 4):
        line(d, [(2080, 1180 + k * 190), (2340, 1180 + k * 190)], (48, 52, 60), 2)
    text(d, (2210, 2030), "R-101", F("SemiBold", 24), LABEL, anchor="ms", tracking=0.12)
    # PSV on top of reactor
    line(d, [(2210, 1180), (2210, 1040)], SK_RED, 4)
    d.polygon([(s(2190), s(1040)), (s(2230), s(1040)), (s(2210), s(1000))], outline=SK_RED, fill=BG, width=s(3))
    line(d, [(2210, 1000), (2210, 940), (2700, 940)], SK_RED, 4)
    text(d, (2240, 1060), "PSV-101", F("SemiBold", 22), SK_RED, tracking=0.1)
    text(d, (2720, 948), "TO FLARE", F("SemiBold", 22), SK_RED, anchor="ls", tracking=0.2)

    # reactor → column
    line(d, [(2360, 1700), (2700, 1700)], LINEC, 4)
    valve(2530, 1700)
    # pump
    d.ellipse([s(2600), s(1740), s(2680), s(1820)], outline=LINEC, fill=BG, width=s(3))
    line(d, [(2640, 1700), (2640, 1740)], LINEC, 4)
    text(d, (2640, 1870), "P-102", F("SemiBold", 22), LABEL, anchor="ms", tracking=0.12)

    # column
    vessel(2700, 1060, 2900, 2000)
    for k in range(1, 9):
        yk = 1100 + k * 100
        line(d, [(2716, yk), (2884, yk)], (48, 52, 60), 2)
    text(d, (2930, 1990), "C-201", F("SemiBold", 22), LABEL, anchor="ls", tracking=0.12)

    # overhead → condenser → drum
    line(d, [(2800, 1060), (2800, 1000), (3200, 1000), (3200, 1160)], LINEC, 4)
    d.ellipse([s(3150), s(1160), s(3250), s(1260)], outline=LINEC, fill=BG, width=s(3))
    line(d, [(3170, 1180), (3230, 1240)], LINEC, 2)
    line(d, [(3200, 1260), (3200, 1360)], LINEC, 4)
    d.rounded_rectangle([s(3060), s(1360), s(3440), s(1520)], radius=s(80), outline=LINEC, fill=BG, width=s(3))
    text(d, (3250, 1580), "D-202", F("SemiBold", 22), LABEL, anchor="ms", tracking=0.12)
    line(d, [(3440, 1440), (3640, 1440)], LINEC, 4)
    valve(3540, 1440)
    text(d, (3640, 1420), "PRODUCT", F("SemiBold", 22), LABEL, anchor="rs", tracking=0.2)
    # bottoms
    line(d, [(2800, 2000), (2800, 2080), (3640, 2080)], LINEC, 4)

    # instrumentation (dashed signal lines)
    def dashed(p0, p1, col=LINEC):
        (x0, y0), (x1, y1) = p0, p1
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / 18)
        for i in range(0, n, 2):
            a, b = i / n, min(1, (i + 1) / n)
            line(d, [(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)], col, 2)

    dashed((2360, 1400), (2480, 1400))
    bubble(2534, 1400, "TIC", "101")
    dashed((2900, 1300), (3000, 1300))
    bubble(3054, 1300, "PT", "201")
    dashed((3250, 1360), (3250, 1300)); dashed((3250, 1300), (3340, 1300))
    bubble(3394, 1250, "LIC", "202")
    dashed((1840, base - 28), (1840, base - 140))
    bubble(1840, base - 194, "FV", "100", col=hot, tcol=hot)
    # SIS interlock tag
    d.rectangle([s(2440), s(1200), s(2600), s(1270)], outline=SK_ORANGE, width=s(3))
    text(d, (2520, 1246), "SIS · SIL2", F("Bold", 22), SK_ORANGE, anchor="ms", tracking=0.1)
    dashed((2360, 1235), (2440, 1235), SK_ORANGE)

    # ── typography (top left) ──
    wordmark(d, M, M + 40, 60, dark=False)
    text(d, (W - M, M + 40), "PROCESS SAFETY  ·  BY DESIGN, BY OPERATION", F("SemiBold", 26), LABEL,
         anchor="rs", tracking=0.22)

    y = 640
    hgrad(img, M, y - 30, M + 120, y - 22, SK_ORANGE, SK_RED)
    text(d, (M + 150, y - 14), "공정안전보고서 이행상태평가 심사단 방문을 환영합니다", F("SemiBold", 42), (230, 232, 236))
    text(d, (M - 6, y + 200), "안전은 설계에서 시작해", F("Light", 132), WHITE, tracking=-0.035)
    text(d, (M - 6, y + 380), "운전으로 증명합니다", F("ExtraBold", 132), WHITE, tracking=-0.04)
    text(d, (M, y + 520), HOSTS, F("Medium", 44), LABEL)

    # three commitments (bottom left)
    cy = 1560
    items = [
        ("01", "위험을 먼저 봅니다", "HAZOP·LOPA 기반 위험성평가"),
        ("02", "변경은 반드시 검증합니다", "MOC · PSSR 절차 준수"),
        ("03", "비상에 늘 대비합니다", "정기 비상대응 훈련"),
    ]
    colw = 480
    for i, (n, h, sub) in enumerate(items):
        x = M + i * colw
        rect(d, x, cy, x + colw - 50, cy + 2, fill=(70, 76, 88) if i else SK_ORANGE)
        text(d, (x, cy + 70), n, F("Bold", 28), SK_ORANGE, tracking=0.12)
        text(d, (x, cy + 150), h, F("Bold", 40), WHITE)
        text(d, (x, cy + 210), sub, F("Regular", 30), LABEL)

    text(d, (M, H - 110), SITE, F("Bold", 36), WHITE)
    tw = tlen(d, SITE, F("Bold", 36))
    text(d, (M + tw + 30, H - 110), DATE, F("Medium", 36), LABEL, tracking=0.05)

    save(img, "welcome_B_pid_dark_3840x2160.png")


# ───────────────────── Board C : Portrait / Standee ─────────────────────
def board_c():
    W, H = 2160, 3840
    img = Image.new("RGB", (s(W), s(H)), WHITE)
    d = ImageDraw.Draw(img)
    M = 160

    # header
    wordmark(d, M, M + 50, 58)
    text(d, (W - M, M + 50), DATE, F("Medium", 36), INK_2, anchor="rs", tracking=0.05)

    # giant numeral 12
    big = F("Black", 1180)
    bb = d.textbbox((0, 0), "12", font=big)
    nx = s(M - 30) - bb[0]
    ny = s(420) - bb[1]
    d.text((nx, ny), "12", font=big, fill=SK_RED)
    # orange slice across numeral (clip)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text((nx, ny), "12", font=big, fill=255)
    band = Image.new("L", img.size, 0)
    ImageDraw.Draw(band).rectangle([0, s(1200), img.width, s(1330)], fill=255)
    from PIL import ImageChops
    m2 = ImageChops.multiply(mask, band)
    img.paste(Image.new("RGB", img.size, SK_ORANGE), (0, 0), m2)
    d = ImageDraw.Draw(img)

    # caption beside numeral
    cx = 1520
    text(d, (cx, 720), "PSM", F("Bold", 30), SK_RED, tracking=0.24)
    text(d, (cx, 790), "ELEMENTS", F("Bold", 30), SK_RED, tracking=0.24)
    rect(d, cx, 840, cx + 60, 846, fill=SK_ORANGE)
    text(d, (cx, 940), "12개의 요소,", F("Light", 62), INK, tracking=-0.03)
    text(d, (cx, 1025), "하나의 원칙", F("ExtraBold", 62), INK, tracking=-0.03)

    # list
    top = 1640
    rowh = 118
    colgap = 80
    colw = (W - 2 * M - colgap) / 2
    text(d, (M, top - 60), "공정안전관리(PSM) 12대 실천요소", F("Bold", 40), INK)
    text(d, (W - M, top - 60), "Process Safety Management", F("Medium", 28), INK_3, anchor="rs", tracking=0.06)
    rect(d, M, top - 20, W - M, top - 16, fill=INK)
    for i, (ko, en) in enumerate(PSM12):
        col, row = divmod(i, 6)
        x = M + col * (colw + colgap)
        y = top + row * rowh
        text(d, (x, y + 76), f"{i + 1:02d}", F("Bold", 30), SK_RED, tracking=0.06)
        text(d, (x + 82, y + 76), ko, F("SemiBold", 42), INK)
        text(d, (x + colw, y + 76), en, F("Medium", 24), INK_3, anchor="rs", tracking=0.16)
        rect(d, x, y + rowh, x + colw, y + rowh + 1.5, fill=RULE)

    # red welcome block
    by = 2620
    rect(d, 0, by, W, H, fill=SK_RED)
    hgrad(img, 0, by, W, by + 16, SK_ORANGE, SK_RED)
    d = ImageDraw.Draw(img)
    text(d, (M, by + 220), "WELCOME", F("Bold", 30), (255, 214, 214), tracking=0.3)
    text(d, (M, by + 380), "공정안전보고서 이행상태평가", F("Light", 92), WHITE, tracking=-0.03)
    text(d, (M, by + 510), "심사단을 환영합니다", F("ExtraBold", 92), WHITE, tracking=-0.035)
    text(d, (M, by + 620), HOSTS, F("Medium", 40), (255, 220, 220))
    rect(d, M, by + 720, W - M, by + 721.5, fill=(244, 110, 130))
    text(d, (M, by + 830), "공정안전을 SHE 경영의 최우선 원칙으로,", F("SemiBold", 44), WHITE)
    text(d, (M, by + 900), "12대 요소를 매일의 현장 업무로 실행합니다.", F("Regular", 44), (255, 228, 228))
    text(d, (M, H - 150), SITE, F("Bold", 40), WHITE)
    text(d, (W - M, H - 150), SITE_EN, F("Medium", 28), (255, 214, 214), anchor="rs", tracking=0.08)

    save(img, "welcome_C_standee_2160x3840.png")


if __name__ == "__main__":
    board_a()
    board_b()
    board_c()

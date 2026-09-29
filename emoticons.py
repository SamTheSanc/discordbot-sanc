import re
from collections import Counter

# Regex patterns to strip non-emoticon tokens to prevent false positives
URL_RE = re.compile(r'https?://\S+')
DISCORD_EMOJI_RE = re.compile(r'<a?:\w+:\d+>')
DISCORD_MENTION_RE = re.compile(r'<[@#&]!?\d+>')
TIME_RE = re.compile(r'\b\d{1,2}:\d{2}\b')
SHORTCODE_RE = re.compile(r':[a-zA-Z0-9_]+:')
WIN_PATH_RE = re.compile(r'\b[A-Za-z]:\\[^\s]*')

# Boundary definitions:
# Lead bound: start of string or whitespace or open punctuation/bracket
LEAD_BOUND = r'(?:(?<=[\s\(\[\{])|^)'
# Trail bound: end of string or whitespace or common trailing punctuation/bracket
TRAIL_BOUND = r'(?:(?=[\s\)\}\].,!?~])|$)'

PATTERNS = [
    # Kaomoji / Anime expressions / Special faces
    r'¯\\_\(ツ\)_/¯',
    r'\^[_\-~\.\^wWoOvVuU]+\^;?',   # ^-^, ^_^, ^~^, ^.^, ^w^, ^o^, ^O^, ^v^, ^u^
    r'\^{2,3}',                     # ^^, ^^^
    r'>[_\.\-wWoO]<',               # >.<, >_<, >w<, >o<
    r'>[_\.\-]>',                   # >_>, >.>
    r'<[_\.\-]<',                   # <_<, <.<
    r'[-_]{1,2}[\.\-_][-]{1,2}',    # -_-, -.-, -__-
    r'[TtQqXx][_\.\-][TtQqXx]',     # T_T, T.T, Q_Q, x_x, X_X, x.x
    r'[oO0][_\.][oO0]',             # o_o, O_O, o.o, O.O
    r';[-_~];',                     # ;-;
    r'\b[uU][wW][uU]\b',            # uwu, UwU, UWU
    r'\b[oO][wW][oO]\b',            # owo, OwO, OWO
    r'\b[xX][dD]\b',                # XD, xD, xd
    r'\b[xX][pP]\b',                # XP, xP, xp
    r'</?3',                        # <3, </3
    
    # Western emoticons:
    # Eyes: :, ;, =, 8, >:
    # Optional nose: -, ~, o, *, ^
    # Mouth: ), (, D, d, p, P, ], [, }, {, 3, c, C, o, O, 0, >, <, \, /, |
    r'(?:>[:;=]|[:;=8])[-~o\*\^]?(?:[)(DdpP\]\[}{3cCoOvV><\/\\|])',
    
    # Reversed Western emoticons:
    # Mouth + optional nose + eyes
    r'(?:[)(DdpP\]\[}{3cCoOvV><\/\\|])[-~o\*\^]?[:;=8]',
]

COMBINED_RE = re.compile('|'.join(f'({LEAD_BOUND}{p}{TRAIL_BOUND})' for p in PATTERNS))

def extract_emoticons(text: str) -> dict[str, int]:
    """
    Extracts ASCII emoticons from text and returns a dictionary of {emoticon: count}.
    Filters out false positives from URLs, Discord custom emojis, shortcodes, and timestamps.
    """
    if not text:
        return {}

    # Strip constructs that contain characters matching emoticon parts
    cleaned = URL_RE.sub(' ', text)
    cleaned = DISCORD_EMOJI_RE.sub(' ', cleaned)
    cleaned = DISCORD_MENTION_RE.sub(' ', cleaned)
    cleaned = SHORTCODE_RE.sub(' ', cleaned)
    cleaned = TIME_RE.sub(' ', cleaned)
    cleaned = WIN_PATH_RE.sub(' ', cleaned)

    matches = [m.group(0).strip() for m in COMBINED_RE.finditer(cleaned)]
    return dict(Counter(matches))

"""Multilingual civic lexicon: transliteration, language ID and English normalisation.

Why this module exists
----------------------
A Marathi voice note and a Hinglish text about the *same* pothole share almost no
characters::

    "कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ"
    "Katraj dairy ke saamne bada gaddha hai, school ke paas"

Any similarity measure over raw text scores those two near zero, so the two
reports become two tickets and the city never learns that ten people are
complaining about one hole in one road.

This module maps both sentences onto the same canonical English bag of terms
(``pothole katraj dairy school opposite``). Everything downstream - the offline
classifier, the deduplication embedder, the citizen-facing summary - then works
across languages without a neural translation model.

It is also *auditable*: ``analyse()`` returns the exact surface forms that
matched, so an officer reviewing a decision can see that the word "गड्ढा" is why
a complaint was filed as a pothole. A neural embedding cannot offer that.

Coverage is deliberately narrow and deep: civic vocabulary for the nine
NagarNetra categories in English, Hindi, Marathi and romanised Hinglish. It is
not a general translator and does not pretend to be (docs/LIMITATIONS.md).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
#  1. Devanagari -> Latin transliteration
# ---------------------------------------------------------------------------
#  A light ITRANS-style transliterator. Its job is not scholarly accuracy, it is
#  to give unknown words (mostly place names) a Latin form that can be compared
#  with how a citizen would type the same place on a phone keyboard.

_HALANT = "्"
_NUKTA = "़"

_CONSONANTS: dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
}

_INDEPENDENT_VOWELS: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऍ": "e", "ऑ": "o",
}

_MATRAS: dict[str, str] = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॅ": "e", "ॉ": "o",
}

_SIGNS: dict[str, str] = {
    "ं": "n",   # anusvara
    "ँ": "n",   # chandrabindu
    "ः": "h",   # visarga
    "।": " ",   # danda
    "॥": " ",   # double danda
}

_DEVANAGARI_RANGE = re.compile(r"[ऀ-ॿ]")


def transliterate(text: str) -> str:
    """Convert Devanagari to a rough Latin form. Non-Devanagari passes through."""
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in _CONSONANTS:
            base = _CONSONANTS[ch]
            nxt = text[i + 1] if i + 1 < length else ""
            if nxt == _NUKTA:  # treat the nukta form as its base consonant
                nxt = text[i + 2] if i + 2 < length else ""
                i += 1
            if nxt == _HALANT:
                out.append(base)
                i += 2
                continue
            if nxt in _MATRAS:
                out.append(base + _MATRAS[nxt])
                i += 2
                continue
            out.append(base + "a")
            i += 1
            continue
        if ch in _INDEPENDENT_VOWELS:
            out.append(_INDEPENDENT_VOWELS[ch])
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
        elif ch == _HALANT or ch == _NUKTA:
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_FOLD_RULES: tuple[tuple[str, str], ...] = (
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
    ("ph", "f"), ("v", "w"), ("z", "j"), ("q", "k"),
)


def fold(token: str) -> str:
    """Aggressively normalise a Latin token so spelling variants collide.

    ``kaatraja`` -> ``katraj``; ``Katraj`` -> ``katraj``; ``khadda`` -> ``khada``.
    Used only as a *secondary* matcher so that it cannot create false positives
    on short words.
    """
    token = unicodedata.normalize("NFKD", token.lower())
    token = "".join(c for c in token if c.isalnum())
    for src, dst in _FOLD_RULES:
        token = token.replace(src, dst)
    # collapse doubled letters: khadda -> khada
    folded: list[str] = []
    for ch in token:
        if not folded or folded[-1] != ch:
            folded.append(ch)
    token = "".join(folded)
    # a trailing inherent vowel is an artefact of transliteration
    if len(token) > 4 and token.endswith("a"):
        token = token[:-1]
    return token


# ---------------------------------------------------------------------------
#  2. Civic term table
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Term:
    """One civic concept and every surface form we expect citizens to use.

    ``variants`` mixes scripts on purpose. Devanagari entries are matched as
    substrings (so inflections like खड्डा / खड्डे / खड्ड्यात all hit the stem
    खड्ड), Latin entries are matched on word boundaries plus a folded fallback.
    """

    canonical: str
    variants: tuple[str, ...]
    category: str | None = None
    hazard: str | None = None
    severity: int | None = None
    weight: float = 1.0


# fmt: off
TERMS: tuple[Term, ...] = (
    # ---------------- pothole / road ----------------
    Term("pothole", ("pothole", "potholes", "pot hole", "khadda", "khaddaa", "khadde", "gaddha",
                     "gadda", "gadde", "gaddhe", "ghadda", "khaddyat", "खड्ड", "गड्ढ", "खडड"),
         category="pothole_road", weight=2.0),
    Term("road", ("road", "roads", "rasta", "raasta", "rastyavar", "sadak", "sadka",
                  "रस्त", "रास्त", "सड़क", "सडक", "मार्ग"), category="pothole_road", weight=0.8),
    Term("road_broken", ("road broken", "broken road", "road damage", "damaged road", "tutlela",
                         "tuta hua", "kharab rasta", "उखडल", "तुटल", "टूट", "खराब रस्त", "नादुरुस्त"),
         category="pothole_road", weight=1.6),
    Term("speed_breaker", ("speed breaker", "speedbreaker", "gati rodhak", "गतिरोधक", "स्पीड ब्रेकर"),
         category="pothole_road", weight=1.2),

    # ---------------- garbage ----------------
    Term("garbage", ("garbage", "rubbish", "trash", "waste", "kachra", "kachara", "kooda", "kuda",
                     "कचर", "कचऱ", "कूड", "घनकचर", "केर"), category="garbage_waste", weight=2.0),
    Term("garbage_bin", ("dustbin", "bin", "kachra kundi", "ghanta gadi", "कुंडी", "डस्टबिन",
                         "घंटा गाडी", "कचरापेट"), category="garbage_waste", weight=1.4),
    Term("not_collected", ("not collected", "uchalla nahi", "nahi uthaya", "safai nahi",
                           "उचलल", "उठाय", "साफसफाई", "सफाई"), category="garbage_waste", weight=1.2),
    Term("bad_smell", ("smell", "stink", "stinking", "durgandhi", "badbu", "badboo",
                       "दुर्गंध", "बदबू", "वास येत"), category="garbage_waste",
         hazard="health_risk", weight=1.3),
    Term("debris", ("debris", "malba", "rubble", "construction waste", "राडारोड", "मलबा", "राबिट"),
         category="garbage_waste", weight=1.2),

    # ---------------- streetlight ----------------
    Term("streetlight", ("streetlight", "street light", "street lamp", "lamp post", "batti",
                         "बत्ती", "पथदिव", "दिवा", "दिवे", "लाईट", "लाइट", "स्ट्रीट लाईट"),
         category="streetlight", weight=2.0),
    Term("light_not_working", ("light not working", "light nahi", "light band", "batti band",
                               "bandh aahe", "lai nahi", "fused", "not glowing", "बंद आहे",
                               "चालू नाही", "बंद है", "जळत नाही", "लागत नाही"),
         category="streetlight", weight=1.5),
    Term("darkness", ("dark", "darkness", "andhar", "andhera", "andheri", "अंधार", "अंधेर",
                      "काळोख"), category="streetlight", hazard="accident_risk", weight=1.4),
    Term("pole", ("pole", "khamb", "खांब", "खंब", "पोल"), category="streetlight", weight=0.7),

    # ---------------- drainage / sewage ----------------
    Term("drain", ("drain", "drainage", "nali", "naali", "gutter", "nalla", "nallah",
                   "नाली", "नाल", "गटार", "गटर", "सांडपाण"), category="drainage_sewage", weight=2.0),
    Term("sewage", ("sewage", "sewer", "malnissaran", "मलनिस्सारण", "मैला", "सांडपाणी"),
         category="drainage_sewage", weight=1.6),
    Term("manhole", ("manhole", "man hole", "chamber", "मॅनहोल", "मैनहोल", "चेंबर", "चैम्बर"),
         category="drainage_sewage", weight=1.8),
    Term("open_manhole", ("open manhole", "manhole open", "cover missing", "no cover",
                          "dhakkan nahi", "zakan nahi", "उघडे मॅनहोल", "खुला मैनहोल", "झाकण नाही",
                          "ढक्कन नहीं", "झाकण उघड", "उघड चेंबर"),
         category="drainage_sewage", hazard="open_manhole", severity=5, weight=2.5),
    Term("drain_blocked", ("blocked drain", "drain blocked", "choked", "chokup", "tumble",
                           "तुंबल", "तुंबले", "चोकअप", "जाम", "अडकल"),
         category="drainage_sewage", weight=1.5),
    Term("overflow", ("overflow", "overflowing", "bahar aa raha", "वाहत", "ओसंडून", "बाहेर येत"),
         category="drainage_sewage", hazard="health_risk", weight=1.4),

    # ---------------- water supply ----------------
    Term("water_supply", ("water supply", "paani", "pani", "water", "nal", "nall", "tap",
                          "पाणी", "पानी", "नळ", "नल"), category="water_supply", weight=1.8),
    Term("no_water", ("no water", "paani nahi", "pani nahi", "water nahi", "supply band",
                      "पाणी येत नाही", "पाणी नाही", "पानी नहीं", "पुरवठा बंद"),
         category="water_supply", weight=2.0),
    Term("pipeline_leak", ("pipeline leak", "leakage", "leaking", "pipe burst", "galti",
                           "गळत", "गळती", "पाइपलाइन", "पाईप", "फुटल"),
         category="water_supply", weight=1.8),
    Term("dirty_water", ("dirty water", "contaminated", "muddy water", "gadul", "gandha pani",
                         "गढूळ", "गंदा पानी", "दूषित", "घाण पाणी"),
         category="water_supply", hazard="health_risk", severity=4, weight=1.8),
    Term("tanker", ("tanker", "टँकर", "टैंकर"), category="water_supply", weight=1.0),

    # ---------------- stray animals ----------------
    Term("stray_dog", ("stray dog", "stray dogs", "street dog", "kutra", "kutre", "kutta",
                       "kutte", "bhatke kutre", "कुत्र", "कुत्त", "श्वान", "भटक"),
         category="stray_animals", weight=2.0),
    Term("cattle", ("cattle", "cow", "bull", "buffalo", "gai", "mhais", "गाय", "बैल", "म्हैस",
                    "जनावर", "गुरे", "मवेशी"), category="stray_animals", weight=1.6),
    Term("pig", ("pig", "pigs", "dukkar", "डुक्कर", "डुकर", "सूअर"),
         category="stray_animals", hazard="health_risk", weight=1.6),
    Term("monkey", ("monkey", "monkeys", "makad", "bandar", "माकड", "बंदर", "वानर"),
         category="stray_animals", weight=1.5),
    Term("animal_bite", ("bite", "bitten", "chavla", "kaatla", "chava", "चावल", "चाव", "काटल",
                         "काट लिया", "हल्ला"), category="stray_animals",
         hazard="accident_risk", severity=5, weight=1.8),

    # ---------------- encroachment / parking ----------------
    Term("encroachment", ("encroachment", "encroached", "atikraman", "अतिक्रमण", "कब्जा", "अतिक्रमन"),
         category="encroachment_illegal_parking", weight=2.0),
    Term("illegal_parking", ("illegal parking", "no parking", "wrong parking", "double parking",
                             "avaidh parking", "पार्किंग", "बेकायदा", "अवैध", "नो पार्किंग"),
         category="encroachment_illegal_parking", weight=1.8),
    Term("footpath_blocked", ("footpath", "foot path", "pavement", "sidewalk", "padpath",
                              "फुटपाथ", "पदपथ", "पादचारी"),
         category="encroachment_illegal_parking", weight=1.5),
    Term("hawker", ("hawker", "hawkers", "vendor", "stall", "handcart", "pheriwala", "thela",
                    "फेरीवाल", "हातगाड", "ठेल", "टपर"),
         category="encroachment_illegal_parking", weight=1.6),
    Term("blocked_way", ("blocked", "obstruction", "rasta band", "adthala", "अडथळ", "अडवल",
                         "रस्ता अडव", "बंद केल"), category="encroachment_illegal_parking", weight=1.0),

    # ---------------- tree ----------------
    Term("tree", ("tree", "trees", "jhad", "zad", "ped", "vruksha", "झाड", "पेड", "पेड़", "वृक्ष"),
         category="tree_fall_hazard", weight=1.8),
    Term("branch", ("branch", "branches", "fandi", "dahal", "tehni", "फांद", "डहाळ", "टहन", "शाख"),
         category="tree_fall_hazard", weight=1.6),
    Term("tree_fallen", ("tree fallen", "fallen tree", "uprooted", "jhad padle", "ped gira",
                         "कोसळ", "पडल", "उन्मळ", "गिर गया", "गिरा"),
         category="tree_fall_hazard", hazard="accident_risk", severity=4, weight=2.0),
    Term("tree_dangerous", ("dangerous tree", "leaning tree", "dhokadayak jhad", "धोकादायक झाड",
                            "झुकल"), category="tree_fall_hazard", hazard="accident_risk", weight=1.6),

    # ---------------- hazards (category-neutral) ----------------
    Term("school", ("school", "skool", "shala", "vidyalaya", "college", "anganwadi",
                    "शाळ", "स्कूल", "विद्यालय", "कॉलेज", "महाविद्यालय", "अंगणवाड"),
         hazard="near_school", weight=1.2),
    Term("hospital", ("hospital", "davakhana", "dawakhana", "clinic", "dispensary", "phc",
                      "रुग्णालय", "दवाखान", "अस्पताल", "क्लिनिक", "हॉस्पिटल"),
         hazard="near_hospital", weight=1.2),
    Term("live_wire", ("live wire", "open wire", "electric wire", "current", "karant", "shock",
                       "spark", "sparking", "electricity pole wire", "विजेच", "वीज तार", "करंट",
                       "शॉक", "ठिणग", "बिजली का तार", "खुला तार", "चिंगार"),
         hazard="live_wire", severity=5, category="streetlight", weight=2.2),
    Term("flooding", ("flooding", "flood", "waterlogging", "water logging", "paani bharla",
                      "पाणी साचल", "पाणी तुंबल", "जलभराव", "पूर", "भरल"),
         hazard="flooding", severity=4, weight=1.8),
    Term("accident", ("accident", "accidents", "apghat", "durghatna", "collision", "fell down",
                      "slipped", "injured", "अपघात", "दुर्घटन", "पडून", "जखमी", "घसरल", "चोट"),
         hazard="accident_risk", severity=4, weight=1.8),
    Term("dangerous", ("dangerous", "danger", "risky", "unsafe", "dhokadayak", "khatarnak",
                       "धोकादायक", "धोक", "खतरनाक", "असुरक्षित"),
         hazard="accident_risk", severity=4, weight=1.4),
    Term("disease", ("disease", "dengue", "malaria", "mosquito", "mosquitoes", "machhar", "das",
                     "infection", "aajar", "bimari", "डेंग", "मलेरिय", "डास", "मच्छर", "आजार",
                     "बीमार", "संसर्ग", "साथीच"), hazard="health_risk", severity=4, weight=1.6),

    # ---------------- severity / urgency modifiers ----------------
    Term("very_large", ("very big", "very large", "huge", "khup motha", "bahut bada", "prachand",
                        "खूप मोठ", "प्रचंड", "बहुत बड", "अवाढव्य"), severity=5, weight=0.6),
    Term("large", ("big", "large", "deep", "motha", "bada", "khol", "मोठ", "बड", "खोल"),
         severity=4, weight=0.5),
    Term("small", ("small", "minor", "chhota", "lahan", "thoda", "लहान", "छोट", "किरकोळ", "थोड"),
         severity=2, weight=0.5),
    Term("urgent", ("urgent", "emergency", "immediately", "turant", "tatdine", "jaldi",
                    "तातडीन", "तात्काळ", "तुरंत", "लवकर", "आपत्कालीन"), severity=5, weight=0.7),
    Term("long_pending", ("since many days", "for weeks", "for months", "many days", "kai divas",
                          "bahut din", "महिन्या", "आठवड", "कित्येक दिवस", "बऱ्याच दिवस", "कई दिन"),
         severity=4, weight=0.5),

    # ---------------- spatial relations (kept for the summary) ----------------
    Term("opposite", ("opposite", "in front of", "saamne", "samne", "samor", "समोर", "सामने"),
         weight=0.3),
    Term("near", ("near", "beside", "next to", "jawal", "javal", "paas", "pass", "जवळ", "पास", "शेजार", "नजीक"), weight=0.3),
    Term("behind", ("behind", "mage", "peeche", "मागे", "पीछे"), weight=0.3),
    Term("corner", ("corner", "chowk", "square", "junction", "naka", "चौक", "नाक", "कोपर"),
         weight=0.4),
)
# fmt: on


# ---------------------------------------------------------------------------
#  3. Pune landmarks
# ---------------------------------------------------------------------------
#: Locality name -> surface forms. Used to recover a location when the citizen
#: gives no GPS, and to strengthen the dedup signal ("Katraj dairy" twice).
LANDMARKS: dict[str, tuple[str, ...]] = {
    "Katraj": ("katraj", "कात्रज"),
    "Swargate": ("swargate", "स्वारगेट"),
    "Kothrud": ("kothrud", "कोथरूड", "कोथरुड"),
    "Hadapsar": ("hadapsar", "हडपसर"),
    "Shivajinagar": ("shivajinagar", "shivaji nagar", "शिवाजीनगर", "शिवाजी नगर"),
    "Hinjewadi": ("hinjewadi", "hinjawadi", "हिंजवडी", "हिंजेवाडी"),
    "Wakad": ("wakad", "वाकड"),
    "Kondhwa": ("kondhwa", "kondhawa", "कोंढवा"),
    "Aundh": ("aundh", "औंध"),
    "Baner": ("baner", "बाणेर"),
    "Warje": ("warje", "वारजे"),
    "Yerawada": ("yerawada", "yerwada", "येरवडा"),
}

#: Secondary landmark nouns that sharpen a location without naming a locality.
PLACE_NOUNS: dict[str, tuple[str, ...]] = {
    "dairy": ("dairy", "डेअरी", "डेयरी", "दूध डेअरी"),
    "petrol pump": ("petrol pump", "petrolpump", "पेट्रोल पंप", "पेट्रोलपंप"),
    "bus stop": ("bus stop", "bus stand", "बस स्टॉप", "बस स्टँड", "बस थांब"),
    "chowk": ("chowk", "chauk", "चौक"),
    "temple": ("temple", "mandir", "मंदिर", "देऊळ"),
    "market": ("market", "mandai", "bazaar", "मार्केट", "मंडई", "बाजार"),
    "station": ("station", "रेल्वे स्टेशन", "स्टेशन"),
    "garden": ("garden", "udyan", "park", "उद्यान", "बाग", "पार्क"),
    "society": ("society", "sosayti", "सोसायटी", "सोसायटी"),
    "bridge": ("bridge", "pul", "पूल", "ब्रिज"),
}


# ---------------------------------------------------------------------------
#  4. Language identification
# ---------------------------------------------------------------------------
#: Function words unique (or near-unique) to Marathi.
_MARATHI_MARKERS: tuple[str, ...] = (
    "आहे", "आहेत", "नाही", "नाहीत", "मध्ये", "जवळ", "समोर", "पासून", "वर",
    "च्या", "ची", "चा", "चे", "ला", "ने", "कृपया", "करा", "झाले", "होत",
    "येथे", "इथे", "तिथे", "खूप", "आम्ही", "माझ", "त्यांनी", "मुळे",
)
#: Function words unique (or near-unique) to Hindi.
_HINDI_MARKERS: tuple[str, ...] = (
    "है", "हैं", "नहीं", "में", "पर", "का", "की", "के", "से", "को",
    "कृपया", "करो", "करिए", "गया", "रहा", "रही", "यहाँ", "यहां", "वहाँ",
    "बहुत", "हमारे", "मेरा", "हुआ", "दीजिये", "दीजिए",
)
#: Romanised Indic function words: the signature of Hinglish.
_HINGLISH_MARKERS: tuple[str, ...] = (
    "hai", "hain", "nahi", "nahin", "nahiye", "aahe", "ahe", "ahet", "kripya",
    "kripaya", "saamne", "samne", "samor", "jawal", "javal", "paas", "pass",
    "bahut", "bohot", "khup", "bada", "motha", "chhota", "lahan", "jaldi",
    "mera", "maza", "majha", "yaha", "yahan", "ithe", "idhar", "udhar", "wala",
    "karo", "kara", "diya", "gaya", "hua", "raha", "mein", "aahet", "tumbla",
    "padla", "nikal", "kar", "bhi", "toh", "abhi", "roz", "divas", "din",
)
_ENGLISH_STOPWORDS: tuple[str, ...] = (
    "the", "is", "are", "there", "near", "please", "has", "have", "been", "and",
    "from", "this", "that", "with", "for", "not", "very", "about", "since",
)

_WORD_RE = re.compile(r"[a-zA-Z]+")


def detect_language(text: str) -> tuple[str, float]:
    """Identify the report language.

    Returns ``(code, confidence)`` where code is one of
    ``en | hi | mr | hinglish | unknown``.

    Script decides Devanagari vs Latin; function words decide Hindi vs Marathi,
    and English vs Hinglish. Deliberately rule-based so the decision can be
    explained to a citizen who disputes it.
    """
    if not text or not text.strip():
        return "unknown", 0.0

    devanagari = len(_DEVANAGARI_RANGE.findall(text))
    latin = len(_WORD_RE.findall(text))
    lowered = text.lower()

    if devanagari >= 2 and devanagari >= latin:
        mr_hits = sum(1 for marker in _MARATHI_MARKERS if marker in text)
        hi_hits = sum(1 for marker in _HINDI_MARKERS if marker in text)
        if mr_hits == hi_hits == 0:
            # Devanagari with no function words: nouns only. Marathi is the
            # majority language of Pune, so that is the safer default, but we
            # say so with low confidence.
            return "mr", 0.45
        if mr_hits >= hi_hits:
            return "mr", min(0.95, 0.6 + 0.1 * (mr_hits - hi_hits))
        return "hi", min(0.95, 0.6 + 0.1 * (hi_hits - mr_hits))

    tokens = set(_WORD_RE.findall(lowered))
    if not tokens:
        return "unknown", 0.0

    hinglish_hits = len(tokens & set(_HINGLISH_MARKERS))
    english_hits = len(tokens & set(_ENGLISH_STOPWORDS))

    if hinglish_hits and hinglish_hits >= english_hits:
        return "hinglish", min(0.95, 0.55 + 0.12 * hinglish_hits)
    if english_hits:
        return "en", min(0.95, 0.55 + 0.1 * english_hits)
    # Latin script, no function words either way (e.g. "pothole katraj").
    # Treat as English but flag the uncertainty.
    return "en", 0.4


# ---------------------------------------------------------------------------
#  5. Analysis
# ---------------------------------------------------------------------------
@dataclass
class Analysis:
    """Everything the lexicon could extract from one complaint."""

    language: str
    language_confidence: float
    english_tokens: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    matched_surface: list[str] = field(default_factory=list)
    category_scores: dict[str, float] = field(default_factory=dict)
    hazards: list[str] = field(default_factory=list)
    severity_hint: int | None = None
    landmarks: list[str] = field(default_factory=list)
    place_nouns: list[str] = field(default_factory=list)
    transliterated: str = ""
    summary_en: str = ""
    #: Similarity key for deduplication. Deliberately NOT the same string as
    #: ``summary_en``: a title is written to be read by an officer, a match key
    #: is written to be compared by a machine. Landmarks are repeated because
    #: *where* is the strongest evidence that two reports describe one physical
    #: problem - the category is already a hard gate by the time we compare.
    #: Measured on the held-out split: AUC 0.904 for the title, 0.989 for this.
    match_text: str = ""

    @property
    def best_category(self) -> tuple[str | None, float]:
        """Top category and its share of total lexical evidence."""
        if not self.category_scores:
            return None, 0.0
        total = sum(self.category_scores.values())
        key = max(self.category_scores, key=lambda k: self.category_scores[k])
        return key, (self.category_scores[key] / total if total else 0.0)


def _build_indexes() -> tuple[list[tuple[str, Term]], dict[str, Term], dict[str, list[Term]]]:
    """Split the term table into substring, exact-word and folded indexes."""
    devanagari_index: list[tuple[str, Term]] = []
    latin_index: dict[str, Term] = {}
    folded_index: dict[str, list[Term]] = {}
    for term in TERMS:
        for variant in term.variants:
            if _DEVANAGARI_RANGE.search(variant):
                devanagari_index.append((variant, term))
            else:
                latin_index.setdefault(variant.lower(), term)
                if len(variant) >= 5 and " " not in variant:
                    folded_index.setdefault(fold(variant), []).append(term)
    # Longest first so "open manhole" wins over "manhole".
    devanagari_index.sort(key=lambda pair: len(pair[0]), reverse=True)
    return devanagari_index, latin_index, folded_index


_DEVANAGARI_INDEX, _LATIN_INDEX, _FOLDED_INDEX = _build_indexes()
_MULTIWORD_LATIN: tuple[str, ...] = tuple(
    sorted((v for v in _LATIN_INDEX if " " in v), key=len, reverse=True)
)


def analyse(text: str) -> Analysis:
    """Run the full lexical analysis over one complaint.

    This is the offline counterpart to the LLM understanding stage: it produces
    a language, a category vote, hazard flags, a severity hint, landmarks and a
    canonical English summary - with the evidence for each.
    """
    language, language_confidence = detect_language(text or "")
    analysis = Analysis(language=language, language_confidence=language_confidence)
    if not text or not text.strip():
        return analysis

    lowered = text.lower()
    analysis.transliterated = transliterate(text)
    latin_blob = f"{lowered} {analysis.transliterated.lower()}"
    tokens = _WORD_RE.findall(latin_blob)
    folded_tokens = {fold(t) for t in tokens if len(t) >= 4}

    seen: set[str] = set()
    severity_votes: list[int] = []

    def record(term: Term, surface: str) -> None:
        if term.canonical in seen:
            return
        seen.add(term.canonical)
        analysis.matched_terms.append(term.canonical)
        analysis.matched_surface.append(surface)
        if term.category:
            analysis.category_scores[term.category] = (
                analysis.category_scores.get(term.category, 0.0) + term.weight
            )
        if term.hazard and term.hazard not in analysis.hazards:
            analysis.hazards.append(term.hazard)
        if term.severity:
            severity_votes.append(term.severity)

    # (a) Devanagari substrings, longest first.
    for variant, term in _DEVANAGARI_INDEX:
        if variant in text:
            record(term, variant)

    # (b) Latin multi-word phrases.
    for phrase in _MULTIWORD_LATIN:
        if phrase in latin_blob:
            record(_LATIN_INDEX[phrase], phrase)

    # (c) Latin single tokens (exact), then folded as a weaker fallback.
    token_set = set(tokens)
    for token in sorted(token_set):
        term = _LATIN_INDEX.get(token)
        if term is not None:
            record(term, token)
    for folded_token in sorted(folded_tokens):
        for term in _FOLDED_INDEX.get(folded_token, ()):
            record(term, folded_token)

    # (d) Landmarks and place nouns.
    for canonical, variants in LANDMARKS.items():
        for variant in variants:
            if (variant in text) or (variant in latin_blob) or (fold(variant) in folded_tokens):
                if canonical not in analysis.landmarks:
                    analysis.landmarks.append(canonical)
                break
    for canonical, variants in PLACE_NOUNS.items():
        for variant in variants:
            if (variant in text) or (variant in latin_blob):
                if canonical not in analysis.place_nouns:
                    analysis.place_nouns.append(canonical)
                break

    if severity_votes:
        analysis.severity_hint = max(severity_votes)

    analysis.english_tokens = _english_tokens(analysis)
    analysis.summary_en = build_summary(analysis)
    analysis.match_text = build_match_text(analysis)
    return analysis


def build_match_text(analysis: Analysis) -> str:
    """Canonical string used for deduplication similarity."""
    landmarks = [name.lower() for name in analysis.landmarks]
    # Sorted, because the vectoriser uses word bigrams and character n-grams:
    # two identical complaints whose terms merely matched in a different order
    # scored 0.905 instead of 1.000 before this.
    return " ".join(sorted([*analysis.english_tokens, *landmarks, *landmarks]))


#: Terms that describe *where*, not *what* - excluded from the leading phrase.
_SPATIAL = {"opposite", "near", "behind", "corner"}
#: Intensity words: they set severity, they are not the subject of the complaint.
_MODIFIERS = {"very_large", "large", "small", "urgent", "long_pending", "dangerous"}
#: Proximity terms already rendered in the trailing "(near school)" clause.
_PROXIMITY = {"school", "hospital"}
_TERM_BY_CANONICAL: dict[str, Term] = {t.canonical: t for t in TERMS}


def _english_tokens(analysis: Analysis) -> list[str]:
    """Canonical English bag used by the embedder and the offline classifier."""
    tokens: list[str] = []
    for term in analysis.matched_terms:
        tokens.extend(term.replace("_", " ").split())
    tokens.extend(h.replace("_", " ") for h in analysis.hazards)
    tokens.extend(landmark.lower() for landmark in analysis.landmarks)
    tokens.extend(noun for noun in analysis.place_nouns)
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def build_summary(analysis: Analysis) -> str:
    """Compose a short, human-readable English summary from lexical evidence.

    Example: ``"Pothole, road near Katraj dairy (near school)"``. When nothing
    matched it returns ``""`` so the caller can route the complaint to a human
    instead of inventing a summary.
    """
    candidates = [
        t
        for t in analysis.matched_terms
        if t not in _SPATIAL and t not in _MODIFIERS and t not in _PROXIMITY
    ]
    # Drop a term that is fully implied by a more specific one that also
    # matched: "manhole" adds nothing once "open manhole" is present.
    specific: list[str] = []
    for term in candidates:
        parts = set(term.split("_"))
        if any(other != term and parts < set(other.split("_")) for other in candidates):
            continue
        specific.append(term)

    # Deterministic order, and led by the category the complaint is actually
    # about. Without this tiering a report that merely mentions water logging
    # next to a pothole produced the title "Pothole, water supply, road", which
    # reads as three different problems to an officer scanning a queue.
    dominant_category, _ = analysis.best_category

    def rank(canonical: str) -> tuple[int, float, str]:
        term = _TERM_BY_CANONICAL.get(canonical)
        weight = term.weight if term else 0.0
        if term and term.category == dominant_category:
            tier = 0          # the subject of the complaint
        elif term and term.category:
            tier = 2          # a different category mentioned in passing
        else:
            tier = 1          # category-neutral evidence (hazards, conditions)
        return (tier, -weight, canonical)

    subject_terms = [t.replace("_", " ") for t in sorted(specific, key=rank)]
    if not subject_terms and not analysis.landmarks:
        return ""

    subject = ", ".join(subject_terms[:2]) if subject_terms else "civic issue"
    place_bits: list[str] = []
    if analysis.landmarks:
        place_bits.append(analysis.landmarks[0])
    if analysis.place_nouns:
        place_bits.append(analysis.place_nouns[0])
    place = " ".join(place_bits)

    summary = subject.capitalize()
    if place:
        relation = "opposite" if "opposite" in analysis.matched_terms else "near"
        summary = f"{summary} {relation} {place}"
    context = [h.replace("_", " ") for h in analysis.hazards if h in {"near_school", "near_hospital"}]
    if context:
        summary = f"{summary} ({', '.join(context)})"
    return summary

"""Generate data/synthetic_complaints.csv - the multilingual Pune corpus.

ALL DATA PRODUCED HERE IS SYNTHETIC. No real citizen complaint, no real name,
no real phone number appears in this repository (docs/DISCLOSURES.md).

What makes it useful rather than decorative:

* **Four languages** - English, Hindi (Devanagari), Marathi (Devanagari) and
  romanised Hinglish - because that is what a Pune grievance inbox actually
  looks like, and because per-language fairness cannot be measured on an
  English-only corpus.
* **Planted duplicate groups.** A "problem" is one real-world thing at one
  coordinate; between two and nine people report it, in *different languages*,
  using *different words*. Each report carries the ground-truth ``cluster_id``,
  which is what ``scripts/evaluate.py`` scores deduplication against.
* **Two deliberately under-served wards** (Kondhwa, Yerawada) that resolve
  slower and less often, so the equity audit has something real to find.
* **Injected PII** in a minority of reports, so redaction is exercised on
  realistic input instead of on a unit test.
* **A held-out split by cluster**, never by row: if half a duplicate group were
  in train and half in test, the deduplication score would be meaningless.

Deterministic: same seed, same file, every time.

Run:  python scripts/generate_synthetic.py
"""

from __future__ import annotations

import csv
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config.localities import PUNE_LOCALITIES, UNDERSERVED_WARD_CODES  # noqa: E402
from app.config.settings import DATA_DIR  # noqa: E402

SEED = 20260926
TOTAL_TARGET = 430
DUPLICATE_GROUPS = 42
TEST_FRACTION = 0.22

LANGUAGES = ("en", "hi", "mr", "hinglish")
#: Share of complaints per language - Marathi-majority, as Pune would be.
LANGUAGE_WEIGHTS = (0.28, 0.17, 0.35, 0.20)

# ---------------------------------------------------------------------------
#  Phrasing
# ---------------------------------------------------------------------------
# fmt: off
TEMPLATES: dict[str, dict[str, tuple[str, ...]]] = {
    "pothole_road": {
        "en": (
            "There is a big pothole on the road {loc}",
            "Deep pothole {loc}, two-wheelers keep falling",
            "The road {loc} is badly broken and full of holes",
            "Huge crater on the road {loc}, nobody has repaired it",
        ),
        "hi": (
            "{loc} सड़क पर बड़ा गड्ढा है",
            "{loc} गहरा गड्ढा है, गाड़ियाँ गिर रही हैं",
            "{loc} सड़क पूरी टूट गई है",
            "{loc} सड़क पर गड्ढों की वजह से चलना मुश्किल है",
        ),
        "mr": (
            "{loc} रस्त्यावर मोठा खड्डा आहे",
            "{loc} खोल खड्डा आहे, दुचाकी घसरत आहेत",
            "{loc} रस्ता पूर्ण उखडला आहे",
            "{loc} खड्ड्यांमुळे रस्ता खूप खराब झाला आहे",
        ),
        "hinglish": (
            "{loc} road pe bada gaddha hai",
            "{loc} gehra gaddha hai, gaadi girti hai",
            "{loc} rasta puri tarah tut gaya hai",
            "{loc} khadda itna bada hai ki chalna mushkil hai",
        ),
    },
    "garbage_waste": {
        "en": (
            "Garbage has not been collected {loc} for several days",
            "A huge garbage pile {loc} is rotting and smelling",
            "The bin {loc} is overflowing and nobody clears it",
            "People are dumping waste {loc} every night",
        ),
        "hi": (
            "{loc} कई दिनों से कचरा नहीं उठाया गया",
            "{loc} कूड़े का ढेर है और बदबू आ रही है",
            "{loc} कचरा कुंडी भर गई है",
            "{loc} रोज़ रात को लोग कचरा फेंक रहे हैं",
        ),
        "mr": (
            "{loc} कित्येक दिवसांपासून कचरा उचलला नाही",
            "{loc} कचऱ्याचा ढीग आहे आणि दुर्गंधी येत आहे",
            "{loc} कचरा कुंडी भरून वाहत आहे",
            "{loc} रोज रात्री लोक कचरा टाकत आहेत",
        ),
        "hinglish": (
            "{loc} kai din se kachra nahi uthaya",
            "{loc} kachre ka dher hai, badbu aa rahi hai",
            "{loc} dustbin bhar gaya hai koi saaf nahi karta",
            "{loc} log roz raat ko garbage daal rahe hain",
        ),
    },
    "streetlight": {
        "en": (
            "The streetlight {loc} has not been working for a week",
            "It is completely dark {loc} at night, the light is fused",
            "Streetlight pole {loc} is off, unsafe for women",
            "Three lights {loc} are not glowing",
        ),
        "hi": (
            "{loc} स्ट्रीट लाइट एक हफ्ते से बंद है",
            "{loc} रात में पूरा अंधेरा रहता है, लाइट नहीं जलती",
            "{loc} का खंभा बंद है, महिलाओं के लिए असुरक्षित है",
            "{loc} तीन लाइटें नहीं जल रही हैं",
        ),
        "mr": (
            "{loc} पथदिवा आठवडाभरापासून बंद आहे",
            "{loc} रात्री पूर्ण अंधार असतो, दिवे लागत नाहीत",
            "{loc} खांबावरचा दिवा बंद आहे, महिलांसाठी असुरक्षित",
            "{loc} तीन दिवे जळत नाहीत",
        ),
        "hinglish": (
            "{loc} street light ek hafte se band hai",
            "{loc} raat ko pura andhera rehta hai, light nahi hai",
            "{loc} ka khamba band hai, ladies ke liye safe nahi",
            "{loc} teen light nahi jal rahi",
        ),
    },
    "drainage_sewage": {
        "en": (
            "The drain {loc} is completely blocked and overflowing",
            "Manhole cover {loc} is missing, it is very dangerous",
            "Sewage water is flowing on the road {loc}",
            "The nallah {loc} is choked with waste",
        ),
        "hi": (
            "{loc} नाली पूरी तरह जाम है और बह रही है",
            "{loc} मैनहोल का ढक्कन नहीं है, बहुत खतरनाक है",
            "{loc} सड़क पर गंदा पानी बह रहा है",
            "{loc} नाला कचरे से भरा है",
        ),
        "mr": (
            "{loc} गटार पूर्ण तुंबले आहे आणि वाहत आहे",
            "{loc} मॅनहोलचे झाकण नाही, खूप धोकादायक आहे",
            "{loc} रस्त्यावर सांडपाणी वाहत आहे",
            "{loc} नाला कचऱ्याने तुंबला आहे",
        ),
        "hinglish": (
            "{loc} nali puri jam hai aur overflow ho rahi hai",
            "{loc} manhole ka dhakkan nahi hai, bahut khatarnak",
            "{loc} road pe gandha pani beh raha hai",
            "{loc} nalla kachre se bhara hua hai",
        ),
    },
    "water_supply": {
        "en": (
            "There has been no water supply {loc} for three days",
            "The pipeline {loc} is leaking and water is wasted",
            "Dirty water is coming from the tap {loc}",
            "Water comes {loc} for only ten minutes a day",
        ),
        "hi": (
            "{loc} तीन दिन से पानी नहीं आ रहा",
            "{loc} पाइपलाइन से पानी लीक हो रहा है",
            "{loc} नल से गंदा पानी आ रहा है",
            "{loc} सिर्फ दस मिनट पानी आता है",
        ),
        "mr": (
            "{loc} तीन दिवसांपासून पाणी येत नाही",
            "{loc} पाइपलाइनला गळती लागली आहे",
            "{loc} नळाला गढूळ पाणी येत आहे",
            "{loc} फक्त दहा मिनिटे पाणी येते",
        ),
        "hinglish": (
            "{loc} teen din se paani nahi aa raha",
            "{loc} pipeline leak ho rahi hai, paani barbaad",
            "{loc} nal se ganda paani aa raha hai",
            "{loc} sirf das minute paani aata hai",
        ),
    },
    "stray_animals": {
        "en": (
            "A pack of stray dogs {loc} is chasing children",
            "Stray cattle {loc} are blocking the road",
            "Pigs {loc} are creating a health hazard",
            "Stray dogs {loc} bit a delivery boy yesterday",
        ),
        "hi": (
            "{loc} आवारा कुत्तों का झुंड बच्चों के पीछे भागता है",
            "{loc} आवारा जानवर सड़क रोक रहे हैं",
            "{loc} सूअरों से बीमारी फैल रही है",
            "{loc} कल कुत्ते ने एक लड़के को काट लिया",
        ),
        "mr": (
            "{loc} भटक्या कुत्र्यांचा कळप मुलांच्या मागे धावतो",
            "{loc} मोकाट जनावरे रस्ता अडवत आहेत",
            "{loc} डुकरांमुळे आरोग्याचा धोका आहे",
            "{loc} काल कुत्र्याने एका मुलाला चावले",
        ),
        "hinglish": (
            "{loc} stray dogs bacchon ke peeche bhagte hain",
            "{loc} awara jaanwar rasta rok rahe hain",
            "{loc} dukkar se bimari fail rahi hai",
            "{loc} kal kutte ne ek ladke ko kaat liya",
        ),
    },
    "encroachment_illegal_parking": {
        "en": (
            "Hawkers have encroached the footpath {loc}",
            "Cars are parked illegally {loc}, blocking the whole lane",
            "A shop {loc} has extended onto the pavement",
            "Handcarts {loc} block the road every evening",
        ),
        "hi": (
            "{loc} फेरीवालों ने फुटपाथ पर कब्जा कर लिया है",
            "{loc} गाड़ियाँ अवैध रूप से खड़ी हैं, रास्ता बंद है",
            "{loc} दुकान ने फुटपाथ घेर लिया है",
            "{loc} हर शाम ठेले रास्ता रोकते हैं",
        ),
        "mr": (
            "{loc} फेरीवाल्यांनी पदपथावर अतिक्रमण केले आहे",
            "{loc} बेकायदा पार्किंगमुळे रस्ता अडला आहे",
            "{loc} दुकानाने फुटपाथ अडवला आहे",
            "{loc} रोज संध्याकाळी हातगाड्या रस्ता अडवतात",
        ),
        "hinglish": (
            "{loc} hawkers ne footpath par kabza kar liya",
            "{loc} illegal parking se pura rasta band hai",
            "{loc} dukaan ne footpath gher liya hai",
            "{loc} roz shaam ko thele rasta rokte hain",
        ),
    },
    "tree_fall_hazard": {
        "en": (
            "A large tree branch {loc} is about to fall",
            "The tree {loc} fell during the rain and blocks the road",
            "A dangerous leaning tree {loc} needs trimming",
            "Tree branches {loc} are touching the electric wires",
        ),
        "hi": (
            "{loc} पेड़ की बड़ी शाखा गिरने वाली है",
            "{loc} बारिश में पेड़ गिर गया, रास्ता बंद है",
            "{loc} झुका हुआ पेड़ खतरनाक है",
            "{loc} पेड़ की डालियाँ बिजली के तार छू रही हैं",
        ),
        "mr": (
            "{loc} झाडाची मोठी फांदी पडण्याच्या बेतात आहे",
            "{loc} पावसात झाड पडले, रस्ता बंद आहे",
            "{loc} झुकलेले झाड धोकादायक आहे",
            "{loc} झाडाच्या फांद्या विजेच्या तारांना लागत आहेत",
        ),
        "hinglish": (
            "{loc} ped ki badi daali girne wali hai",
            "{loc} baarish me ped gir gaya, rasta band hai",
            "{loc} jhuka hua ped khatarnak hai",
            "{loc} ped ki daaliyan bijli ke taar chhu rahi hain",
        ),
    },
    "other": {
        "en": (
            "The public toilet {loc} has been locked for weeks",
            "The bus shelter {loc} is broken and unusable",
            "Someone has damaged the park benches {loc}",
            "The community notice board {loc} has collapsed",
        ),
        "hi": (
            "{loc} सार्वजनिक शौचालय हफ्तों से बंद है",
            "{loc} बस शेल्टर टूटा हुआ है",
            "{loc} पार्क की बेंचें तोड़ दी गई हैं",
            "{loc} सूचना पट्ट गिर गया है",
        ),
        "mr": (
            "{loc} सार्वजनिक शौचालय कित्येक आठवडे बंद आहे",
            "{loc} बस थांब्याचे छप्पर तुटले आहे",
            "{loc} बागेतील बाक तोडले आहेत",
            "{loc} सूचना फलक कोसळला आहे",
        ),
        "hinglish": (
            "{loc} public toilet kai hafte se band hai",
            "{loc} bus stop toota hua hai",
            "{loc} park ki bench tod di gayi hai",
            "{loc} notice board gir gaya hai",
        ),
    },
}

PLACE_NOUNS: dict[str, dict[str, str]] = {
    "dairy": {"en": "dairy", "hi": "डेअरी", "mr": "डेअरी", "hinglish": "dairy"},
    "chowk": {"en": "chowk", "hi": "चौक", "mr": "चौक", "hinglish": "chowk"},
    "bus stop": {"en": "bus stop", "hi": "बस स्टॉप", "mr": "बस थांबा", "hinglish": "bus stop"},
    "school": {"en": "school", "hi": "स्कूल", "mr": "शाळा", "hinglish": "school"},
    "petrol pump": {"en": "petrol pump", "hi": "पेट्रोल पंप", "mr": "पेट्रोल पंप", "hinglish": "petrol pump"},
    "market": {"en": "market", "hi": "मार्केट", "mr": "मंडई", "hinglish": "market"},
    "temple": {"en": "temple", "hi": "मंदिर", "mr": "मंदिर", "hinglish": "mandir"},
    "garden": {"en": "garden", "hi": "उद्यान", "mr": "उद्यान", "hinglish": "garden"},
    "society": {"en": "society", "hi": "सोसायटी", "mr": "सोसायटी", "hinglish": "society"},
    "bridge": {"en": "bridge", "hi": "पुल", "mr": "पूल", "hinglish": "bridge"},
}

LANDMARK_NAMES: dict[str, dict[str, str]] = {
    "Shivajinagar": {"en": "Shivajinagar", "hi": "शिवाजीनगर", "mr": "शिवाजीनगर", "hinglish": "Shivajinagar"},
    "Swargate": {"en": "Swargate", "hi": "स्वारगेट", "mr": "स्वारगेट", "hinglish": "Swargate"},
    "Kothrud": {"en": "Kothrud", "hi": "कोथरूड", "mr": "कोथरूड", "hinglish": "Kothrud"},
    "Warje": {"en": "Warje", "hi": "वारजे", "mr": "वारजे", "hinglish": "Warje"},
    "Katraj": {"en": "Katraj", "hi": "कात्रज", "mr": "कात्रज", "hinglish": "Katraj"},
    "Kondhwa": {"en": "Kondhwa", "hi": "कोंढवा", "mr": "कोंढवा", "hinglish": "Kondhwa"},
    "Hadapsar": {"en": "Hadapsar", "hi": "हडपसर", "mr": "हडपसर", "hinglish": "Hadapsar"},
    "Yerawada": {"en": "Yerawada", "hi": "येरवडा", "mr": "येरवडा", "hinglish": "Yerawada"},
    "Aundh": {"en": "Aundh", "hi": "औंध", "mr": "औंध", "hinglish": "Aundh"},
    "Baner": {"en": "Baner", "hi": "बाणेर", "mr": "बाणेर", "hinglish": "Baner"},
    "Wakad": {"en": "Wakad", "hi": "वाकड", "mr": "वाकड", "hinglish": "Wakad"},
    "Hinjewadi": {"en": "Hinjewadi", "hi": "हिंजवडी", "mr": "हिंजवडी", "hinglish": "Hinjewadi"},
}

LOCATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "en": ("near {place} {noun}", "opposite {place} {noun}", "at {place} {noun}", "in {place}"),
    "hi": ("{place} {noun} के पास", "{place} {noun} के सामने", "{place} {noun} पर", "{place} में"),
    "mr": ("{place} {noun} जवळ", "{place} {noun} समोर", "{place} {noun} येथे", "{place} मध्ये"),
    "hinglish": ("{place} {noun} ke paas", "{place} {noun} ke saamne", "{place} {noun} pe", "{place} me"),
}

HAZARD_CLAUSES: dict[str, dict[str, str]] = {
    "near_school": {
        "en": ", right next to the school", "hi": ", स्कूल के बिल्कुल पास",
        "mr": ", शाळेच्या अगदी जवळ", "hinglish": ", school ke bilkul paas",
    },
    "near_hospital": {
        "en": ", just outside the hospital", "hi": ", अस्पताल के ठीक बाहर",
        "mr": ", रुग्णालयाच्या बाहेरच", "hinglish": ", hospital ke bahar hi",
    },
    "open_manhole": {
        "en": ", the manhole cover is missing", "hi": ", मैनहोल का ढक्कन गायब है",
        "mr": ", मॅनहोलचे झाकण नाही", "hinglish": ", manhole ka dhakkan gayab hai",
    },
    "live_wire": {
        "en": ", an open electric wire is hanging there", "hi": ", खुला बिजली का तार लटक रहा है",
        "mr": ", उघडी वीज तार लोंबकळत आहे", "hinglish": ", khula bijli ka taar latak raha hai",
    },
    "flooding": {
        "en": ", water has been logged for days", "hi": ", कई दिनों से पानी भरा है",
        "mr": ", कित्येक दिवस पाणी साचले आहे", "hinglish": ", kai din se paani bhara hai",
    },
    "accident_risk": {
        "en": ", two accidents have already happened", "hi": ", दो हादसे हो चुके हैं",
        "mr": ", दोन अपघात झाले आहेत", "hinglish": ", do accident ho chuke hain",
    },
    "health_risk": {
        "en": ", mosquitoes and disease are spreading", "hi": ", मच्छर और बीमारी फैल रही है",
        "mr": ", डास आणि आजार पसरत आहेत", "hinglish": ", machhar aur bimari fail rahi hai",
    },
}

URGENCY_CLAUSES: dict[str, tuple[str, ...]] = {
    "en": ("", ", please fix it urgently", ", it has been like this for two weeks", ", this is very dangerous"),
    "hi": ("", ", कृपया जल्दी ठीक कराइए", ", दो हफ्ते से ऐसा ही है", ", यह बहुत खतरनाक है"),
    "mr": ("", ", कृपया लवकर दुरुस्त करा", ", दोन आठवड्यांपासून असेच आहे", ", हे खूप धोकादायक आहे"),
    "hinglish": ("", ", kripya jaldi theek karo", ", do hafte se aisa hi hai", ", ye bahut khatarnak hai"),
}

#: Synthetic contact details, injected to exercise the redaction stage.
PII_CLAUSES: dict[str, tuple[str, ...]] = {
    "en": (" My number is 98220{n}.", " Contact me at resident{n}@example.com.", " Vehicle MH12{a}{n2}."),
    "hi": (" मेरा नंबर 98220{n} है।", " मुझसे resident{n}@example.com पर संपर्क करें।", " गाड़ी MH12{a}{n2}।"),
    "mr": (" माझा नंबर 98220{n} आहे.", " मला resident{n}@example.com वर संपर्क करा.", " गाडी MH12{a}{n2}."),
    "hinglish": (" Mera number 98220{n} hai.", " Mujhe resident{n}@example.com pe contact karo.", " Gaadi MH12{a}{n2}."),
}

#: Which hazards are plausible for which category.
CATEGORY_HAZARDS: dict[str, tuple[str, ...]] = {
    "pothole_road": ("accident_risk", "near_school", "flooding"),
    "garbage_waste": ("health_risk", "near_school", "near_hospital"),
    "streetlight": ("accident_risk", "live_wire", "near_school"),
    "drainage_sewage": ("open_manhole", "flooding", "health_risk", "near_school"),
    "water_supply": ("health_risk", "near_hospital"),
    "stray_animals": ("accident_risk", "health_risk", "near_school"),
    "encroachment_illegal_parking": ("accident_risk",),
    "tree_fall_hazard": ("accident_risk", "live_wire", "near_school"),
    "other": (),
}
# fmt: on

CATEGORY_KEYS = tuple(TEMPLATES.keys())
#: Realistic mix - potholes and garbage dominate a real Indian civic inbox.
CATEGORY_WEIGHTS = (0.20, 0.19, 0.14, 0.13, 0.10, 0.08, 0.07, 0.05, 0.04)


@dataclass
class SyntheticRow:
    report_id: str
    cluster_id: str
    text: str
    language: str
    category: str
    ward_code: str
    lat: float
    lon: float
    location_text: str
    created_at: str
    status: str
    resolved_at: str
    severity: int
    hazard_flags: str
    has_photo: int
    contains_pii: int
    split: str


def _weighted_choice(rng: random.Random, options, weights):
    return rng.choices(list(options), weights=list(weights), k=1)[0]


def _location_phrase(rng: random.Random, language: str, landmark: str, noun_key: str) -> str:
    pattern = rng.choice(LOCATION_PATTERNS[language])
    return pattern.format(
        place=LANDMARK_NAMES[landmark][language], noun=PLACE_NOUNS[noun_key][language]
    ).strip()


def _compose(
    rng: random.Random,
    language: str,
    category: str,
    landmark: str,
    noun_key: str,
    hazards: list[str],
    template_index: int,
) -> tuple[str, bool]:
    body = TEMPLATES[category][language][template_index % len(TEMPLATES[category][language])]
    text = body.format(loc=_location_phrase(rng, language, landmark, noun_key))
    for hazard in hazards:
        clause = HAZARD_CLAUSES.get(hazard, {}).get(language)
        if clause:
            text += clause
    text += rng.choice(URGENCY_CLAUSES[language])

    contains_pii = rng.random() < 0.09
    if contains_pii:
        template = rng.choice(PII_CLAUSES[language])
        text += template.format(
            n=f"{rng.randint(10000, 99999)}",
            n2=f"{rng.randint(1000, 9999)}",
            a="".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2)),
        )
    return text, contains_pii


def _jitter(rng: random.Random, lat: float, lon: float, metres: float) -> tuple[float, float]:
    """Random offset up to ``metres`` in a random direction."""
    import math

    bearing = rng.uniform(0, 2 * math.pi)
    distance = rng.uniform(0, metres)
    d_lat = (distance * math.cos(bearing)) / 111_000.0
    d_lon = (distance * math.sin(bearing)) / (111_000.0 * math.cos(math.radians(lat)))
    return round(lat + d_lat, 6), round(lon + d_lon, 6)


def main() -> None:
    rng = random.Random(SEED)
    now = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)
    rows: list[SyntheticRow] = []

    # Each "problem" is one real-world thing. Duplicate groups get many reports.
    problems: list[dict] = []
    for index in range(DUPLICATE_GROUPS):
        locality = rng.choice(PUNE_LOCALITIES)
        category = _weighted_choice(rng, CATEGORY_KEYS, CATEGORY_WEIGHTS)
        problems.append(
            {
                "cluster_id": f"C{index:03d}",
                "locality": locality,
                "category": category,
                "noun": rng.choice(list(PLACE_NOUNS)),
                "reports": rng.choice([2, 2, 3, 3, 4, 5, 6, 9]),
            }
        )

    # Top up with one-off complaints until the corpus reaches its target size.
    # The duplicate total is fixed before the loop; recomputing it inside would
    # chase a moving target and silently under-generate.
    duplicate_report_total = sum(problem["reports"] for problem in problems)
    for singleton_index in range(max(0, TOTAL_TARGET - duplicate_report_total)):
        locality = rng.choice(PUNE_LOCALITIES)
        problems.append(
            {
                "cluster_id": f"S{singleton_index:03d}",
                "locality": locality,
                "category": _weighted_choice(rng, CATEGORY_KEYS, CATEGORY_WEIGHTS),
                "noun": rng.choice(list(PLACE_NOUNS)),
                "reports": 1,
            }
        )

    # Hold out whole clusters, never individual reports.
    rng.shuffle(problems)
    test_cutoff = int(len(problems) * TEST_FRACTION)
    for position, problem in enumerate(problems):
        problem["split"] = "test" if position < test_cutoff else "train"

    counter = 0
    for problem in problems:
        locality = problem["locality"]
        category = problem["category"]
        possible = CATEGORY_HAZARDS[category]
        hazards = (
            rng.sample(possible, k=min(len(possible), rng.choice([0, 1, 1, 2])))
            if possible
            else []
        )
        severity = 3
        if {"live_wire", "open_manhole"} & set(hazards):
            severity = 5
        elif {"accident_risk", "flooding"} & set(hazards):
            severity = 4
        elif rng.random() < 0.25:
            severity = rng.choice([2, 4])

        base_lat, base_lon = _jitter(rng, locality.lat, locality.lon, 3000)
        first_seen = now - timedelta(
            days=rng.uniform(0.5, 29.0), hours=rng.uniform(0, 23)
        )

        underserved = locality.ward_code in UNDERSERVED_WARD_CODES
        resolve_probability = 0.32 if underserved else 0.62
        is_resolved = rng.random() < resolve_probability
        if is_resolved:
            # Under-served wards take roughly three times as long to close.
            base_hours = rng.uniform(6, 60)
            resolution_hours = base_hours * (3.1 if underserved else 1.0)
            resolved_at = first_seen + timedelta(hours=resolution_hours)
            if resolved_at > now:
                resolved_at = now - timedelta(hours=rng.uniform(1, 8))
        else:
            resolved_at = None

        # Different people, different languages, different words, same problem.
        languages_used: list[str] = []
        for report_index in range(problem["reports"]):
            if report_index == 0:
                language = _weighted_choice(rng, LANGUAGES, LANGUAGE_WEIGHTS)
            else:
                remaining = [lang for lang in LANGUAGES if lang not in languages_used] or list(LANGUAGES)
                language = rng.choice(remaining)
            languages_used.append(language)

            lat, lon = _jitter(rng, base_lat, base_lon, 55)
            created_at = first_seen + timedelta(hours=rng.uniform(0, 72) * report_index)
            if created_at > now:
                created_at = now - timedelta(minutes=rng.uniform(5, 120))

            text, contains_pii = _compose(
                rng, language, category, locality.name, problem["noun"], hazards, report_index
            )
            counter += 1
            rows.append(
                SyntheticRow(
                    report_id=f"SYN{counter:05d}",
                    cluster_id=problem["cluster_id"],
                    text=text,
                    language=language,
                    category=category,
                    ward_code=locality.ward_code,
                    lat=lat,
                    lon=lon,
                    location_text=_location_phrase(rng, "en", locality.name, problem["noun"]),
                    created_at=created_at.isoformat(),
                    status="resolved" if resolved_at is not None else "open",
                    resolved_at=resolved_at.isoformat() if resolved_at is not None else "",
                    severity=severity,
                    hazard_flags="|".join(hazards),
                    has_photo=int(rng.random() < 0.22),
                    contains_pii=int(contains_pii),
                    split=problem["split"],
                )
            )

    rows.sort(key=lambda row: row.created_at)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / "synthetic_complaints.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    # ---- report ----
    by_language: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_split: dict[str, int] = {}
    for row in rows:
        by_language[row.language] = by_language.get(row.language, 0) + 1
        by_category[row.category] = by_category.get(row.category, 0) + 1
        by_split[row.split] = by_split.get(row.split, 0) + 1

    duplicate_clusters = {r.cluster_id for r in rows if r.cluster_id.startswith("C")}
    print(f"wrote {target.relative_to(ROOT)}  ({len(rows)} complaints)")
    print(f"  languages   : {by_language}")
    print(f"  split       : {by_split}")
    print(f"  clusters    : {len(duplicate_clusters)} multi-report groups, "
          f"{sum(1 for r in rows if r.cluster_id.startswith('S'))} singletons")
    print(f"  with PII    : {sum(r.contains_pii for r in rows)}")
    print(f"  with photo  : {sum(r.has_photo for r in rows)}")
    print(f"  categories  : {by_category}")


if __name__ == "__main__":
    main()

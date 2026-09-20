"""Canonical taxonomy: issue categories, hazard flags, statuses, departments.

This module is the single source of truth. The API, the offline classifier, the
synthetic data generator and the frontend all derive their vocabularies here so
that a new category can never be half-added.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    """One civic issue category with its municipal owner and display labels."""

    key: str
    label_en: str
    label_hi: str
    label_mr: str
    department: str
    icon: str
    examples: tuple[str, ...] = field(default=())


CATEGORIES: tuple[Category, ...] = (
    Category(
        key="pothole_road",
        label_en="Pothole / Road damage",
        label_hi="गड्ढा / सड़क क्षति",
        label_mr="खड्डा / रस्ता नादुरुस्त",
        department="roads",
        icon="road",
        examples=("pothole", "broken road", "sunken patch", "speed breaker damage"),
    ),
    Category(
        key="garbage_waste",
        label_en="Garbage / Solid waste",
        label_hi="कचरा / ठोस अपशिष्ट",
        label_mr="कचरा / घनकचरा",
        department="swm",
        icon="trash",
        examples=("garbage pile", "bin not cleared", "debris dumping"),
    ),
    Category(
        key="streetlight",
        label_en="Streetlight",
        label_hi="स्ट्रीट लाइट",
        label_mr="पथदिवा",
        department="electrical",
        icon="bulb",
        examples=("light not working", "dark street", "flickering pole"),
    ),
    Category(
        key="drainage_sewage",
        label_en="Drainage / Sewage",
        label_hi="नाली / सीवेज",
        label_mr="गटार / मलनिस्सारण",
        department="sewerage",
        icon="drain",
        examples=("open manhole", "overflowing drain", "blocked nallah"),
    ),
    Category(
        key="water_supply",
        label_en="Water supply",
        label_hi="जल आपूर्ति",
        label_mr="पाणीपुरवठा",
        department="water",
        icon="droplet",
        examples=("no water", "pipeline leak", "contaminated water"),
    ),
    Category(
        key="stray_animals",
        label_en="Stray animals",
        label_hi="आवारा पशु",
        label_mr="भटकी जनावरे",
        department="veterinary",
        icon="paw",
        examples=("stray dogs", "cattle on road", "monkey menace"),
    ),
    Category(
        key="encroachment_illegal_parking",
        label_en="Encroachment / Illegal parking",
        label_hi="अतिक्रमण / अवैध पार्किंग",
        label_mr="अतिक्रमण / बेकायदा पार्किंग",
        department="encroachment",
        icon="cone",
        examples=("footpath blocked", "hawker encroachment", "no-parking violation"),
    ),
    Category(
        key="tree_fall_hazard",
        label_en="Tree fall / Branch hazard",
        label_hi="पेड़ गिरना / शाखा खतरा",
        label_mr="झाड पडणे / फांदी धोका",
        department="garden",
        icon="tree",
        examples=("fallen tree", "dangerous branch", "tree on wire"),
    ),
    Category(
        key="other",
        label_en="Other",
        label_hi="अन्य",
        label_mr="इतर",
        department="central",
        icon="dots",
        examples=("anything that does not fit the list",),
    ),
)

CATEGORY_KEYS: tuple[str, ...] = tuple(c.key for c in CATEGORIES)
CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
#: Categories the classifier is allowed to predict (``other`` is a routing bucket,
#: reachable only via low confidence or an explicit officer choice).
CLASSIFIABLE_KEYS: tuple[str, ...] = tuple(k for k in CATEGORY_KEYS if k != "other")


@dataclass(frozen=True)
class Department:
    code: str
    name: str
    short: str


DEPARTMENTS: tuple[Department, ...] = (
    Department("roads", "Road & Bridges Department", "Roads"),
    Department("swm", "Solid Waste Management Department", "SWM"),
    Department("electrical", "Electrical Department", "Electrical"),
    Department("sewerage", "Sewerage & Drainage Department", "Sewerage"),
    Department("water", "Water Supply Department", "Water"),
    Department("veterinary", "Veterinary & Animal Welfare Cell", "Veterinary"),
    Department("encroachment", "Anti-Encroachment & Traffic Cell", "Encroachment"),
    Department("garden", "Garden & Tree Authority", "Garden"),
    Department("central", "Central Grievance Cell", "Central"),
)
DEPARTMENT_BY_CODE: dict[str, Department] = {d.code: d for d in DEPARTMENTS}


@dataclass(frozen=True)
class HazardFlag:
    key: str
    label_en: str
    label_hi: str
    label_mr: str
    #: A hazard the citizen can plausibly observe, vs. one we derive from map data.
    derived: bool = False


HAZARD_FLAGS: tuple[HazardFlag, ...] = (
    HazardFlag("live_wire", "Live/exposed wire", "खुला बिजली तार", "उघडी वीज तार"),
    HazardFlag("open_manhole", "Open manhole", "खुला मैनहोल", "उघडे मॅनहोल"),
    HazardFlag("flooding", "Water logging / flooding", "जलभराव", "पाणी साचणे"),
    HazardFlag("accident_risk", "Accident risk", "दुर्घटना का खतरा", "अपघाताचा धोका"),
    HazardFlag("near_school", "Near a school", "स्कूल के पास", "शाळेजवळ"),
    HazardFlag("near_hospital", "Near a hospital", "अस्पताल के पास", "रुग्णालयाजवळ"),
    HazardFlag("health_risk", "Public health risk", "स्वास्थ्य जोखिम", "आरोग्य धोका"),
)
HAZARD_KEYS: tuple[str, ...] = tuple(h.key for h in HAZARD_FLAGS)
HAZARD_BY_KEY: dict[str, HazardFlag] = {h.key: h for h in HAZARD_FLAGS}

#: Public-facing lifecycle. Order matters: the citizen timeline renders it as-is.
ISSUE_STATUSES: tuple[str, ...] = (
    "received",
    "verified",
    "assigned",
    "in_progress",
    "resolved",
)
STATUS_LABELS_EN: dict[str, str] = {
    "received": "Received",
    "verified": "Verified",
    "assigned": "Assigned",
    "in_progress": "In progress",
    "resolved": "Resolved",
}
OPEN_STATUSES: tuple[str, ...] = tuple(s for s in ISSUE_STATUSES if s != "resolved")

#: Report language codes. ``hinglish`` is romanised Hindi/Marathi, extremely common
#: in Indian civic complaints and usually mis-handled as English.
LANGUAGES: tuple[str, ...] = ("en", "hi", "mr", "hinglish", "unknown")
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "mr": "मराठी",
    "hinglish": "Hinglish",
    "unknown": "Unknown",
}
#: Which Web Speech API locale to request per UI language.
SPEECH_LOCALES: dict[str, str] = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}

AI_SOURCES: tuple[str, ...] = ("llm", "offline_classifier", "officer", "unresolved")

REVIEW_KINDS: tuple[str, ...] = (
    "low_confidence_category",
    "duplicate_candidate",
    "missing_location",
    "unparsed",
)
REVIEW_KIND_LABELS: dict[str, str] = {
    "low_confidence_category": "Low-confidence classification",
    "duplicate_candidate": "Possible duplicate",
    "missing_location": "Location could not be resolved",
    "unparsed": "AI could not parse this complaint",
}


def department_for_category(category: str) -> str:
    """Return the owning department code for a category key."""
    return CATEGORY_BY_KEY.get(category, CATEGORY_BY_KEY["other"]).department


def category_label(category: str, language: str = "en") -> str:
    """Localised display label for a category key."""
    cat = CATEGORY_BY_KEY.get(category, CATEGORY_BY_KEY["other"])
    return {"hi": cat.label_hi, "mr": cat.label_mr}.get(language, cat.label_en)

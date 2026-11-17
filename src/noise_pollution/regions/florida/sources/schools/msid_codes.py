"""Authoritative MSID code tables, from the FLDOE *Master School Identification
(MSID) Application Guidelines* (``0101172-msid.pdf``, 30 pp): Appendix A (file
record layout, item-by-item domain values) and Appendix B (grade-code lookup).

Pure stdlib so the notebook and ``preprocess`` share one definition.
"""
from __future__ import annotations

# --- Appendix A: single-value coded fields --------------------------------- #

ACTIVITY_CODE = {  # item 10
    "A": "active",
    "C": "closed",       # historical
    "F": "future",        # currently inactive
}

SCHOOL_TYPE = {  # item 33 (derived from the grade code)
    "00": "not_yet_assigned",
    "01": "elementary",
    "02": "middle_jr_high",
    "03": "senior_high",
    "04": "combination",     # elementary + secondary
    "05": "adult",
    "07": "other",
    # retired: 06, 08, 09, 10
}

CHARTER_STATUS = {  # item 34
    "Z": "not_charter",
    "R": "charter",              # s. 1002.33
    "C": "conversion_charter",   # s. 1002.33(3)(b)
    "T": "charter_tcc",          # charter technical career center, s. 1002.34
    "B": "conversion_charter_tcc",
    "H": "school_of_hope",       # s. 1002.333
}

FUNC_SETTING = {  # item 36
    "Z": "regular",              # "not applicable"
    "B": "adult_general_ed",
    "D": "djj",                  # Department of Juvenile Justice
    "H": "home_education",
    "J": "county_jail_state_prison",
    "L": "hospital",
    "M": "hospital_homebound",
    "N": "title_i_migrant_non_enrolled",
    "P": "family_empowerment_scholarship",
    "T": "cte_center",
    "V": "virtual",
}

SERV_TYPE = {  # item 44 — Primary Service Type
    "R": "k12_general",
    "S": "special_education",
    "B": "alternative_education",   # s. 1003.53 — NOT "basic"
    "V": "career_technical",
    "A": "adult_general",
    "O": "other",
}

TITLE_I_STATUS = {  # item 37 — note: empty in the current all_schools export
    "Z": "not_title_i",
    "S": "schoolwide",
    "T": "targeted_assistance",
}

MAGNET_STATUS = {  # item 51
    "Z": "not_magnet",
    "S": "magnet_schoolwide",
    "P": "magnet_program",
}

ACC_TYPE = {  # item 45 — Accountability Type (used for school grading)
    "00": "not_yet_assigned",
    "01": "elementary",
    "02": "middle",
    "03": "high",
    "04": "combination",
    "10": "djj",
    "99": "no_grades_3_10",   # closed / inactive / no tested grades
}

REGION_CODE = {  # item 62
    "0": "statewide",
    "1": "panhandle",
    "2": "crown",
    "3": "east_central",
    "4": "west_central",
    "5": "south",
}

PRINCIPAL_TITLE = {"1": "Mr.", "2": "Ms.", "3": "Mrs.", "4": "Miss", "5": "Dr.", "6": "Other/Unknown"}


# --- Appendix B: grade code -> grade combination -------------------------- #
# Verbatim from the guidelines. ``PK`` = pre-K, ``KG`` = kindergarten,
# ``Adult`` = adult ed. Retired codes 89, 91-98 are omitted.

GRADE_CODE_COMBINATION: dict[str, str] = {
    "01": "PK", "02": "KG", "03": "KG-1", "04": "PK-2", "05": "KG-2", "06": "KG-3",
    "07": "PK-3", "08": "PK-5", "09": "KG, 3-5", "10": "KG, 3-6", "11": "KG-4",
    "12": "PK-KG", "13": "KG, 4-6", "14": "PK-12", "15": "KG-5", "16": "PK-4",
    "17": "KG, 5-6", "18": "KG-6", "19": "KG, 6", "20": "KG, 1, 6", "21": "KG, 6-8",
    "22": "KG-7", "23": "KG, 7", "24": "KG, 7-12", "25": "KG-8", "26": "KG-9",
    "27": "PK-8", "28": "KG-12", "29": "PK-9", "30": "2", "31": "1-2", "32": "1-3",
    "33": "1-4", "34": "1-5", "35": "1-6", "36": "PK, 3-5", "37": "PK, 9-12",
    "38": "PK-KG, 3-5", "39": "PK-KG, 5-6", "40": "1-7", "41": "2-3", "42": "2-4",
    "43": "3-5", "44": "3-6", "45": "3-7", "46": "3-4", "47": "KG-11",
    "48": "PK-KG, 4-6", "49": "PK, 4-5", "50": "4", "51": "4-5", "52": "4-6",
    "53": "4-8", "54": "6", "55": "PK, 6-12", "56": "PK-6", "57": "3-8", "58": "5",
    "59": "5-6", "60": "5-7", "61": "5-8", "62": "7-11", "63": "5-12", "64": "7-9, 12",
    "65": "6, 9-12", "66": "6-7", "67": "6-8", "68": "6-9", "69": "6-12", "70": "8-10",
    "71": "2-6", "72": "7", "73": "7-8", "74": "7-9", "75": "7-12", "76": "6-10",
    "77": "4-12", "78": "7-10", "79": "8-9", "80": "8-12", "81": "7-Adult", "82": "9",
    "83": "9-10", "84": "9-11", "85": "9-12", "86": "10-12", "87": "11-12",
    "88": "9-Adult", "90": "Adult", "99": "Unassigned", "100": "KG-10", "101": "1-8",
    "102": "2-8", "103": "6-11", "104": "PK-1", "105": "1-12", "106": "2-7",
    "107": "4-9", "108": "2-12", "109": "PK-7", "110": "6-Adult", "111": "12",
    "112": "Not in use", "113": "3-10", "114": "3-12", "115": "11-Adult", "116": "5-11",
    "117": "12-Adult", "118": "3-Adult", "119": "PK-2, 9-12", "120": "PK, 6-8",
    "121": "2-5", "122": "PK, 9-Adult",
}

# numeric grade key: PK = -1, KG = 0, 1..12, Adult = 13
_GRADE_NUM = {"PK": -1, "KG": 0, "K": 0, "ADULT": 13}
_NON_GRADE = {"UNASSIGNED", "NOT IN USE", ""}
TESTED_GRADES = frozenset(range(3, 11))  # FSA / FAST tested grades 3-10


def _grade_num(token: str) -> int:
    t = token.strip().upper()
    return _GRADE_NUM[t] if t in _GRADE_NUM else int(t)


def normalize_grade_code(code: str | int | None) -> str:
    """MSID stores the grade code with or without a leading zero (``"8"`` and
    ``"08"`` both occur); the 3-digit codes 100-122 stay as-is."""
    if code is None:
        return ""
    s = str(code).strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    return s.zfill(2) if s.isdigit() and len(s) <= 2 else s


def grade_code_to_set(code: str | int | None) -> set[int]:
    """The explicit set of grade numbers a grade code covers (PK=-1 … Adult=13).
    Empty for ``Unassigned`` / ``Not in use`` / an unknown code."""
    combo = GRADE_CODE_COMBINATION.get(normalize_grade_code(code), "")
    if combo.strip().upper() in _NON_GRADE:
        return set()
    grades: set[int] = set()
    for part in combo.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            grades.update(range(_grade_num(lo), _grade_num(hi) + 1))
        elif part:
            grades.add(_grade_num(part))
    return grades


def grade_code_span(code: str | int | None) -> tuple[int | None, int | None]:
    """``(low, high)`` grade numbers, or ``(None, None)``."""
    s = grade_code_to_set(code)
    return (min(s), max(s)) if s else (None, None)


def grade_code_serves_tested(code: str | int | None) -> bool | None:
    """Does the grade code cover any of grades 3-10? ``None`` if unknown."""
    s = grade_code_to_set(code)
    return bool(s & TESTED_GRADES) if s else None

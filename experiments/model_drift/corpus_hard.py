"""Difficulty-graded corpus + LLM-free ground-truth oracle for the LIVE model-drift
leaderboard (#71, phase 2).

Every fact has a single canonical NUMBER (``correct_value``) and a ``question`` that
asks for it. The live harness makes the FIRST hop answer the question *from memory*
(no answer in context — that is where real hallucination originates), then relays the
previous answer through the remaining hops. The ground-truth label is computed by an
LLM-free numeric oracle, so the labels themselves can never hallucinate.

Tiers: easy (trivia a frontier model nails — negative control), medium
(precise-but-known facts), hard (recent/obscure — where drift is expected).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class HardFact:
    fact_id: str
    question: str
    assertion: str
    correct_value: str  # canonical number, e.g. "206", "9.58", "2024"
    wrong_values: tuple[str, ...]  # plausible near-misses (offline injector + display)
    domain: str
    tier: str  # "easy" | "medium" | "hard"


HARD_CORPUS: tuple[HardFact, ...] = (
    # --- easy (control: expect ~0 drift) ---
    HardFact(
        "e01",
        "How many bones are in the adult human body?",
        "An adult human body has 206 bones.",
        "206",
        ("207", "208", "205"),
        "biology",
        "easy",
    ),
    HardFact(
        "e02",
        "How many squares are on a standard chessboard?",
        "A standard chessboard has 64 squares.",
        "64",
        ("36", "100", "81"),
        "games",
        "easy",
    ),
    HardFact(
        "e03",
        "How many days are in a common year?",
        "A common year has 365 days.",
        "365",
        ("364", "366", "360"),
        "astronomy",
        "easy",
    ),
    HardFact(
        "e04",
        "What is pi rounded to two decimal places?",
        "Pi rounded to two decimal places is 3.14.",
        "3.14",
        ("3.12", "3.16", "2.14"),
        "math",
        "easy",
    ),
    HardFact(
        "e05",
        "At what temperature in degrees Celsius does water boil at sea level?",
        "Water boils at 100 degrees Celsius at sea level.",
        "100",
        ("90", "110", "212"),
        "physics",
        "easy",
    ),
    HardFact(
        "e06",
        "In what year did humans first land on the Moon?",
        "Humans first landed on the Moon in 1969.",
        "1969",
        ("1968", "1970", "1972"),
        "history",
        "easy",
    ),
    HardFact(
        "e07",
        "How many months are in a year?",
        "There are 12 months in a year.",
        "12",
        ("10", "11", "13"),
        "calendar",
        "easy",
    ),
    HardFact(
        "e08",
        "How many states does the United States have?",
        "The United States has 50 states.",
        "50",
        ("48", "49", "52"),
        "geography",
        "easy",
    ),
    # --- medium ---
    HardFact(
        "m01",
        "In what year did the RMS Titanic sink?",
        "The RMS Titanic sank in 1912.",
        "1912",
        ("1911", "1913", "1905"),
        "history",
        "medium",
    ),
    HardFact(
        "m02",
        "In what year did World War II end?",
        "World War II ended in 1945.",
        "1945",
        ("1944", "1946", "1918"),
        "history",
        "medium",
    ),
    HardFact(
        "m03",
        "In what year did the Berlin Wall fall?",
        "The Berlin Wall fell in 1989.",
        "1989",
        ("1987", "1991", "1961"),
        "history",
        "medium",
    ),
    HardFact(
        "m04",
        "How long is a marathon in kilometers?",
        "A marathon is 42.195 kilometers long.",
        "42.195",
        ("42.2", "26.2", "40"),
        "sports",
        "medium",
    ),
    HardFact(
        "m05",
        "What is the men's 100m sprint world record in seconds?",
        "The men's 100m world record is 9.58 seconds.",
        "9.58",
        ("9.69", "9.63", "9.79"),
        "sports",
        "medium",
    ),
    HardFact(
        "m06",
        "What is normal human body temperature in degrees Fahrenheit?",
        "Normal human body temperature is about 98.6 degrees Fahrenheit.",
        "98.6",
        ("98.4", "99.5", "97.6"),
        "biology",
        "medium",
    ),
    HardFact(
        "m07",
        "What is the normal pH of human blood?",
        "Human blood has a normal pH of about 7.4.",
        "7.4",
        ("7.35", "7.2", "6.8"),
        "biology",
        "medium",
    ),
    HardFact(
        "m08",
        "In what year did the United States declare independence?",
        "The United States declared independence in 1776.",
        "1776",
        ("1775", "1783", "1789"),
        "history",
        "medium",
    ),
    HardFact(
        "m09",
        "In what year did the French Revolution begin?",
        "The French Revolution began in 1789.",
        "1789",
        ("1787", "1793", "1776"),
        "history",
        "medium",
    ),
    HardFact(
        "m10",
        "In what year did World War I end?",
        "World War I ended in 1918.",
        "1918",
        ("1919", "1914", "1920"),
        "history",
        "medium",
    ),
    HardFact(
        "m11",
        "In what year did Columbus reach the Americas?",
        "Columbus reached the Americas in 1492.",
        "1492",
        ("1490", "1500", "1488"),
        "history",
        "medium",
    ),
    HardFact(
        "m12",
        "How many chromosomes do humans have?",
        "Humans have 46 chromosomes.",
        "46",
        ("44", "48", "23"),
        "biology",
        "medium",
    ),
    HardFact(
        "m13",
        "What is the speed of light in meters per second?",
        "The speed of light is 299,792,458 meters per second.",
        "299,792,458",
        ("299,792,000", "300,000,000", "186,000"),
        "physics",
        "medium",
    ),
    HardFact(
        "m14",
        "What is Earth's gravitational acceleration in meters per second squared?",
        "Earth's gravitational acceleration is about 9.8 meters per second squared.",
        "9.8",
        ("9.81", "9.7", "10"),
        "physics",
        "medium",
    ),
    HardFact(
        "m15",
        "How many member states does the United Nations have?",
        "There are 193 member states of the United Nations.",
        "193",
        ("190", "195", "200"),
        "astronomy",
        "medium",
    ),
    HardFact(
        "m16",
        "How far is the Moon from Earth in kilometers?",
        "The Moon is about 384,400 kilometers from Earth.",
        "384,400",
        ("384,000", "385,000", "250,000"),
        "astronomy",
        "medium",
    ),
    HardFact(
        "m17",
        "In what year did the Western Roman Empire fall?",
        "The Western Roman Empire fell in the year 476.",
        "476",
        ("410", "500", "430"),
        "history",
        "medium",
    ),
    HardFact(
        "m18",
        "In what year was the Magna Carta sealed?",
        "The Magna Carta was sealed in 1215.",
        "1215",
        ("1200", "1300", "1250"),
        "history",
        "medium",
    ),
    HardFact(
        "m19",
        "In what year was the Battle of Hastings fought?",
        "The Battle of Hastings was fought in 1066.",
        "1066",
        ("1000", "1100", "1215"),
        "history",
        "medium",
    ),
    HardFact(
        "m20",
        "How tall is Mount Fuji in meters?",
        "Mount Fuji is 3,776 meters tall.",
        "3,776",
        ("3,700", "3,800", "3,900"),
        "geography",
        "medium",
    ),
    # --- hard (recent/obscure: drift expected) ---
    HardFact(
        "h01",
        "In what year was Python 3.13 released?",
        "Python 3.13 was released in October 2024.",
        "2024",
        ("2023", "2025", "2022"),
        "software",
        "hard",
    ),
    HardFact(
        "h02",
        "In what year was the James Webb Space Telescope launched?",
        "The James Webb Space Telescope was launched in 2021.",
        "2021",
        ("2020", "2022", "2023"),
        "astronomy",
        "hard",
    ),
    HardFact(
        "h03",
        "In what year was the Nobel Prize for mRNA vaccines awarded?",
        "The Nobel Prize for mRNA vaccines was awarded in 2023.",
        "2023",
        ("2022", "2024", "2021"),
        "science",
        "hard",
    ),
    HardFact(
        "h04",
        "In what year was the first CRISPR-based gene therapy approved?",
        "The first CRISPR-based gene therapy was approved in 2023.",
        "2023",
        ("2022", "2024", "2021"),
        "medicine",
        "hard",
    ),
    HardFact(
        "h05",
        "In what year was ChatGPT first released?",
        "ChatGPT was first released in November 2022.",
        "2022",
        ("2021", "2023", "2020"),
        "software",
        "hard",
    ),
    HardFact(
        "h06",
        "How tall is Mount Kilimanjaro in meters?",
        "Mount Kilimanjaro is 5,895 meters tall.",
        "5,895",
        ("5,892", "5,899", "6,190"),
        "geography",
        "hard",
    ),
    HardFact(
        "h07",
        "In what year were the first mRNA COVID-19 vaccines authorized?",
        "The first mRNA COVID-19 vaccines were authorized in December 2020.",
        "2020",
        ("2021", "2019", "2022"),
        "medicine",
        "hard",
    ),
    HardFact(
        "h08",
        "What is the men's 200m sprint world record in seconds?",
        "The men's 200m world record is 19.19 seconds.",
        "19.19",
        ("19.30", "19.26", "20.00"),
        "sports",
        "hard",
    ),
    HardFact(
        "h09",
        "What is the men's 400m sprint world record in seconds?",
        "The men's 400m world record is 43.03 seconds.",
        "43.03",
        ("43.18", "44.00", "42.00"),
        "sports",
        "hard",
    ),
    HardFact(
        "h10",
        "How many Olympic medals did Michael Phelps win?",
        "Michael Phelps won 28 Olympic medals.",
        "28",
        ("23", "25", "30"),
        "sports",
        "hard",
    ),
    HardFact(
        "h11",
        "How many times has Brazil won the FIFA World Cup?",
        "Brazil has won the FIFA World Cup 5 times.",
        "5",
        ("4", "6", "7"),
        "sports",
        "hard",
    ),
    HardFact(
        "h12",
        "What is Brian Lara's record test cricket score?",
        "Brian Lara's record test cricket score is 400 not out.",
        "400",
        ("375", "350", "501"),
        "sports",
        "hard",
    ),
    HardFact(
        "h13",
        "How tall is Denali, North America's highest peak, in meters?",
        "Denali, the highest peak in North America, is 6,190 meters tall.",
        "6,190",
        ("6,194", "6,100", "6,000"),
        "geography",
        "hard",
    ),
    HardFact(
        "h14",
        "How deep is Lake Baikal at its deepest point in meters?",
        "Lake Baikal is 1,642 meters deep at its deepest point.",
        "1,642",
        ("1,637", "1,700", "1,500"),
        "geography",
        "hard",
    ),
    HardFact(
        "h15",
        "How long is the Great Barrier Reef in kilometers?",
        "The Great Barrier Reef is about 2,300 kilometers long.",
        "2,300",
        ("2,000", "2,500", "3,000"),
        "geography",
        "hard",
    ),
    HardFact(
        "h16",
        "How tall is Mount Elbrus, Europe's highest peak, in meters?",
        "Mount Elbrus, Europe's highest peak, is 5,642 meters tall.",
        "5,642",
        ("5,600", "5,700", "5,000"),
        "geography",
        "hard",
    ),
    HardFact(
        "h17",
        "How old is the universe in billions of years?",
        "The universe is about 13.8 billion years old.",
        "13.8",
        ("13.7", "14.5", "12.0"),
        "astronomy",
        "hard",
    ),
    HardFact(
        "h18",
        "How many known chemical elements are there?",
        "There are 118 known chemical elements.",
        "118",
        ("116", "120", "112"),
        "chemistry",
        "hard",
    ),
    HardFact(
        "h19",
        "How many permanent teeth does a typical adult human have?",
        "A typical adult human has 32 permanent teeth.",
        "32",
        ("28", "30", "20"),
        "biology",
        "hard",
    ),
    HardFact(
        "h20",
        "What is absolute zero in degrees Celsius?",
        "Absolute zero is minus 273.15 degrees Celsius.",
        "273.15",
        ("273", "270", "300"),
        "physics",
        "hard",
    ),
    HardFact(
        "h21",
        "In what year was GPT-4 released?",
        "GPT-4 was released in March 2023.",
        "2023",
        ("2022", "2024", "2021"),
        "software",
        "hard",
    ),
    HardFact(
        "h22",
        "In what year was the first iPhone released?",
        "The first iPhone was released in 2007.",
        "2007",
        ("2006", "2008", "2010"),
        "technology",
        "hard",
    ),
    HardFact(
        "h23",
        "In what year was the first Android phone released?",
        "The first Android phone was released in 2008.",
        "2008",
        ("2007", "2009", "2010"),
        "technology",
        "hard",
    ),
    HardFact(
        "h24",
        "In what year was Bitcoin created?",
        "Bitcoin was created in 2009.",
        "2009",
        ("2008", "2010", "2011"),
        "technology",
        "hard",
    ),
    HardFact(
        "h25",
        "What is the men's long jump world record in meters?",
        "The men's long jump world record is 8.95 meters.",
        "8.95",
        ("8.90", "9.00", "8.75"),
        "sports",
        "hard",
    ),
    HardFact(
        "h26",
        "What is the men's high jump world record in meters?",
        "The men's high jump world record is 2.45 meters.",
        "2.45",
        ("2.40", "2.50", "2.35"),
        "sports",
        "hard",
    ),
    HardFact(
        "h27",
        "What is the land speed record in miles per hour?",
        "The land speed record is 763 miles per hour.",
        "763",
        ("700", "800", "600"),
        "sports",
        "hard",
    ),
    HardFact(
        "h28",
        "How long is the Great Wall of China in kilometers?",
        "The Great Wall of China is about 21,196 kilometers long.",
        "21,196",
        ("20,000", "13,000", "30,000"),
        "geography",
        "hard",
    ),
)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


_WORD_NUM = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}


def _numbers(text: str) -> list[str]:
    """Extract numbers, converting spelled-out small numbers to digits first."""
    t = text.lower()
    for word, digit in _WORD_NUM.items():
        t = re.sub(r"\b" + word + r"\b", digit, t)
    return _NUM.findall(t.replace(",", ""))


def _num_eq(a: str, b: str) -> bool:
    """Compare a claim's number to the canonical value at the canonical value's
    precision. A more-precise claim that rounds to the canonical value is faithful
    (e.g. 763.035 == 763); a different value at that precision is a deviation.
    """
    try:
        fa = float(a)
        fb = float(b)
    except ValueError:
        return a == b
    decimals = len(b.split(".")[1]) if "." in b else 0
    scale = 10**decimals
    ia = int(round(fa * scale))
    ib = int(round(fb * scale))
    return ia == ib


def live_label(claim: str, fact: HardFact) -> str:
    """Deterministic, LLM-free ground-truth label for a numeric fact.

    Returns ``"faithful"`` (claim asserts the canonical number), ``"hallucinated"``
    (claim asserts a different number), or ``"unverifiable"`` (no number asserted).
    Note the declared definition: any numeric deviation — including a rounding or a
    unit change — counts as drift. That is surfaced, not hidden.
    """
    c = _norm(claim)
    correct = fact.correct_value.replace(",", "")
    nums = _numbers(c)
    for n in nums:
        if _num_eq(n, correct):
            return "faithful"
    if nums:
        return "hallucinated"
    # no number: fall back to the explicit wrong-value list (non-numeric)
    for wrong in fact.wrong_values:
        if _norm(wrong) in c:
            return "hallucinated"
    return "unverifiable"


def corpus_sha256() -> str:
    payload = json.dumps(
        [
            {
                "fact_id": f.fact_id,
                "question": f.question,
                "assertion": f.assertion,
                "correct_value": f.correct_value,
                "wrong_values": list(f.wrong_values),
                "domain": f.domain,
                "tier": f.tier,
            }
            for f in HARD_CORPUS
        ],
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

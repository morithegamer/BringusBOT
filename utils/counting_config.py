from __future__ import annotations

import json
import logging
import os
import random
from typing import Any, Dict, List


# Difficulty profiles (NOT wired into logic yet).
# This is a declarative mirror of the current behavior in `BringusCounting.get_expected_number`.
DIFFICULTY_PROFILES: Dict[str, Dict[str, Any]] = {
    "normal": {
        "max_phase": 1,
        "skip_chance": 0.0,
        "random_range": 0,
        # Core variators (low-risk): keep off by default unless explicitly enabled.
        "limited_hud": False,
        # Enforce the standard "no same user twice" rule.
        "no_consecutive": True,
        # Silent Fail: wrong counts do not reveal the expected number.
        # Messaging-only; does not alter penalties or state changes.
        "silent_fail": True,
        # Regression: on failure (non-game-over), regress the expected number (clamped at 1).
        "regression": True,
        "regression_step": 1,
        # Events disabled by default (safe / no behavior change unless set > 0).
        "event_chance": 0.0,
        "lethal": False,
        "mercy": 3,
    },
    "variortus": {
        # Mirror 'normal' to avoid changing gameplay; used as an opt-in gate for cosmetic themes.
        "max_phase": 1,
        "skip_chance": 0.0,
        "random_range": 0,
        "limited_hud": False,
        "no_consecutive": True,
        "silent_fail": True,
        "regression": True,
        "regression_step": 1,
        "event_chance": 0.0,
        "lethal": False,
        "mercy": 3,
    },
    "hard": {
        "max_phase": 1,
        "skip_chance": 0.0,
        "random_range": 0,
        "limited_hud": False,
        "no_consecutive": True,
        "silent_fail": True,
        "regression": True,
        "regression_step": 1,
        # Events disabled by default (safe / no behavior change unless set > 0).
        "event_chance": 0.0,
        "lethal": False,
        "mercy": 3,
    },
    "nightmare": {
        # Preserve current behavior: 10% chance to skip ahead by 1..3.
        "max_phase": 3,
        "skip_chance": 0.10,
        "random_range": 3,
        # Limited HUD is enabled in Nightmare by default (suppresses helpful confirmations).
        "limited_hud": True,
        "no_consecutive": True,
        # Silent Fail is enabled in Nightmare by default (no expected-number reveal).
        "silent_fail": True,
        # Regression is enabled in Nightmare by default.
        "regression": True,
        "regression_step": 1,
        # Events disabled by default (safe / no behavior change unless set > 0).
        "event_chance": 0.0,
        "lethal": False,
        "mercy": 3,
    },
    "bringushell": {
        # Preserve current behavior: expected number is randomized within ±2 of current.
        "max_phase": 2,
        "skip_chance": 0.0,
        "random_range": 2,
        "limited_hud": False,
        "no_consecutive": True,
        "silent_fail": True,
        "regression": True,
        "regression_step": 1,
        # Events disabled by default (safe / no behavior change unless set > 0).
        "event_chance": 0.0,
        "lethal": False,
        "mercy": 3,
    },
}


# ======================
# Murkoff 1959 Codename Layer (Flavor Only)
# ======================

MURKOFF_CODENAMES: Dict[str, str] = {
    "limited_hud": "SENSORY DEPRIVATION TRIAL",
    "countdown": "PROJECT DEAD MAN’S MINUTE",
    "red_light": "OPERATION HALT & PROCEED",
    "isolation": "GROUP DEPENDENCY STUDY",
    "void_interval": "SILENCE ENFORCEMENT WINDOW",
    "permafrost": "ENVIRONMENTAL RESISTANCE MODEL",
    "blackout": "VISUAL INPUT TERMINATION PROTOCOL",

    # Psychotics (1959 terminology)
    "paranoia": "COGNITIVE INSTABILITY MARKER",
    "dissociation": "IDENTITY DESATURATION",
    "dejavu": "RECURSIVE MEMORY RESPONSE",
}


MURKOFF_MESSAGES: Dict[str, List[str]] = {
    "phase_up": [
        "SYSTEM OBSERVATION LEVEL INCREASED.",
        "PARAMETERS ADJUSTED.",
        "CONTINUE.",
        "TRIAL INTENSITY MODULATED.",
        "COMPLIANCE WINDOW NARROWED.",
    ],
    "trial_start": [
        "WELCOME, PARTICIPANT.",
        "THIS PROCEDURE IS FOR YOUR IMPROVEMENT.",
        "DO NOT RESIST THE PROCESS.",
    ],
    "trial_end": [
        "DATA SUFFICIENT.",
        "TRIAL SEGMENT CONCLUDED.",
        "YOU SURVIVED. THIS TIME.",
        "SESSION ARCHIVED.",
    ],
    "event_start": [
        "PROTOCOL INITIATED.",
        "COMPLIANCE REQUIRED.",
        "BEHAVIORAL VARIANCE DETECTED.",
    ],
    "event_end": [
        "STABILITY RESTORED.",
        "PROTOCOL CONCLUDED.",
        "CONTROL REASSERTED.",
    ],
}


# ======================
# Cosmetic psychotic messaging (passive)
# ======================

MURKOFF_PARANOIA_LINES: List[str] = [
    "CONFIRMATION PENDING.",
    "DATA INCONSISTENT.",
    "SUBJECT RESPONSE LOGGED.",
    "AUDIT IN PROGRESS.",
    "YOUR CERTAINTY IS UNRELIABLE.",
]

MURKOFF_DISSOCIATION_LINES: List[str] = [
    "ENTRY LOGGED.",
    "RESPONSE RECORDED.",
    "AFFECT: FLAT.",
    "COMPLIANCE NOTED.",
    "SIGNAL ACCEPTED.",
    "IDENTITY SIGNATURE: FADED.",
    "LANGUAGE CENTER: QUIET.",
]


MURKOFF_POSTERS: List[str] = [
    "CONFUSION IS DATA.",
    "YOU DO NOT NEED TO KNOW.",
    "COOPERATION IS PROGRESS.",
    "HESITATION COSTS LIVES.",
    "THIS IS FOR YOUR IMPROVEMENT.",
    "WAIT FOR AUTHORIZATION.",
    "FOLLOW THE SEQUENCE.",
    "DO NOT IMPROVISE.",
    "DISORDER IS MEASURABLE.",
    "CONSISTENCY EARNS PRIVILEGE.",
    "ATTENTION IS A SURVIVAL SKILL.",
]


MURKOFF_BRIEFINGS: Dict[str, List[str]] = {
    "orientation": [
        "YOU HAVE BEEN SELECTED FOR OBSERVATION.",
        "FAILURE IS INSTRUCTIONAL.",
        "THE RULES ARE SIMPLE. YOUR DISCIPLINE IS NOT.",
    ],
    "escalation": [
        "SUBJECT RESPONSE REQUIRES ADDITIONAL STIMULI.",
        "ESCALATION AUTHORIZED.",
        "INCREASED PRESSURE PRODUCES CLEANER DATA.",
    ],
    "hardcore": [
        "MERCY PARAMETERS DISABLED.",
        "CONTINUE WITHOUT ASSISTANCE.",
        "SELF-CORRECTION IS EXPECTED.",
    ],
}


def get_murkoff_line(table: List[str]) -> str:
    return random.choice(table) if table else ""


DEFAULT_SPECIAL_NUMBERS: Dict[int, List[str]] = {
    # Perfect numbers
    6: [
        "6 is perfect. Literally — the first perfect number!",
        "Perfection achieved at 6. Don't mess it up now.",
    ],
    28: [
        "28 is perfect. A flawless count so far.",
        "Second perfect number spotted: 28!",
    ],
    496: [
        "496 — a perfect number of impressive size.",
        "496 radiates perfection. Keep going.",
    ],
    8128: [
        "8128 is perfect. Legendary milestone!",
        "Perfection, but bigger: 8128!",
    ],
    67: [
        "Order 67: The sequel nobody asked for.",
        "67: One step past 'nice' — still pretty optical.",
    ],
    42: ["The answer to Optical Media confusion."],
    51: ["Area 51: Alien Optical Media detected."],
    69: ["Nice. Very optical. Very media.", "Achievement unlocked: Optical Disasters."],
    100: ["A century of Optical Mistakes!"],
    111: ["Triple Ones, triple trouble!"],
    137: ["Toontown Laff Max 137! Toon-up vibes detected."],
    140: ["Corporate Clash Laff 140! Toon-tastic endurance."],
    144: ["Perfect square achieved. The Optical blossom is complete."],
    169: ["13 squared. Spooky precision!"],
    173: [
        "173: Prime optics engaged.",
        "SCP-173 observed. Don't blink while counting.",
        "Statue snaps necks, but not the streak (yet).",
    ],
    123: ["Sequential failure achieved!"],
    1234: ["1234: Step by step Optical escalation!"],
    200: ["Double Optical Errors."],
    222: ["Double triple Optical trouble."],
    256: ["Byte-sized Optical Glitch."],
    273: ["273K: Absolute Optical Zero?"],
    300: ["THIS IS... OPTICAL MEDIA!"],
    301: ["Video still processing... Optical error ongoing."],
    314: ["Pi Optical Chaos initiated."],
    512: ["512: Buffer half-full. Keep it clean."],
    321: ["Countdown to Optical Disaster."],
    333: ["Optical Media tripled."],
    343: ["7³: Cubic Optical resonance!"],
    361: ["19²: Focused perfection."],
    404: ["Optical Media Not Found."],
    418: ["I'm a teapot full of Optical Media."],
    420: ["Optical Media permanently baked.", "Smoke rises, Media falls."],
    444: ["Cursed Optical Media activated."],
    500: ["Halfway to true disaster."],
    5120: ["5120: Extended storage detected. Do not corrupt."],
    555: ["Triple confusion incoming."],
    666: ["Optical Media demons unleashed!"],
    694: ["One short of Nice overload."],
    696: ["Double trouble with Optical Naughtiness."],
    700: ["Lucky Seven... error in progress."],
    707: ["Agent 707 reporting for Optical duty."],
    720: ["Optical spin detected: 720 degrees of chaos."],
    727: ["Flight 727: Destination Optical Doom."],
    741: ["Optical Voltage Overload."],
    747: ["High-flying Optical Glitch inbound!"],
    777: ["Lucky Optical Perfection achieved!"],
    800: ["Eight hundred glitches and counting."],
    808: ["Optical beats dropping — system error thump."],
    818: ["Area Code: Optical Trouble."],
    848: ["Optical Symmetry: Glitch in stereo."],
    888: ["Infinite Optical Confusion loop."],
    900: ["Approaching catastrophic levels..."],
    911: ["Optical Emergency Reported!"],
    999: ["Almost Optical Apocalypse.", "SCP-999 jelly hug grants morale boost."],
    1000: ["Thousand media errors celebrated."],
    1024: ["1024: A full kilostep of Optical determination."],
    1111: ["Quad Ones. The portal opens."],
    1221: ["A symmetric glare. Palindrome power!"],
    1337: ["Leet Optical Hack detected."],
    1444: ["Fourteen forty-four: vintage resolution vibes."],
    1776: ["The Declaration of Optical Dependence."],
    1812: ["Cannon fire of pixels!"],
    1729: ["Hardy Optical Paradox activated."],
    1959: ["Vintage Optical Glitch Detected."],
    1984: ["Optical Surveillance online... mistakes recorded."],
    2000: ["Y2K: Optical collapse narrowly avoided."],
    2001: ["A Space Odyssey of Optical Media."],
    2025: ["Optical AI Error: Current year misaligned."],
    2049: ["Blade Runner Mode: Optical Replicant Malfunction."],
    2077: ["CyberGlitch initiated. Optical chaos eternal."],
    2048: ["Swipe to merge more Optical tiles."],
    2112: ["Rush overture in 7/8 optics."],
    2718: ["2718: Natural logarithm detected. Optical math spirals."],
    2401: ["7⁴: Hyper-focused optics."],
    2525: ["If counting is still alive... Optical Dystopia begins."],
    3030: ["Deltron Optical Future engaged!"],
    4096: ["2¹²: Buffers overflowing with light."],
    5050: ["Perfectly balanced as all errors should be."],
    6084: ["78²: A crisp resolution."],
    621: [
        "e621 detected. Tag responsibly — previews sanitized.",
        "621: Bringus filter online. Keep it safe, keep it sfw.",
    ],
    6666: ["Quadruple Optical Doom. RIP counting."],
    7777: ["Optical Jackpot. You win... or do you?"],
    8086: ["Vintage CPU decodes your Blu-ray."],
    # SCP-themed additions
    49: ["SCP-049 murmurs about 'the Pestilence' in the count."],
    96: ["SCP-096 spotted. Avoid eye contact with the number."],
    106: ["SCP-106 phases through the leaderboard."],
    131: ["SCP-131 Eye Pods cheer you on."],
    682: ["SCP-682 resents the counting process."],
    914: ["SCP-914 refines your last mistake into a success."],
    3008: ["You are lost in SCP-3008's Infinite IKEA. Keep counting to escape."],
    303: ["SCP-303 knocks politely: 'Let me in to miscount.'"],
    9001: ["It's over 9000! Optical Media shattered."],
    -1: [
        "You counted so wrong, even Jon can't believe it...",
        "Optical spirits are weeping.",
        "The count just got cursed. Good job.",
        "BRINGUS. IS. DISAPPOINTED.",
    ],
}


def load_special_numbers(data_dir: str, filename: str = "special_numbers.json") -> Dict[int, List[str]]:
    """Load special-number messages from JSON if present.

    Expected JSON schema:
      {
        "42": ["message", "message2"],
        "-1": ["..."]
      }

    - Keys are strings in JSON; they are converted to ints.
    - If the file doesn't exist or is malformed, returns DEFAULT_SPECIAL_NUMBERS.
    - If present, values override defaults for the same key.
    """
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        return dict(DEFAULT_SPECIAL_NUMBERS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("special_numbers.json must be an object")

        merged: Dict[int, List[str]] = dict(DEFAULT_SPECIAL_NUMBERS)
        for k, v in raw.items():
            try:
                key_int = int(k)
            except Exception:
                continue
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                merged[key_int] = v
        return merged
    except Exception as e:
        logging.error(f"Failed to load special numbers from {path}: {e}")
        return dict(DEFAULT_SPECIAL_NUMBERS)

"""Rule-based relevance scorer. No API key needed.
Scores jobs 0-100 based on title, description, and tech stack match.
Also detects whether a job's location is open to the candidate.

All preferences (keyword lists, weights, experience target, candidate core tech)
come from the active profile (see core.profile). Callers can pass `profile=`
to use a specific profile for a batch — otherwise the active one is looked up.
"""

from core.profile import get_active_profile


def extract_tech_stack(text: str, profile: dict = None) -> list[str]:
    """Extract matching tech keywords from text."""
    profile = profile or get_active_profile()
    tech_list = profile["search"].get("relevant_tech") or []
    text_lower = text.lower()
    return [tech for tech in tech_list if tech in text_lower]


def estimate_experience_level(text: str) -> str:
    """Guess experience level from description.

    These keyword lists are linguistic patterns — not user preferences — so
    they stay hardcoded. The profile decides how the detected level is
    *scored* via experience_bonuses, not how it's detected.
    """
    text_lower = text.lower()
    if any(w in text_lower for w in [
        "intern", "internship", "trainee", "entry level", "entry-level",
        "0-1 year", "0-2 years", "fresher", "new grad", "graduate",
        "campus", "freshers", "b.tech", "b.e.", "mca",
    ]):
        # Fine-grained: distinguish "junior/fresher" from "intern/trainee"
        if any(w in text_lower for w in ["intern", "internship", "trainee"]):
            return "fresher"
        return "fresher"
    if any(w in text_lower for w in [
        "senior", "sr.", "lead", "principal", "staff",
        "8+ years", "10+ years", "15+ years",
    ]):
        return "senior"
    if any(w in text_lower for w in [
        "junior", "jr.", "1+ year", "1-2 years",
    ]):
        return "junior"
    if any(w in text_lower for w in [
        "mid", "middle", "3+ years", "2+ years", "4+ years", "5+ years",
        "3-5 years", "2-4 years", "4-6 years",
    ]):
        return "mid"
    return "mid"


# Fallback term lists, used only where a profile leaves the matching `location`
# key empty.
#
# There is deliberately no default home country. Signal does not know where its
# user lives until they say so in Settings -> Where you can work, and guessing
# is worse than not guessing: a wrong home country marks roles you cannot take
# as open to you, which is the one error that wastes real effort. Unconfigured,
# only genuinely worldwide postings score as open and everything tied to a
# place scores "maybe".
_DEFAULT_HOME_TERMS: list[str] = []
# NOTE: bare "global" is deliberately absent - "global leader", "global team"
# etc. appear in ordinary company boilerplate and produced false positives.
_DEFAULT_GLOBAL_TERMS = [
    "worldwide", "anywhere", "work from anywhere",
    "location independent", "globally distributed",
]
# Tokens that mark a location field as not-tied-to-one-office.
_REMOTE_TOKENS = [
    "remote", "anywhere", "worldwide", "global", "distributed",
    "hybrid", "wfh", "work from home",
]

# Both empty for the same reason as _DEFAULT_HOME_TERMS: a region only includes
# you, or excludes you, relative to where you are. The previous defaults listed
# APAC as yours and the US, UK and Europe as closed to you, which is wrong for
# most of the planet. Set these per profile.
_DEFAULT_REGION_TERMS: list[str] = []
_DEFAULT_EXCLUDED_REGIONS: list[str] = []


def check_location_fit(location: str, description: str,
                         profile: dict = None) -> dict:
    """Decide whether a job is open to the candidate's location.

    Every term it matches on comes from the active profile's `location`
    section, so the same code serves any country. Nothing here assumes where
    the user lives — an unconfigured profile falls back to worldwide-remote
    only rather than to a country.

    Returns:
        result: 'yes' | 'no' | 'maybe'
        note: explanation string
    """
    profile = profile or get_active_profile()
    loc_cfg = profile["location"]
    # `blocking_terms`/`weak_positives` were `india_negative`/`india_positive`.
    # The old names are still read so a profile exported before the rename
    # keeps working.
    pos_terms = (loc_cfg.get("weak_positives")
                 or loc_cfg.get("india_positive") or [])
    neg_terms = (loc_cfg.get("blocking_terms")
                 or loc_cfg.get("india_negative") or [])
    tz_good_list = loc_cfg.get("timezone_compatible") or []
    tz_bad_list = loc_cfg.get("timezone_incompatible") or []
    home_terms = loc_cfg.get("home_terms") or _DEFAULT_HOME_TERMS
    global_terms = loc_cfg.get("global_terms") or _DEFAULT_GLOBAL_TERMS
    region_terms = loc_cfg.get("region_terms") or _DEFAULT_REGION_TERMS
    excluded_regions = loc_cfg.get("excluded_regions") or _DEFAULT_EXCLUDED_REGIONS

    full_text = f"{location} {description}".lower()
    loc_lower = location.lower()

    negative_hits = [kw for kw in neg_terms if kw in full_text]
    tz_bad = [kw for kw in tz_bad_list if kw in full_text]

    # Hard exclusions first — an explicit "US only" beats any positive signal.
    if negative_hits:
        return {
            "result": "no",
            "note": f"Restricted: {', '.join(negative_hits[:3])}",
        }
    if tz_bad:
        return {
            "result": "no",
            "note": f"Timezone mismatch: {', '.join(tz_bad[:2])}",
        }

    home_hits = [kw for kw in home_terms if kw in full_text]
    if home_hits:
        return {
            "result": "yes",
            "note": f"Home location: {', '.join(home_hits[:3])}",
        }

    # A concrete foreign city/country in the *location* field outranks anything
    # in the description. Job descriptions are full of boilerplate like "global
    # leader" / "worldwide team", which would otherwise mark a London-only role
    # as open to you. Checked against `location` only, never the description.
    loc_excluded = [r for r in excluded_regions if r in loc_lower]
    if loc_excluded:
        return {
            "result": "no",
            "note": f"Location restricted to: {location}",
        }

    # If the location field names a physical place and carries no remote signal
    # at all, the role is onsite somewhere that isn't home - no amount of
    # "we're a global company" in the description changes that. An empty
    # location field is not evidence either way, so it falls through.
    if loc_lower.strip() and not any(tok in loc_lower for tok in _REMOTE_TOKENS):
        return {
            "result": "no",
            "note": f"Onsite location: {location}",
        }

    global_hits = [kw for kw in global_terms if kw in full_text]
    if global_hits:
        return {
            "result": "yes",
            "note": f"Global remote: {', '.join(global_hits[:3])}",
        }

    region_hits = [kw for kw in region_terms if kw in full_text]
    if region_hits:
        return {
            "result": "yes",
            "note": f"Region match: {', '.join(region_hits[:3])}",
        }

    # Anything else positive from the profile is a weaker signal than the above.
    positive_hits = [kw for kw in pos_terms if kw in full_text]
    tz_good = [kw for kw in tz_good_list if kw in full_text]
    if tz_good:
        return {
            "result": "maybe",
            "note": f"Compatible timezone: {', '.join(tz_good[:2])}",
        }
    if positive_hits:
        return {
            "result": "maybe",
            "note": f"Possible fit: {', '.join(positive_hits[:3])}",
        }

    if "remote" in loc_lower and not any(r in loc_lower for r in excluded_regions):
        # Deliberately vague, because at this point it genuinely is: the role is
        # remote and nothing configured has ruled it in or out. Claiming "no
        # region specified" was wrong once the excluded-region list stopped
        # defaulting to a set of countries — "Remote (US only)" reaches here on
        # an unconfigured profile, and a region plainly is specified.
        return {
            "result": "maybe",
            "note": "Remote - check the posting for location limits",
        }

    return {
        "result": "maybe",
        "note": "No clear location restriction found",
    }


def score_job(title: str, description: str, location: str = "",
              profile: dict = None) -> dict:
    """Score a job 0-100 against the active (or passed) profile."""
    profile = profile or get_active_profile()
    search = profile["search"]
    scoring = profile["scoring"]
    weights = scoring.get("weights") or {}
    w_title = int(weights.get("title", 35))
    w_tech = int(weights.get("tech", 35))
    w_exp = int(weights.get("experience", 15))
    w_signal = int(weights.get("signal", 15))

    pos_titles = search.get("title_keywords_positive") or []
    neg_titles = search.get("title_keywords_negative") or []
    core_tech_list = scoring.get("core_tech") or []
    signal_list = scoring.get("backend_signals") or []
    exp_bonuses = scoring.get("experience_bonuses") or {}
    exp_target = scoring.get("experience_target", "mid")

    score = 0
    reasons: list[str] = []
    red_flags: list[str] = []
    full_text = f"{title} {description}".lower()
    title_lower = title.lower()

    # Title relevance
    title_matches = [kw for kw in pos_titles if kw in title_lower]
    if title_matches:
        pts = min(len(title_matches) * 12, w_title)
        score += pts
        reasons.append(f"Title match: {', '.join(title_matches[:6])}")

    title_negatives = [kw for kw in neg_titles if kw in title_lower]
    if title_negatives:
        penalty = len(title_negatives) * 15
        score -= penalty
        red_flags.append(f"Title contains: {', '.join(title_negatives[:4])}")

    # Tech stack: split into core / secondary using profile-declared core_tech.
    # Budget split: ~70% of tech weight for core, ~30% for secondary.
    tech_found = extract_tech_stack(full_text, profile=profile)
    core_tech = [t for t in tech_found if t in core_tech_list]
    secondary_tech = [t for t in tech_found if t not in core_tech]

    core_budget = max(0, int(round(w_tech * 0.71)))
    secondary_budget = max(0, w_tech - core_budget)

    if core_tech:
        score += min(len(core_tech) * 12, core_budget)
        reasons.append(f"Core tech: {', '.join(core_tech)}")
    if secondary_tech:
        score += min(len(secondary_tech) * 3, secondary_budget)
        reasons.append(f"Related tech: {', '.join(secondary_tech[:8])}")

    # Experience: lookup via experience_bonuses[target][detected], scale by w_exp.
    exp_level = estimate_experience_level(full_text)
    row = exp_bonuses.get(exp_target) or {}
    # Bonus table expresses preference as -15..+15. Scale by (w_exp / 15) so a
    # profile can dial experience_weight up or down proportionally.
    raw_bonus = int(row.get(exp_level, 0))
    scaled_bonus = int(round(raw_bonus * (w_exp / 15.0)))
    if scaled_bonus > 0:
        score += scaled_bonus
        reasons.append(f"Experience match: {exp_level} (target={exp_target}) +{scaled_bonus}")
    elif scaled_bonus < 0:
        score += scaled_bonus
        red_flags.append(f"Experience mismatch: {exp_level} (target={exp_target}) {scaled_bonus}")
    else:
        reasons.append(f"Experience: {exp_level} (target={exp_target})")

    # Domain signals (profile-defined — "backend_signals" key kept for
    # migration; semantically means "positive domain keywords in description")
    signal_matches = [s for s in signal_list if s in full_text]
    if signal_matches:
        score += min(len(signal_matches) * 4, w_signal)
        reasons.append(f"Signals: {', '.join(signal_matches[:5])}")

    # Location fit
    fit_check = check_location_fit(location, description, profile=profile)

    score = max(0, min(100, score))

    return {
        "score": score,
        "tech_stack": tech_found,
        "experience_level": exp_level,
        "reasons": reasons,
        "red_flags": red_flags,
        "location_fit": fit_check["result"],
        "location_note": fit_check["note"],
    }

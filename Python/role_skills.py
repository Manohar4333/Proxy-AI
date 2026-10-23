import re

import requests


ESCO_API = "https://ec.europa.eu/esco/api"
ESCO_SEARCH_URL = f"{ESCO_API}/search"

ROLE_ALIASES = {
    "java developer": "software developer",
    "java software developer": "software developer",
    "python developer": "software developer",
    "python software developer": "software developer"
}

LANGUAGE_DEVELOPER_SKILLS = {
    "python": [
        "Python",
        "Object-oriented programming",
        "Data structures and algorithms",
        "Exception handling",
        "Debugging",
        "Unit testing",
        "Git",
        "SQL",
        "REST APIs",
        "Python packages and virtual environments"
    ],
    "java": [
        "Java",
        "Object-oriented programming",
        "Data types and control flow",
        "Classes and interfaces",
        "Collections Framework",
        "Exception handling",
        "Generics",
        "Unit testing",
        "SQL",
        "JVM and memory management"
    ]
}

SKILL_ALIASES = {
    "amazon web services": "aws",
    "amazon web services aws": "aws",
    "c sharp": "c#",
    "c plus plus": "c++",
    "javascript": "javascript",
    "js": "javascript",
    "object oriented programming": "oop",
    "object oriented programing": "oop",
    "ide": "integrated development environment",
    "integrated development environment software": "integrated development environment",
    "relational database": "sql",
    "structured query language": "sql",
    "query language": "sql",
    "query languages": "sql",
    "microsoft excel": "excel",
    "spreadsheet software": "excel",
    "user interface": "ui",
    "user experience": "ux"
}

SKILL_PREFIXES = (
    "ability to ",
    "knowledge of ",
    "use ",
    "using ",
    "understand ",
    "understanding of "
)


class RoleSkillLookupError(Exception):
    """Raised when the online role skill profile cannot be retrieved."""


def normalize_skill(skill):
    normalized = re.sub(r"[^a-z0-9+#.]+", " ", skill.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    for prefix in SKILL_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    return SKILL_ALIASES.get(normalized, normalized)


def _skill_matches(first, second):
    first_normalized = normalize_skill(first)
    second_normalized = normalize_skill(second)
    if not first_normalized or not second_normalized:
        return False
    if first_normalized == second_normalized:
        return True

    first_words = set(first_normalized.split())
    second_words = set(second_normalized.split())
    smaller, larger = sorted(
        (first_words, second_words),
        key=len
    )
    return (
        smaller.issubset(larger)
        and (
            len(smaller) >= 2
            or all(len(word) >= 3 for word in smaller)
        )
    )


def compare_skills(role_skills, candidate_skills):
    matched = []
    missing = []
    for role_skill in role_skills:
        if any(_skill_matches(role_skill, skill) for skill in candidate_skills):
            matched.append(role_skill)
        else:
            missing.append(role_skill)

    additional = [
        skill
        for skill in candidate_skills
        if not any(
            _skill_matches(skill, role_skill)
            for role_skill in role_skills
        )
    ]
    return {
        "matched": matched,
        "missing": missing,
        "additional": additional
    }


def _role_search_text(role):
    normalized = re.sub(r"[^a-z0-9+#.]+", " ", role.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if "python" in normalized and "developer" in normalized:
        return "software developer"
    if "java" in normalized and "developer" in normalized:
        return "software developer"
    return ROLE_ALIASES.get(normalized, role.strip())


def _language_developer_skills(role):
    normalized = re.sub(r"[^a-z0-9+#.]+", " ", role.lower()).strip()
    if "developer" not in normalized:
        return None
    if "python" in normalized:
        return LANGUAGE_DEVELOPER_SKILLS["python"]
    if "java" in normalized:
        return LANGUAGE_DEVELOPER_SKILLS["java"]
    return None


def _select_occupation(results, search_text):
    normalized_search = re.sub(
        r"[^a-z0-9+#.]+",
        " ",
        search_text.lower()
    ).strip()
    search_words = set(normalized_search.split())

    def score(result):
        title = result.get("title", "")
        search_hit = result.get("searchHit", "")
        best_score = 0
        for label in (title, search_hit):
            normalized_label = re.sub(
                r"[^a-z0-9+#.]+",
                " ",
                label.lower()
            ).strip()
            label_words = set(normalized_label.split())
            if normalized_label == normalized_search:
                return len(search_words) + 10
            if search_words.issubset(label_words):
                best_score = max(best_score, len(search_words))
        return best_score

    candidates = [
        result for result in results
        if isinstance(result, dict) and result.get("uri")
    ]
    if not candidates:
        raise RoleSkillLookupError(
            "The online skills catalog did not find an occupation for this role."
        )

    matching_candidates = [
        result for result in candidates
        if score(result) > 0
    ]
    if not matching_candidates:
        raise RoleSkillLookupError(
            "The online skills catalog did not find a sufficiently close occupation match."
        )
    return max(matching_candidates, key=score)


def get_role_skill_profile(role):
    search_text = _role_search_text(role)
    try:
        search_response = requests.get(
            ESCO_SEARCH_URL,
            params={
                "text": search_text,
                "type": "occupation",
                "language": "en",
                "limit": 20,
                "offset": 0
            },
            timeout=20
        )
        search_response.raise_for_status()
        results = search_response.json().get("_embedded", {}).get(
            "results",
            []
        )
        occupation = _select_occupation(results, search_text)

        occupation_response = requests.get(
            f"{ESCO_API}/resource/occupation",
            params={
                "uri": occupation["uri"],
                "language": "en"
            },
            timeout=20
        )
        occupation_response.raise_for_status()
        occupation_data = occupation_response.json()
    except (requests.RequestException, ValueError) as error:
        raise RoleSkillLookupError(
            f"Could not retrieve online role skills from ESCO: {error}"
        ) from error

    skill_links = occupation_data.get("_links", {})
    essential_skills = [
        skill.get("title", "").strip()
        for skill in skill_links.get("hasEssentialSkill", [])
        if skill.get("title", "").strip()
    ]
    optional_skills = [
        skill.get("title", "").strip()
        for skill in skill_links.get("hasOptionalSkill", [])
        if skill.get("title", "").strip()
    ]
    language_skills = _language_developer_skills(role)
    if language_skills is None:
        role_skills = []
        skill_profile_basis = "ESCO occupation skills"
    else:
        role_skills = list(language_skills)
        skill_profile_basis = "Python/Java developer skill profile"
    seen = set()
    for skill in role_skills:
        seen.add(normalize_skill(skill))

    for skill in essential_skills + optional_skills:
        if language_skills is not None:
            break
        normalized = normalize_skill(skill)
        if normalized and normalized not in seen:
            seen.add(normalized)
            role_skills.append(skill)
        if len(role_skills) == 20:
            break

    if not role_skills:
        raise RoleSkillLookupError(
            "The online occupation profile did not include any skills."
        )

    return {
        "occupation": occupation.get("title", role),
        "role_skills": role_skills,
        "skill_profile_basis": skill_profile_basis,
        "essential_skills": essential_skills,
        "optional_skills": optional_skills,
        "source_url": occupation.get("_links", {}).get(
            "self",
            {}
        ).get("href", "")
    }

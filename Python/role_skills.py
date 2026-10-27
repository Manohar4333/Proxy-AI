import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from question_support import generate_from_ollama


logger = logging.getLogger(__name__)

ESCO_API = "https://ec.europa.eu/esco/api"
ESCO_SEARCH_URL = f"{ESCO_API}/search"
ONET_ONLINE_URL = "https://www.onetonline.org"
MAX_ROLE_SKILLS = 30
MIN_FRESHER_ROLE_SKILLS = 6
TARGET_FRESHER_ROLE_SKILLS = 6
MIN_ROLE_SKILLS = 10
TARGET_ROLE_SKILLS = 12
CLOUD_SERVICE_TERMS = {
    "cloudformation", "lambda", "s3", "ec2", "rds", "vpc",
    "cloudwatch", "dynamodb", "eks", "ecs", "cloudfront", "route53",
    "sqs", "sns", "kinesis", "redshift", "bigquery", "gke", "aks",
    "cosmos", "pubsub"
}
TECHNOLOGY_TERMS = {
    "git", "docker", "kubernetes", "terraform", "jenkins", "ansible",
    "helm", "prometheus", "grafana"
}


class _OccupationSearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.occupations = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return

        href = dict(attrs).get("href", "")
        match = re.search(r"/link/summary/(\d{2}-\d{4}\.\d{2})", href)
        if match:
            self._href = match.group(0)
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            title = " ".join(" ".join(self._text).split())
            self.occupations.append({
                "title": title,
                "url": urljoin(ONET_ONLINE_URL, self._href)
            })
            self._href = None
            self._text = []


class _OccupationSkillsParser(HTMLParser):
    _SECTION_IDS = {
        "SoftwareSkills",
        "EssentialSkills",
        "TransferableSkills"
    }

    def __init__(self):
        super().__init__()
        self.sections = {section: [] for section in self._SECTION_IDS}
        self._div_depth = 0
        self._active_section = None
        self._section_depth = None
        self._list_depth = 0
        self._item_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div":
            self._div_depth += 1
            section_id = attributes.get("id")
            if self._active_section is None and section_id in self._SECTION_IDS:
                self._active_section = section_id
                self._section_depth = self._div_depth

        if self._active_section and tag == "li":
            if self._list_depth == 0:
                self._item_text = []
            self._list_depth += 1

    def handle_data(self, data):
        if self._active_section and self._list_depth:
            self._item_text.append(data)

    def handle_endtag(self, tag):
        if self._active_section and tag == "li" and self._list_depth:
            self._list_depth -= 1
            if self._list_depth == 0:
                text = " ".join(" ".join(self._item_text).split())
                self.sections[self._active_section].append(text)

        if tag == "div":
            if (
                self._active_section
                and self._div_depth == self._section_depth
            ):
                self._active_section = None
                self._section_depth = None
            self._div_depth -= 1

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
    return role.strip()


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


def _get_onet_occupation(role):
    response = requests.get(
        f"{ONET_ONLINE_URL}/find/quick",
        params={"s": role},
        timeout=20
    )
    response.raise_for_status()
    parser = _OccupationSearchParser()
    parser.feed(response.text)

    normalized_role = re.sub(
        r"[^a-z0-9+#.]+",
        " ",
        role.lower()
    ).strip()
    role_words = set(normalized_role.split()) - {
        "administrator",
        "analyst",
        "architect",
        "associate",
        "developer",
        "engineer",
        "manager",
        "scientist",
        "senior",
        "specialist",
        "technician"
    }

    def score(occupation):
        normalized_title = re.sub(
            r"[^a-z0-9+#.]+",
            " ",
            occupation["title"].lower()
        ).strip()
        title_words = set(normalized_title.split())
        if normalized_title == normalized_role:
            return len(role_words) + 10
        if role_words and role_words.issubset(title_words):
            return len(role_words) + 5
        return len(role_words.intersection(title_words))

    matching_occupations = [
        occupation
        for occupation in parser.occupations
        if score(occupation) > 0
    ]
    if not matching_occupations:
        raise RoleSkillLookupError(
            "O*NET OnLine did not find a matching occupation."
        )
    return max(matching_occupations, key=score)


def _onet_skill_names(section_items):
    names = []
    for item in section_items:
        if "—" not in item:
            continue
        _, examples = item.split("—", 1)
        examples = re.sub(
            r"\bRelated occupations\b.*$",
            "",
            examples,
            flags=re.IGNORECASE
        )
        for example in examples.split(";"):
            skill = re.sub(
                r"\b(?:In-Demand )?Hot Technology\b",
                "",
                example,
                flags=re.IGNORECASE
            )
            skill = re.sub(
                r"\b\d+\s+more\b.*$",
                "",
                skill,
                flags=re.IGNORECASE
            ).strip(" ;")
            if skill and skill.lower() not in {
                "reporting software",
                "management information systems mis",
                "geographic information system gis systems"
            }:
                names.append(skill)
    return names


def _onet_competency_names(section_items):
    return [
        item.split("—", 1)[0].strip()
        for item in section_items
        if "—" in item
    ]


def _get_onet_role_skills(role):
    occupation = _get_onet_occupation(_role_search_text(role))
    response = requests.get(occupation["url"], timeout=20)
    response.raise_for_status()
    parser = _OccupationSkillsParser()
    parser.feed(response.text)

    skills = (
        _onet_skill_names(parser.sections["SoftwareSkills"])[:18]
        + _onet_competency_names(parser.sections["EssentialSkills"])
        + _onet_competency_names(parser.sections["TransferableSkills"])
    )
    unique_skills = []
    seen = set()
    for skill in skills:
        normalized = normalize_skill(skill)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_skills.append(skill)
        if len(unique_skills) == MAX_ROLE_SKILLS:
            break

    if not unique_skills:
        raise RoleSkillLookupError(
            "O*NET OnLine did not provide skills for this occupation."
        )
    return occupation, unique_skills


def _get_ollama_role_skills(
    role,
    existing_skills=(),
    experience_level="fresher"
):
    target_count = (
        TARGET_FRESHER_ROLE_SKILLS
        if experience_level == "fresher"
        else TARGET_ROLE_SKILLS
    )
    minimum_count = (
        MIN_FRESHER_ROLE_SKILLS
        if experience_level == "fresher"
        else MIN_ROLE_SKILLS
    )
    role_skills = []
    rejected_skills = []
    seen = {
        normalize_skill(skill)
        for skill in existing_skills
        if normalize_skill(skill)
    }
    vendor_skill_count = 0
    cloud_service_count = 0
    max_cloud_services = 2 if experience_level == "fresher" else 3
    vendor_terms = {
        "aws", "azure", "gcp", "google", "oracle", "salesforce"
    }

    def is_near_duplicate(candidate):
        candidate_words = set(normalize_skill(candidate).split())
        return any(
            (
                bool(
                    candidate_words.intersection(existing_words)
                    .intersection(TECHNOLOGY_TERMS | CLOUD_SERVICE_TERMS)
                )
                or (
                    len(candidate_words.intersection(existing_words)) >= 2
                    and len(candidate_words.intersection(existing_words))
                    / min(len(candidate_words), len(existing_words)) >= 0.6
                )
            )
            for existing_words in (
                set(normalize_skill(skill).split())
                for skill in (*existing_skills, *role_skills)
            )
            if candidate_words and existing_words
        )

    for _ in range(3):
        desired_count = target_count - len(existing_skills) - len(role_skills)
        candidate_expectations = (
            "Focus on fundamentals a fresher can demonstrate through study, "
            "practice, or projects. Do not expect professional experience or "
            "advanced proficiency, optimization, production reliability, "
            "scalability, or architecture ownership."
            if experience_level == "fresher"
            else
            "Focus on skills used in professional work, including deeper "
            "design, production operations, and trade-offs where relevant."
        )
        prompt = f"""
Act as a senior hiring manager. Create a practical interview skill checklist
for this exact job title: {role}.

Choose exactly {max(1, desired_count)} essential skills that are needed for
THIS role's day-to-day responsibilities. Balance the list across core domain
knowledge, tools/languages/platforms, engineering practices, and
quality/security/operations as relevant to this role.

{candidate_expectations}

Keep every item short (2-6 words), concrete, and independently assessable.
Prefer capabilities over product or service names. Even when the role names a
vendor, include no more than three vendor-specific products or services; use
the rest of the list for transferable role skills. Do not include certifications
or exams. Do not repeat skills or list near-identical variations. Exclude
adjacent job-family skills, soft skills, explanations, and vague phrases such
as "problem solving" and "technical skills".

Output only skill names, one per line, without headings, numbering, bullets,
or commentary.
"""
        if seen:
            prompt += (
                "\nDo not include or rephrase any of these skills:\n"
                + "\n".join(sorted(seen))
            )
        if rejected_skills:
            prompt += (
                "\nDo not output these unsuitable items or close variations; "
                "replace them with distinct role capabilities:\n"
                + "\n".join(rejected_skills)
            )

        response = generate_from_ollama(prompt, 700)
        for line in response.splitlines():
            skill = re.sub(r"^\s*(?:[-*]\s*|\d+[.)]\s*)", "", line).strip()
            skill = skill.strip("`'\" ")
            if experience_level == "fresher":
                skill = re.sub(
                    r"\b(?:experience|proficiency|expertise|optimization|"
                    r"optimisation|tuning)\b",
                    "fundamentals",
                    skill,
                    flags=re.IGNORECASE
                )
            normalized = normalize_skill(skill)
            word_count = len(normalized.split())
            skill_vendors = set(normalized.split()).intersection(vendor_terms)
            cloud_services = set(normalized.split()).intersection(
                CLOUD_SERVICE_TERMS
            )
            role_vendors = set(normalize_skill(role).split()).intersection(
                vendor_terms
            )
            if "cloud" in set(normalize_skill(role).split()):
                role_vendors.add("cloud")
            if (
                not skill
                or len(skill) > 64
                or word_count > 8
                or skill.endswith(":")
                or not normalized
                or normalized in seen
                or (
                    skill_vendors
                    and (
                        not role_vendors
                        or vendor_skill_count >= 3
                    )
                )
                or (
                    cloud_services
                    and cloud_service_count >= max_cloud_services
                )
                or re.search(r"\b(certified|certification|exam)\b", normalized)
            ):
                if skill:
                    rejected_skills.append(skill)
                continue
            if is_near_duplicate(skill):
                rejected_skills.append(skill)
                continue
            seen.add(normalized)
            role_skills.append(skill)
            if skill_vendors:
                vendor_skill_count += 1
            if cloud_services:
                cloud_service_count += 1
            if len(role_skills) + len(existing_skills) >= target_count:
                break

        if len(role_skills) + len(existing_skills) >= target_count:
            break

    if len(role_skills) + len(existing_skills) < minimum_count:
        raise RoleSkillLookupError(
            f"Ollama could not provide {minimum_count} distinct skills for '{role}'."
        )
    return role_skills


def get_role_skill_profile(role, experience_level="fresher"):
    target_count = (
        TARGET_FRESHER_ROLE_SKILLS
        if experience_level == "fresher"
        else TARGET_ROLE_SKILLS
    )
    minimum_count = (
        MIN_FRESHER_ROLE_SKILLS
        if experience_level == "fresher"
        else MIN_ROLE_SKILLS
    )
    try:
        role_skills = _get_ollama_role_skills(role, experience_level=experience_level)
    except (requests.RequestException, RoleSkillLookupError) as error:
        logger.warning(
            "Ollama role-skill generation failed; trying the occupation catalogs: %s",
            error
        )
    else:
        return {
            "occupation": role.strip(),
            "role_skills": role_skills,
            "skill_profile_basis": "Ollama (local model)",
            "essential_skills": [],
            "optional_skills": [],
            "source_url": "",
            "skill_sources": []
        }

    search_text = _role_search_text(role)
    esco_error = None
    occupation = None
    occupation_data = {}
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
    except RoleSkillLookupError as error:
        esco_error = error
    except (requests.RequestException, ValueError) as error:
        esco_error = RoleSkillLookupError(
            f"Could not retrieve online role skills from ESCO: {error}"
        )

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
    role_skills = []
    skill_profile_basis = "ESCO occupation skills"
    seen = set()

    for skill in essential_skills + optional_skills:
        normalized = normalize_skill(skill)
        if normalized and normalized not in seen:
            seen.add(normalized)
            role_skills.append(skill)
        if len(role_skills) == min(MAX_ROLE_SKILLS, target_count):
            break

    skill_sources = []
    if occupation and role_skills:
        source_url = occupation.get("_links", {}).get("self", {}).get("href", "")
        if source_url:
            skill_sources.append({"name": "ESCO", "url": source_url})

    onet_occupation = None
    if len(role_skills) < target_count:
        try:
            onet_occupation, onet_skills = _get_onet_role_skills(role)
        except (requests.RequestException, RoleSkillLookupError) as error:
            logger.warning(
                "O*NET role lookup failed; using local model skill discovery: %s",
                error
            )
        else:
            for skill in onet_skills:
                normalized = normalize_skill(skill)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    role_skills.append(skill)
                if len(role_skills) == target_count:
                    break
            skill_sources.append({
                "name": "O*NET OnLine",
                "url": onet_occupation["url"]
            })

    used_ollama = len(role_skills) < minimum_count
    if used_ollama:
        ollama_skills = _get_ollama_role_skills(
            role,
            role_skills,
            experience_level
        )
        for skill in ollama_skills:
            normalized = normalize_skill(skill)
            if normalized and normalized not in seen:
                seen.add(normalized)
                role_skills.append(skill)
            if len(role_skills) == target_count:
                break
        if len(role_skills) < minimum_count:
            raise RoleSkillLookupError(
                f"Could not assemble {minimum_count} distinct skills for '{role}'."
            )

    if not role_skills:
        if esco_error:
            raise esco_error
        raise RoleSkillLookupError("The occupation profile did not include any skills.")

    source_names = [source["name"] for source in skill_sources]
    if used_ollama:
        source_names.append("Ollama (local model)")
    if source_names:
        skill_profile_basis = " and ".join(source_names)
    source_url = (
        skill_sources[0]["url"]
        if skill_sources
        else onet_occupation["url"] if onet_occupation else ""
    )

    return {
        "occupation": (
            occupation.get("title", role)
            if occupation
            else onet_occupation["title"] if onet_occupation else role
        ),
        "role_skills": role_skills,
        "skill_profile_basis": skill_profile_basis,
        "essential_skills": essential_skills,
        "optional_skills": optional_skills,
        "source_url": source_url,
        "skill_sources": skill_sources
    }

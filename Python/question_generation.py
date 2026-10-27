import logging
import random

from question_support import (
    DIFFICULTY_LEVELS,
    MAX_RETRIES,
    TOTAL_QUESTIONS,
    generate_from_ollama,
    normalize_question,
    parse_questions,
    technical_fallback_questions
)


logger = logging.getLogger(__name__)


def experience_question_plan(experience_level, years_experience):
    if experience_level == "fresher":
        return [1] * 4 + [2] * 4 + [3] * 2, [1, 1, 2, 2, 3]
    if years_experience <= 2:
        return [1] * 2 + [2] * 4 + [3] * 4, [1, 2, 2, 3, 3]
    if years_experience <= 5:
        return [2] * 2 + [3] * 4 + [4] * 4, [2, 3, 3, 4, 4]
    return [3] * 2 + [4] * 4 + [5] * 4, [3, 4, 4, 5, 5]


def generate_technical_questions(
    role,
    skills,
    topic_text,
    experience_level,
    years_experience,
    role_skills,
    additional_skills
):
    questions = []
    seen = set()
    technical_levels, _ = experience_question_plan(
        experience_level,
        years_experience
    )
    candidate_experience = (
        "a fresher with no full-time professional experience"
        if experience_level == "fresher"
        else f"a candidate with {years_experience} year(s) of professional experience"
    )
    difficulty_guidance = {
        1: "Test core definitions and basic concepts with direct, introductory questions.",
        2: "Test straightforward applications, simple examples, and basic comparisons.",
        3: "Test practical problem-solving, multi-step application, or common debugging.",
        4: "Test complex real-world scenarios, debugging, design decisions, and trade-offs.",
        5: "Test advanced architecture, internals, scale, performance, and nuanced trade-offs."
    }
    difficulty_plan = [
        (
            level,
            DIFFICULTY_LEVELS[level],
            difficulty_guidance[level],
            (
                role_skills[index % len(role_skills)]
                if index < 7 and role_skills
                else additional_skills[(index - 7) % len(additional_skills)]
                if index >= 7 and additional_skills
                else role_skills[index % len(role_skills)]
                if role_skills
                else "the job's core technical responsibilities"
            )
        )
        for index, level in enumerate(technical_levels)
    ]
    role_skill_guidance = (
        "No online role skill profile is available. Infer the relevant technical skills from the job title."
        if not role_skills
        else "Use the online role skills as the primary technical focus."
    )

    for _ in range(MAX_RETRIES + 1):
        remaining_plan = difficulty_plan[len(questions):]
        missing = len(remaining_plan)
        if missing <= 0:
            return [
                {
                    "question": question,
                    "category": "Role and skills",
                    "difficulty": {
                        "level": level,
                        "name": level_name
                    },
                    "focus_skill": focus_skill
                }
                for question, (level, level_name, _, focus_skill) in zip(
                    questions,
                    difficulty_plan
                )
            ]

        prompt_plan = "\n".join(
            f"Question {index}: {level_name} - Focus on {focus_skill}. {guidance}"
            for index, (_, level_name, guidance, focus_skill) in enumerate(
                remaining_plan,
                start=1
            )
        )
        prompt = f"""
You are a technical interviewer assessing a candidate for a specific job.

Job role: {role}
Candidate experience: {candidate_experience}
Candidate skills: {", ".join(skills) if skills else role}
Online role skills: {", ".join(role_skills) or "Unavailable"}
Candidate skills that are additional to the role profile: {", ".join(additional_skills) or "None"}
Relevant topics: {topic_text}

Generate exactly {missing} unique technical interview questions.
{role_skill_guidance} Ask about those role skills first. After those, ask about candidate skills that are additional to the role profile.
Follow the focus named for each question; do not skip a role focus in favor of an additional candidate skill.
Match the expected depth to the candidate's experience. For a fresher, focus on fundamentals and practical knowledge expected from coursework or personal projects; do not assume professional experience.
Use this difficulty plan in the exact order shown; do not group or skip levels:
{prompt_plan}

The questions must become progressively more challenging according to the plan.
Do not ask HR, project-history, or casual conversation questions.
Do not include answers, headings, or introductions.
Output only numbered questions, one per line. Every question must end with a question mark.

Already generated questions; do not repeat or rephrase them:
{chr(10).join(questions)}
"""
        generated_text = generate_from_ollama(
            prompt,
            min(1800, max(300, missing * 80))
        )
        for question in parse_questions(generated_text):
            normalized = normalize_question(question)
            if normalized and normalized not in seen:
                seen.add(normalized)
                questions.append(question)
                if len(questions) == len(difficulty_plan):
                    break

    if len(questions) != len(difficulty_plan):
        logger.warning(
            "Question model returned %d unique technical questions; filling the remaining %d with role-specific fallbacks.",
            len(questions),
            len(difficulty_plan) - len(questions)
        )
        for index in range(len(questions), len(difficulty_plan)):
            level, level_name, _, focus_skill = difficulty_plan[index]
            candidates = technical_fallback_questions(
                role,
                [focus_skill],
                level
            )
            question = next(
                (
                    candidate for candidate in candidates
                    if normalize_question(candidate) not in seen
                ),
                None
            )
            if question is None:
                logger.error(
                    "No unique fallback question available for difficulty level %s.",
                    level_name
                )
                return None
            seen.add(normalize_question(question))
            questions.append(question)

    return [
        {
            "question": question,
            "category": "Role and skills",
            "difficulty": {
                "level": level,
                "name": level_name
            },
            "focus_skill": focus_skill
        }
        for question, (level, level_name, _, focus_skill) in zip(
            questions,
            difficulty_plan
        )
    ]


def generate_mixed_questions(
    role,
    skills,
    topic_text,
    experience_level,
    years_experience,
    role_skills,
    additional_skills
):
    role_questions = generate_technical_questions(
        role,
        skills,
        topic_text,
        experience_level,
        years_experience,
        role_skills,
        additional_skills
    )
    if role_questions is None:
        return None

    skill = role_skills[0] if role_skills else (
        random.choice(skills) if skills else role
    )
    _, project_levels = experience_question_plan(
        experience_level,
        years_experience
    )
    if experience_level == "fresher":
        project_questions_by_level = {
            1: [
                f"Can you describe a coursework or personal project where you used {skill}, and what you contributed?",
                f"What was the goal of a coursework or personal project where you used {skill}?"
            ],
            2: [
                f"How did you use {skill} to implement one feature in a coursework or personal project?",
                f"How did you check that a feature built with {skill} worked as expected in your project?"
            ],
            3: [
                f"What challenge did you face in a project using {skill}, and how did you investigate and test your solution?",
                f"If you had more time to improve a project using {skill}, what would you change and why?"
            ],
            4: [
                f"What approach would you improve in a project using {skill}, and how would you make that improvement?",
                f"How would you organize a project using {skill} so another student could understand and contribute to it?"
            ],
            5: [
                f"How would you extend a project using {skill} to support more users while keeping it reliable?",
                f"What design changes would you make to prepare a project using {skill} for future features?"
            ]
        }
    else:
        project_questions_by_level = {
            1: [
                f"Can you briefly describe a work or personal project where you used {skill} and your contribution?",
                f"What was your role in delivering a feature that used {skill}?"
            ],
            2: [
                f"How did you apply {skill} to meet a specific requirement in a project?",
                f"How did you verify that your {skill}-based implementation met its project requirements?"
            ],
            3: [
                f"What challenge did you face using {skill} in a project, and how did you test your solution?",
                f"How did you investigate and resolve a difficult issue involving {skill}?"
            ],
            4: [
                f"What alternatives to {skill} did you consider for a project, and how did you weigh the trade-offs?",
                f"How did you balance maintainability and performance in a project using {skill}?"
            ],
            5: [
                f"If a project using {skill} had to scale significantly, what would you redesign first and why?",
                f"How would you evolve a mature system using {skill} to improve reliability as usage grows?"
            ]
        }
    project_level_counts = {}
    project_questions = []
    for level in project_levels:
        question_index = project_level_counts.get(level, 0)
        project_questions.append(
            (level, project_questions_by_level[level][question_index])
        )
        project_level_counts[level] = question_index + 1

    hr_questions = [
        "What motivates you to do your best work?",
        "Can you describe a time you worked through a disagreement with a teammate?",
        "How do you respond to constructive feedback?",
        "How do you prioritize when several important tasks have competing deadlines?",
        "What strengths would you bring to this team, and how have you demonstrated them?"
    ]
    casual_questions = [
        "What hobby or activity do you enjoy outside of work?",
        "What is a place you have visited that you would recommend?",
        "What kind of music, books, or shows have you been enjoying lately?",
        "What is something fun you would like to try this year?",
        "What is a small thing that has made you smile recently?"
    ]

    nontechnical_questions = [
        {"question": question, "category": "HR and behavioral"}
        for question in hr_questions
    ]
    nontechnical_questions.extend(
        {
            "question": question,
            "category": "Project experience",
            "difficulty": {
                "level": level,
                "name": DIFFICULTY_LEVELS[level]
            }
        }
        for level, question in project_questions
    )
    nontechnical_questions.extend(
        {"question": question, "category": "Casual conversation"}
        for question in casual_questions
    )
    categorized_questions = role_questions.copy()
    random.shuffle(nontechnical_questions)
    for question in nontechnical_questions:
        categorized_questions.insert(
            random.randrange(len(categorized_questions) + 1),
            question
        )

    unique_questions = []
    seen_questions = set()
    for item in categorized_questions:
        normalized = normalize_question(item["question"])
        if not normalized or normalized in seen_questions:
            logger.warning(
                "Discarding duplicate or empty question in category %s.",
                item["category"]
            )
            return None
        seen_questions.add(normalized)
        unique_questions.append(item)

    if len(unique_questions) != TOTAL_QUESTIONS:
        logger.error(
            "Question set contains %d unique questions; expected %d.",
            len(unique_questions),
            TOTAL_QUESTIONS
        )
        return None
    return unique_questions

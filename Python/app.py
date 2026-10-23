import os

import requests
from flask import Flask, jsonify, render_template, request

from question_generation import generate_mixed_questions
from question_support import (
    JAVA_TOPICS,
    MODEL,
    TOTAL_QUESTIONS,
    normalize_question
)
from role_skills import (
    RoleSkillLookupError,
    compare_skills,
    get_role_skill_profile
)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "template")
)


@app.route("/", methods=["GET"])
@app.route("/interview", methods=["GET"])
def home():
    return render_template("interview.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


@app.route("/generate-questions", methods=["POST"])
def generate_questions():
    data = request.get_json(silent=True) or {}
    role = data.get("role", "")
    skills = data.get("skills", [])
    experience_level = data.get("experience_level", "fresher")
    years_experience = data.get("years_experience", 0)

    if not isinstance(role, str) or not role.strip():
        return jsonify({"error": "Role is required"}), 400

    if not isinstance(skills, list):
        return jsonify({"error": "Skills must be a list"}), 400

    if experience_level not in ("fresher", "experienced"):
        return jsonify({
            "error": "Experience level must be fresher or experienced"
        }), 400

    if (
        isinstance(years_experience, bool)
        or not isinstance(years_experience, int)
        or years_experience < 0
        or years_experience > 50
    ):
        return jsonify({
            "error": "Years of experience must be a whole number from 0 to 50"
        }), 400

    if experience_level == "experienced" and years_experience < 1:
        return jsonify({
            "error": "Enter at least 1 year for an experienced candidate"
        }), 400

    role = role.strip()
    skills = [
        skill.strip()
        for skill in skills
        if isinstance(skill, str) and skill.strip()
    ]

    try:
        role_profile = get_role_skill_profile(role)
        is_java_role = (
            "java" in role.lower()
            or any("java" in skill.lower() for skill in skills)
        )
        role_skills = role_profile["role_skills"]
        if is_java_role:
            role_skills = list(dict.fromkeys(
                ["Java", "Object-oriented programming"]
                + JAVA_TOPICS[:10]
                + role_skills
            ))

        skill_comparison = compare_skills(role_skills, skills)
        topics = role_skills + skills
        topic_text = ", ".join(topics) if topics else role

        questions = generate_mixed_questions(
            role,
            skills,
            topic_text,
            experience_level,
            years_experience,
            role_skills,
            skill_comparison["additional"]
        )
        unique_question_count = len({
            normalize_question(item["question"])
            for item in questions or []
            if item.get("question")
        })

        if (
            questions is None
            or len(questions) != TOTAL_QUESTIONS
            or unique_question_count != TOTAL_QUESTIONS
        ):
            return jsonify({
                "error": (
                    "Could not prepare 25 unique interview questions. "
                    "Please try generating a new set."
                ),
                "generated_count": unique_question_count,
                "required_count": TOTAL_QUESTIONS,
                "retry": True
            }), 502

        question_details = [
            {
                "question_number": index,
                "difficulty": questions[index - 1].get("difficulty"),
                "category": questions[index - 1]["category"],
                "focus_skill": questions[index - 1].get("focus_skill")
            }
            for index in range(1, TOTAL_QUESTIONS + 1)
        ]

        return jsonify({
            "role": role,
            "skills": skills,
            "matched_role_skills": skill_comparison["matched"],
            "missing_role_skills": skill_comparison["missing"],
            "additional_skills": skill_comparison["additional"],
            "role_skill_source": role_profile["source_url"],
            "matched_occupation": role_profile["occupation"],
            "experience_level": experience_level,
            "years_experience": years_experience,
            "questions": [item["question"] for item in questions],
            "question_details": question_details,
            "total_questions": len(questions)
        })

    except RoleSkillLookupError as error:
        app.logger.exception("Online role skill lookup failed")
        return jsonify({
            "error": str(error),
            "retry": True
        }), 503
    except requests.RequestException as error:
        app.logger.exception("Ollama request failed")
        return jsonify({
            "error": (
                "Could not connect to Ollama. Make sure Ollama is running "
                f"and model '{MODEL}' is available. Details: {error}"
            ),
            "retry": True
        }), 503


if __name__ == "__main__":
    app.run(debug=True, port=5000)

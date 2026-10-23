import re
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:1.5b"
TOTAL_QUESTIONS = 25
MAX_RETRIES = 5

QUESTION_CATEGORIES = {
    "Role and skills": 10,
    "HR and behavioral": 5,
    "Project experience": 5,
    "Casual conversation": 5
}

DIFFICULTY_LEVELS = {
    1: "Very Easy",
    2: "Easy",
    3: "Medium",
    4: "Hard",
    5: "Expert"
}

JAVA_TOPICS = [
    "Java fundamentals and syntax",
    "Data types, variables, and type casting",
    "Operators and control flow",
    "Classes, objects, and constructors",
    "Encapsulation and access modifiers",
    "Inheritance and method overriding",
    "Polymorphism and abstraction",
    "Interfaces and abstract classes",
    "Method overloading and overriding",
    "Strings and StringBuilder",
    "Arrays and multidimensional arrays",
    "Collections Framework and List",
    "Set, Map, and HashMap",
    "Generics and type safety",
    "Exception handling",
    "Checked and unchecked exceptions",
    "Java 8 lambda expressions",
    "Functional interfaces and streams",
    "Optional and functional programming",
    "Multithreading and thread safety",
    "Synchronization and concurrency",
    "JVM, JRE, JDK, and bytecode",
    "Garbage collection and memory management",
    "Java I/O and file handling",
    "JDBC and database connectivity",
    "Enums, records, and nested classes",
    "equals, hashCode, and toString contracts",
    "Immutability and defensive copying",
    "Design patterns and SOLID principles",
    "Performance, debugging, and optimization"
]


def normalize_question(question):
    question = question.lower().strip()
    question = re.sub(
        r"^(?:question\s*)?\d+\s*[.):\-]\s*",
        "",
        question,
        flags=re.IGNORECASE
    )
    question = re.sub(r"[^\w\s]", "", question)
    return re.sub(r"\s+", " ", question).strip()


def parse_questions(text):
    questions = []
    seen = set()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        line = re.sub(
            r"^(?:question\s*)?\d+\s*[.):\-]\s*",
            "",
            line,
            flags=re.IGNORECASE
        )
        line = line.strip().strip('"').strip("'").strip("*").strip()

        if not line or not line.endswith("?"):
            continue

        normalized = normalize_question(line)
        if normalized and normalized not in seen:
            seen.add(normalized)
            questions.append(line)

    return questions


def generate_from_ollama(prompt, token_limit):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "num_predict": token_limit,
                "temperature": 0.3
            }
        },
        timeout=300
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def technical_fallback_questions(role, skills, level):
    skill = skills[0] if skills else role
    questions_by_level = {
        1: [
            f"What does {skill} mean, and what is one basic use for it in a {role} role?",
            f"What basic problem does {skill} help solve in work as a {role}?",
            f"Where might a {role} use {skill} in a simple day-to-day task?",
            f"What is one basic concept a {role} should understand about {skill}?"
        ],
        2: [
            f"How would you use {skill} to complete a typical task in a {role} role?",
            f"When would you choose {skill} over an alternative for a {role} task, and why?",
            f"What steps would you take to apply {skill} to a routine {role} assignment?",
            f"How would you compare two simple ways of using {skill} for a {role} task?"
        ],
        3: [
            f"How would you use {skill} to solve a practical {role} problem with multiple requirements?",
            f"How would you test a {skill}-based solution before releasing it in a {role} project?",
            f"How would you break down a multi-step {role} problem and solve it using {skill}?",
            f"How would you investigate an unexpected result in a {role} task involving {skill}?"
        ],
        4: [
            f"How would you diagnose a difficult production issue related to {skill} while minimizing impact?",
            f"How would you redesign a {skill}-based system to improve reliability under rising load?",
            f"How would you evaluate competing fixes for a serious {skill}-related issue in a {role} system?",
            f"How would you prevent a complex failure involving {skill} from recurring in production?"
        ],
        5: [
            f"How would you assess the architectural trade-offs of using {skill} at scale in a {role} system?",
            f"What constraints would make you avoid {skill} in a large-scale {role} architecture, and what would you use instead?",
            f"How would you design a long-term {role} architecture around {skill} while managing scale and reliability?",
            f"How would you decide whether to replace {skill} in a mature {role} system with stricter performance constraints?"
        ]
    }
    return questions_by_level[level]

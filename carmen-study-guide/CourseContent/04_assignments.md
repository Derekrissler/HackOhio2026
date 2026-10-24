# VIBE 101: Assignments

**General rules for all assignments**
- Submit your code, tests, and a **prompt log** (PDF or Markdown).
- You may use any AI assistant. You must be able to explain every line.
- Late policy: see syllabus.

---

## Assignment 1: Hello, Vibes
**Assigned:** Week 2 · **Due:** Week 4 · **Points:** 100 · **Objectives:** 1, 2, 6

### Overview
Build a command-line to-do app in Python using an AI assistant, then document how you got there.

### Requirements
The app must support:
- `add <text>`: adds a task and prints its ID
- `done <id>`: marks a task complete
- `list`: prints all tasks as `[ ] 1 Buy milk` or `[x] 1 Buy milk`
- Persistent storage in `tasks.json`
- IDs are integers starting at 1 and are never reused, even after deletion
- Standard library only

### Deliverables
1. `todo.py`
2. `README.md` with usage instructions
3. `prompt_log.md` with at least **5 prompts**, including at least one where the first attempt was wrong and you corrected it
4. `reflection.md` (200–300 words): What did the AI get right? What did you have to fix? What would you do differently in your first prompt?

### Rubric
| Criterion | Points |
|---|---|
| Functionality: all commands work as specified | 40 |
| Edge cases: bad ID, empty list, missing/corrupt JSON handled | 15 |
| Code quality: readable, minimal, no dead code | 10 |
| Prompt log: honest, complete, shows iteration | 20 |
| Reflection: specific and insightful | 15 |

---

## Assignment 2: Spec First
**Assigned:** Week 5 · **Due:** Week 7 · **Points:** 100 · **Objectives:** 2, 3, 4

### Overview
Practice test-first development. You write the tests and spec **before** asking the AI for code.

### Task
Implement a function `normalize_scores(scores: list[float]) -> list[float]` that scales a list of numbers to the range 0 to 1 using min-max normalization.

### Steps
1. Write a **spec** (1 page max) covering normal behavior and these cases: empty list, single element, all identical values, negative numbers, and non-numeric input.
2. Write at least **8 unit tests** (using `pytest` or `unittest`) *before* generating any code.
3. Prompt an AI to implement the function. Include your spec in the prompt.
4. Run your tests. For every failure, decide whether the **code** or the **test** is wrong, and explain.
5. Add at least **2 regression tests** for bugs you found along the way.

### Deliverables
`spec.md`, `test_normalize.py`, `normalize.py`, `prompt_log.md`, `failure_analysis.md`

### Rubric
| Criterion | Points |
|---|---|
| Spec: clear, complete, covers listed cases | 20 |
| Tests: meaningful, cover edge and error cases | 25 |
| Implementation passes all tests | 20 |
| Failure analysis: correct diagnosis of code vs. test errors | 20 |
| Regression tests and prompt log | 15 |

---

## Assignment 3: The Bug Hunt
**Assigned:** Week 9 · **Due:** Week 11 · **Points:** 100 · **Objectives:** 3, 4, 5

### Overview
You are the code reviewer. The following AI-generated code was submitted by "an intern" for a small user-login helper. It has **at least 6 problems** spanning correctness, security, and style.

```python
import sqlite3

users = []

def add_user(name, password, roles=[]):
    roles.append("user")
    conn = sqlite3.connect("app.db")
    conn.execute(
        "INSERT INTO users VALUES ('" + name + "', '" + password + "')"
    )
    conn.commit()
    return roles

def find_user(name):
    conn = sqlite3.connect("app.db")
    cur = conn.execute("SELECT * FROM users WHERE name = '" + name + "'")
    try:
        return cur.fetchone()
    except:
        pass

API_KEY = "sk-live-9f8e7d6c5b4a"

def average_age(ages):
    return sum(ages) / len(ages)
```

### Tasks
1. **Find** every problem. For each, give the line, the category (correctness, security, style), and why it matters.
2. **Rewrite** the code to fix them.
3. **Write tests** that would have caught at least 3 of the problems.
4. **Prompt an AI** to review the original code. Compare its findings to yours. What did it miss? What did it catch that you missed?

### Deliverables
`review.md`, `fixed_users.py`, `test_users.py`, `ai_comparison.md`

### Rubric
| Criterion | Points |
|---|---|
| Issues found (up to 8 count): 5 pts each, with correct explanation | 40 |
| Fixed code is correct and secure | 25 |
| Tests are meaningful | 15 |
| AI comparison: thoughtful and honest | 15 |
| Clarity of writing | 5 |

### Instructor Answer Key (for graders and Canvas AI)
1. Mutable default argument `roles=[]`
2. SQL injection in `add_user` (string concatenation)
3. SQL injection in `find_user`
4. Password stored in plaintext (no hashing)
5. Bare `except: pass` swallows errors; also the `try` wraps the wrong operation
6. Hard-coded secret `API_KEY`
7. `average_age` raises `ZeroDivisionError` on empty list
8. Unused global `users`; connections never closed; no table creation or schema

---

## Final Project: Ship It
**Proposal:** Week 12 · **Due:** Week 14 · **Points:** 100 · **Objectives:** all

### Overview
Build and demo a small working application (web app, CLI, bot, or data tool) using AI assistance. Scope: roughly 10 hours of work. Smaller and finished beats bigger and broken.

### Requirements
- A working demo (5 minutes live)
- Version-controlled repository with meaningful commits
- At least **10 tests**, passing
- `PROMPT_LOG.md` and `DECISIONS.md` (3+ moments where you accepted, rejected, or modified AI output, and why)
- `SECURITY.md`: a short checklist confirming no secrets committed, inputs validated, dependencies checked
- A 1-page **"What the AI got wrong"** report

### Rubric
| Criterion | Points |
|---|---|
| Working application matching the proposal | 30 |
| Tests and code quality | 20 |
| Process documentation (prompt log, decisions) | 20 |
| Security and ethics checklist | 10 |
| Demo and Q&A (can you explain your code?) | 15 |
| "What the AI got wrong" report | 5 |

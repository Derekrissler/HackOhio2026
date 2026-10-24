# VIBE 101: Exams

Closed notes, closed AI. You may use scratch paper. Write code by hand clearly; syntax mistakes will not be penalized if your intent is clear.

---

# MIDTERM EXAM (Week 8): Chapters 1–4
**Time:** 75 minutes · **Total:** 100 points
**Part I:** 12 multiple choice × 3 pts = 36 · **Part II:** 3 free response = 64

## Part I: Multiple Choice

**1.** What makes AI-generated code risky to trust without testing?
- A. It always contains syntax errors
- B. It is always slower than hand-written code
- C. It can look plausible yet be wrong, and output varies between runs
- D. It cannot use standard libraries

**2.** The spec says `first(xs)` returns `None` for an empty list. Which input exposes the bug in the code below?
```python
def first(xs):
    return xs[0]
```
- A. `[]`
- B. `[1]`
- C. `[1, 2, 3]`
- D. `["a"]`

**3.** Which is the strongest rewrite of the prompt "Parse the dates"?
- A. "Parse the dates better."
- B. "Parse the dates quickly and robustly."
- C. "Please parse the dates carefully."
- D. "Write Python `parse_date(s)` that accepts 'YYYY-MM-DD' and returns a `datetime.date`; raise `ValueError` otherwise. Example: '2024-02-29' → `date(2024, 2, 29)`."

**4.** What does `f(4)` return?
```python
def f(n):
    total = 0
    for i in range(1, n):
        total += i
    return total
```
- A. 10
- B. 6
- C. 4
- D. 3

**5.** The spec says `f(n)` should return the sum of the integers from 1 through n. Which change fixes the code in Question 4?
- A. `range(1, n + 1)`
- B. `range(0, n)`
- C. `range(1, n - 1)`
- D. `range(n)`

**6.** A regression test is:
- A. A test that measures how fast code runs
- B. A test for the oldest module in a project
- C. A test added after fixing a bug to confirm it does not return
- D. A test generated using regression analysis

**7.** A test fails. What should you do first?
- A. Rewrite the function from scratch
- B. Ask the AI to fix it and accept the answer
- C. Add print statements everywhere
- D. Reproduce the failure with the smallest possible input

**8.** An AI wrote both your tests and your code from the same ambiguous prompt, and all tests pass. The most accurate conclusion is:
- A. The code is definitely correct
- B. The tests show only that the code agrees with the tests, which may share the same misunderstanding
- C. The tests are too short
- D. The prompt must have been fine

**9.** The assistant's code has `import fastjsonx`, and you have never heard of it. The best action is:
- A. Run `pip install fastjsonx` and see what happens
- B. Ask the AI whether the package is real
- C. Verify the package exists and is legitimate before installing anything
- D. Rename the import to something familiar

**10.** Which is the strongest sign of overengineering?
- A. An abstract factory and a config loader in a 10-line script
- B. Meaningful variable names
- C. A unit test
- D. A docstring

**11.** Which best describes the programmer's role in vibe coding?
- A. Typing every line by hand
- B. Waiting for the AI to finish
- C. Choosing the programming language only
- D. Directing, reviewing, and verifying the AI's output

**12.** What does this code print?
```python
def g(acc=[]):
    acc.append(len(acc))
    return acc

g()
print(g())
```
- A. `[1]`
- B. `[0, 1]`
- C. `[0]`
- D. `[1, 1]`

## Part II: Free Response

**FRQ 1 (20 pts): Prompts as Specs.**
A teammate writes this prompt: *"Write a function that cleans up a list of names."*
(a) (10 pts) Rewrite the prompt so that it includes all five parts of a good prompt (goal, context, constraints, examples, format). Label each part.
(b) (6 pts) List three edge cases the new prompt should address.
(c) (4 pts) Explain in 1–2 sentences why examples help more than adjectives like "robust."

**FRQ 2 (24 pts): Review and Repair.**
The spec: `top_n(scores, n)` returns the `n` highest scores in **descending order**, does **not modify** the input list, returns all scores if `n` exceeds the list length, and returns `[]` if `n <= 0`.
```python
def top_n(scores, n):
    scores.sort()
    return scores[:n]
```
(a) (9 pts) Identify at least three ways this code violates the spec.
(b) (7 pts) Write a corrected version.
(c) (8 pts) Write at least four unit tests (as `assert` statements) that would catch the bugs. Include at least two edge cases.

**FRQ 3 (20 pts): Argue It.**
A teammate says, "We don't need to write tests. The AI is really good now." In 150–200 words, respond. Your answer must (i) give at least two specific reasons tests are still necessary, (ii) mention one limitation of AI-written tests, and (iii) suggest a practical workflow.

---

## Midterm Answer Key and Rubrics

### Part I
1. C · 2. A · 3. D · 4. B · 5. A · 6. C · 7. D · 8. B · 9. C · 10. A · 11. D · 12. B

### FRQ 1 (20 pts)
**(a) 10 pts, 2 per labeled part.** Sample answer:
- Goal: Write a function `clean_names(names)` that normalizes a list of full names.
- Context: Python 3, no external libraries.
- Constraints: Strip leading/trailing whitespace, collapse repeated internal spaces, title-case each word, remove empty strings and duplicates (case-insensitive), preserve first-seen order. Do not modify the input.
- Examples: `["  ada  LOVELACE", "Ada Lovelace", ""]` → `["Ada Lovelace"]`.
- Format: Return the full function with a docstring and no extra explanation.
Partial credit: 1 pt for a part that is present but vague.

**(b) 6 pts, 2 each.** Any three reasonable edge cases: empty list; names that are only whitespace; hyphenated or apostrophe names (e.g., "o'neil", "Mary-Jane"); non-string elements; very long lists; names with Unicode characters; duplicates differing only in case.

**(c) 4 pts.** Examples make behavior concrete and testable; adjectives are subjective and let the AI choose its own interpretation. (2 pts for the contrast with vagueness, 2 pts for connecting to testability or ambiguity.)

### FRQ 2 (24 pts)
**(a) 9 pts, 3 each (max 3 issues).**
1. `scores.sort()` mutates the input list.
2. It sorts ascending, so the slice returns the *lowest* n, not the highest.
3. No handling for `n <= 0`: `scores[:0]` happens to return `[]`, but a negative `n` such as `-1` returns all but the last element, which is wrong.
(Also acceptable: no validation of non-numeric input if the student explains why it matters.)

**(b) 7 pts.**
```python
def top_n(scores, n):
    return sorted(scores, reverse=True)[:max(n, 0)]
```
Full credit for any correct solution: uses `sorted` or copies the list (3 pts), descending order (2 pts), handles `n <= 0` (2 pts).

**(c) 8 pts, 2 each.** Sample tests:
```python
assert top_n([3, 1, 2], 2) == [3, 2]
assert top_n([3, 1, 2], 10) == [3, 2, 1]
assert top_n([3, 1, 2], 0) == []
assert top_n([3, 1, 2], -1) == []
s = [3, 1, 2]; top_n(s, 2); assert s == [3, 1, 2]
```
Tests must be correct and distinct. At least two edge cases (n=0, n<0, n>len, empty list, duplicates) required for full credit.

### FRQ 3 (20 pts)
- **Reasons tests are needed (8 pts, 4 each):** AI output is nondeterministic and can be plausibly wrong; tests document the spec; tests catch regressions; code changes over time; the developer is accountable.
- **Limitation of AI-written tests (4 pts):** They can share the same blind spots or misreadings as the code, so they must be reviewed.
- **Practical workflow (4 pts):** Write spec and tests first (or review the AI's tests), generate code, run tests, add regression tests for bugs.
- **Clarity and length (4 pts):** 150–200 words, organized, respectful tone.

---

# FINAL EXAM (Finals Week): Chapters 1–6 (emphasis on 3–6)
**Time:** 110 minutes · **Total:** 100 points
**Part I:** 10 multiple choice × 3 pts = 30 · **Part II:** 2 free response × 35 = 70

## Part I: Multiple Choice

**1.** What distinguishes an agent from a basic chat assistant?
- A. It never makes mistakes
- B. It takes multiple steps toward a goal with some autonomy, such as editing files or running commands
- C. It runs only on local machines
- D. It cannot use tools

**2.** Which is the best safeguard before letting an agent modify your codebase?
- A. Disable all tests to avoid conflicts
- B. Give it administrator access so it never gets blocked
- C. Trust that it will ask if it's unsure
- D. Work in a version-controlled repository and review the diff before accepting changes

**3.** You discover an API key committed to a public repository. Your first action should be to:
- A. Revoke or rotate the key immediately
- B. Delete the commit and assume the problem is solved
- C. Wait to see whether anyone uses it
- D. Change the variable name

**4.** Which code is safe from SQL injection?
- A. `db.execute("SELECT * FROM t WHERE n='" + name + "'")`
- B. `db.execute(f"SELECT * FROM t WHERE n='{name}'")`
- C. `db.execute("SELECT * FROM t WHERE n = ?", (name,))`
- D. `db.execute("SELECT * FROM t WHERE n=" + repr(name))`

**5.** Which test best targets a boundary case for `mean(xs)` defined as `sum(xs) / len(xs)`?
- A. `mean([1, 2, 3])`
- B. `mean([5, 5, 5])`
- C. `mean([10, 20])`
- D. `mean([])`

**6.** When is it most appropriate to write code by hand rather than using AI?
- A. Boilerplate configuration files
- B. A throwaway script
- C. Learning a new concept you are trying to master, or security-critical code you must fully understand
- D. Translating a short function between languages

**7.** Which is a privacy concern when using AI coding tools?
- A. Using meaningful variable names
- B. Pasting real user records into a third-party tool without permission
- C. Writing unit tests
- D. Adding comments

**8.** An agent proposes running `rm -rf` on a project directory. The best policy is:
- A. Require explicit human approval for destructive or irreversible actions
- B. Let it proceed to save time
- C. Allow it only on weekends
- D. Ask the agent whether it is sure, then proceed if it says yes

**9.** After an AI "fix," your failing test now passes, but you notice the test file no longer contains that test. What should you do?
- A. Accept the fix, since the suite is green
- B. Ask the AI to rewrite the test
- C. Delete the other tests too for consistency
- D. Restore the test and require the code, not the test, to be changed to pass

**10.** Which statement is most accurate?
- A. AI assistance eliminates the need for code review
- B. AI-generated code is always insecure
- C. AI assistance changes where effort goes, but verification is still required
- D. Only beginners benefit from AI assistance

## Part II: Free Response

**FRQ 1 (35 pts): Security Review.**
```python
import sqlite3

SECRET = "hunter2-prod"

def login(name, pw):
    db = sqlite3.connect("app.db")
    q = f"SELECT * FROM users WHERE name='{name}' AND pw='{pw}'"
    return db.execute(q).fetchone() is not None
```
(a) (10 pts) Identify at least three security or quality problems and explain why each matters.
(b) (15 pts) Rewrite `login` to fix them. You may assume a helper `verify_password(pw, stored_hash)` exists.
(c) (10 pts) Write two tests that would catch problems in the original.

**FRQ 2 (35 pts): Agent Guardrails.**
Your team plans to let an AI agent make multi-file changes and run shell commands in your project.
(a) (16 pts) Propose a guardrail plan with at least four distinct safeguards. For each, explain the specific risk it addresses.
(b) (9 pts) Describe one situation where you would choose **not** to use an agent and justify your choice.
(c) (10 pts) Explain how your prompt log and a `DECISIONS.md` file support accountability when something goes wrong.

---

## Final Exam Answer Key and Rubrics

### Part I
1. B · 2. D · 3. A · 4. C · 5. D · 6. C · 7. B · 8. A · 9. D · 10. C

### FRQ 1 (35 pts)
**(a) 10 pts (up to 4 issues; 3 pts for the first three found, 1 pt for a fourth):**
1. SQL injection through f-string interpolation of `name` and `pw`.
2. Passwords compared in plaintext, which implies they are stored unhashed.
3. Hard-coded secret `SECRET` in source code.
4. The connection is never closed; no error handling.
Each requires an explanation of impact (e.g., "attacker can log in as anyone with `' OR '1'='1`").

**(b) 15 pts.** Sample:
```python
import sqlite3

def login(name, pw):
    db = sqlite3.connect("app.db")
    try:
        row = db.execute(
            "SELECT pw_hash FROM users WHERE name = ?", (name,)
        ).fetchone()
    finally:
        db.close()
    return row is not None and verify_password(pw, row[0])
```
Rubric: parameterized query (5), password verified via hash (5), secret removed or moved to an environment variable (3), connection closed (2).

**(c) 10 pts, 5 each.** Sample tests:
```python
def test_sql_injection_blocked():
    assert login("' OR '1'='1", "x") is False

def test_wrong_password_rejected():
    assert login("alice", "wrong") is False
```
Also acceptable: test that the secret is not present in source; test that unknown user returns False.

### FRQ 2 (35 pts)
**(a) 16 pts, 4 per safeguard (2 for the safeguard, 2 for the risk).** Examples: version control and diff review (unintended or unrecoverable changes); least-privilege permissions (damage from misuse); human approval for destructive commands (data loss); sandboxed or non-production environment (outages and leaked data); test suite must pass before merge (regressions); spending or step limits (runaway cost); no secrets in the agent's accessible environment (leakage).

**(b) 9 pts.** Any well-justified case, such as security-critical authentication code, an unfamiliar concept the student is trying to learn, or a production database migration where review time exceeds writing time. (4 pts situation, 5 pts justification tied to risk and verification cost.)

**(c) 10 pts.** The prompt log records what was asked and what changed, enabling reproduction and root-cause analysis (5 pts). `DECISIONS.md` records why AI output was accepted, rejected, or modified, showing human judgment and responsibility (5 pts).

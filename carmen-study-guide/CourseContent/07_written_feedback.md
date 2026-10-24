# VIBE 101: Sample Written Feedback

These are example student submissions paired with instructor/TA feedback. They show the grading style for the course: specific, kind, tied to the rubric, and focused on next steps. Names are fictional.

**Feedback style guide**
- Start with something specific the student did well.
- Tie every deduction to a rubric line.
- Quote the code or text being discussed.
- End with one concrete next step.
- Humor is welcome in moderation. Sarcasm is not.

---

## Assignment 1 Feedback: "Hello, Vibes"

**Student:** Jordan P. · **Score: 79 / 100**

### Excerpt of submission (`todo.py`)
```python
import json, os

def load():
    return json.load(open("tasks.json"))

def add(text):
    tasks = load()
    new_id = len(tasks) + 1
    tasks.append({"id": new_id, "text": text, "done": False})
    json.dump(tasks, open("tasks.json", "w"))
    print(new_id)
```

### Excerpt of prompt log
> **Prompt 1:** make a todo app in python
> **Prompt 2:** add json saving
> **Prompt 3:** add done command
> **Prompt 4:** fix the bug
> **Prompt 5:** make it better

### Rubric Breakdown
| Criterion | Score | Notes |
|---|---|---|
| Functionality | 34 / 40 | `add`, `done`, `list` all work. IDs are reused after deletion (see below). |
| Edge cases | 8 / 15 | Crashes if `tasks.json` does not exist. No handling of an invalid ID. |
| Code quality | 8 / 10 | Clean and short. Files are opened without being closed. |
| Prompt log | 14 / 20 | Honest, but prompts are very short and "fix the bug" does not say which bug. |
| Reflection | 15 / 15 | Genuinely thoughtful. See below. |

### Written Feedback
Jordan, nice work. Your code is short, readable, and it runs, which is already more than some "enterprise" software can claim. The reflection was the highlight of this submission. You wrote that your biggest mistake was "asking for features instead of describing rules," and that is exactly the lesson of Chapter 2.

Two things to address:

1. **IDs are reused.** `new_id = len(tasks) + 1` means that if you delete task 2 of 3, the next task gets ID 3 and collides with the existing one. The spec said IDs are never reused, which implies you need to track a `next_id` separately or use `max(id) + 1`. This was exactly the kind of detail that a stronger first prompt would have caught: "IDs start at 1 and are never reused" appears in the assignment text, but not in your Prompt 1.
2. **Missing file crash.** Run `python todo.py list` on a fresh machine and you get a `FileNotFoundError`. Try it. A one-line test would have found this.

Your prompt log reads like a list of commands, not a conversation. "Fix the bug" tells me nothing: *which* bug, what did you see, what did you expect? Compare:

> "Running `list` with no tasks.json raises FileNotFoundError. It should print nothing and exit cleanly."

That second version is shorter to debug and shorter to grade.

**Next step:** Before Assignment 2, rewrite your Prompt 1 as a full five-part prompt and see how much of the code changes. You do not need to submit it, but I suspect you will be surprised.

---

## Assignment 3 Feedback: "The Bug Hunt"

**Student:** Priya S. · **Score: 89 / 100**

### Excerpt of submission (`review.md`)
> **Issue 1 (security):** In `add_user`, the SQL is built with string concatenation so a name like `'); DROP TABLE users;--` could destroy data. Fix: parameterized query.
> **Issue 2 (security):** Password is stored as plain text. Use bcrypt.
> **Issue 3 (correctness):** `roles=[]` is a mutable default argument, so roles accumulate across calls.
> **Issue 4 (style):** `except: pass` is bad.
> **Issue 5 (security):** API key is hard-coded.
> **Issue 6 (correctness):** `average_age` will divide by zero.

### Rubric Breakdown
| Criterion | Score | Notes |
|---|---|---|
| Issues found | 32 / 40 | Six of eight found. Missing SQL injection in `find_user` and the unclosed connections. |
| Fixed code | 24 / 25 | Excellent. Parameterized queries, bcrypt, env var. One minor miss: still no `CREATE TABLE`. |
| Tests | 14 / 15 | Good. The mutable default test is exactly right. |
| AI comparison | 14 / 15 | Honest and specific. |
| Clarity | 5 / 5 | |

### Written Feedback
Priya, this is strong work. Your explanation for Issue 1 is the model answer: you did not just say "SQL injection," you showed the actual input that breaks it. That is how a real security review reads.

A few notes:

- **Issue 4 is underexplained.** "Bad" is not a reason. *Why* is `except: pass` bad here? Because it swallows every exception, including `KeyboardInterrupt`, and hides failures that you would want to know about. There is also a subtler point: the `try` wraps `fetchone()`, but the real failure risk is in the query above it, so the handler is guarding the wrong line. You will get full credit next time for explaining the *consequence*.
- **You missed `find_user`.** You caught the injection in `add_user` but not the identical one in `find_user`. This is a common reviewer trap: once you have found a bug pattern, search for **every** instance of it. A quick text search for `"' +"` would have caught it.
- **Your AI comparison was the best in the section.** Noticing that the AI fixed one function and silently left the other is precisely the kind of thing we want to see. It supports the course's central point: the AI is a useful reviewer but a confident one, so verify.

**Next step:** For your final project, add a "pattern sweep" step to your `SECURITY.md`: after fixing any vulnerability, search the entire codebase for the same pattern.

---

## Midterm Feedback: FRQ 2 (Review and Repair)

**Student:** Marcus L. · **FRQ 2 Score: 15 / 24**

### Student Response
> **(a)** The code sorts the list so it changes the original. Also it doesn't sort in descending order.
> **(b)**
> ```python
> def top_n(scores, n):
>     s = scores.copy()
>     s.sort(reverse=True)
>     return s[:n]
> ```
> **(c)**
> ```python
> assert top_n([1,2,3], 2) == [3,2]
> assert top_n([5,1], 5) == [5,1]
> ```

### Rubric Breakdown
| Part | Score | Notes |
|---|---|---|
| (a) | 6 / 9 | Two of three issues, both correct and clearly stated. Missing the negative `n` problem. |
| (b) | 5 / 7 | Copy and descending order are both correct. No handling for `n <= 0`. |
| (c) | 4 / 8 | Two correct tests, but both are normal cases. Only the second is arguably an edge case (n greater than length). |

### Written Feedback
Marcus, you have the core ideas right. You noticed the mutation and the wrong sort order, and your `copy()` plus `reverse=True` fix is clean and readable. Many students missed the mutation bug entirely, so well done.

Where points were lost:

1. **The `n <= 0` requirement.** The spec explicitly says "returns `[]` if `n <= 0`." With your code, `top_n([1,2,3], -1)` returns `[3, 2]` because `s[:-1]` means "everything except the last item." That is a classic slicing trap, and it is the sort of subtle behavior AI-generated code gets wrong while sounding confident. Adding `max(n, 0)` fixes it.
2. **Your tests are all happy-path.** The question asked for at least two edge cases. Edge cases are where bugs live: `n = 0`, `n = -1`, an empty list, and duplicates are all good candidates. Notice that if you had written a test for `n = -1`, you would have discovered your own bug in part (b). This is exactly why we write tests *before* the code.
3. You did not test that the input list is unchanged, which was one of the three spec requirements. A test like `s = [3,1,2]; top_n(s, 2); assert s == [3,1,2]` would have covered it.

**Next step:** For every function you write this term, make a list titled "ways this could break" *before* you write any code. Five minutes of pessimism saves an hour of debugging.

---

## Final Exam Feedback: FRQ 2 (Agent Guardrails)

**Student:** Elena R. · **FRQ 2 Score: 29 / 35**

### Student Response (summarized)
> **(a)** 1) Use git so changes can be reverted. 2) Give the agent only the permissions it needs. 3) Require my approval before it runs delete commands. 4) Run tests before merging.
> **(b)** I would not use an agent to write the authentication code because I need to understand every line, and review would take as long as writing it.
> **(c)** The prompt log shows what happened, and DECISIONS.md shows why.

### Rubric Breakdown
| Part | Score | Notes |
|---|---|---|
| (a) | 12 / 16 | Four valid safeguards, but each is missing the risk it addresses. |
| (b) | 9 / 9 | Clear situation and sound justification. |
| (c) | 8 / 10 | Correct but brief. Needs an example. |

### Written Feedback
Elena, solid exam. Part (b) was the best answer I read. You gave a specific situation, and you tied your reasoning to verification cost, which is exactly the argument from Chapter 6.

Two notes for improvement:

- **Part (a): safeguards without risks.** The question asked you to explain "the specific risk it addresses." You listed the safeguards, which are all correct, but you lost 4 points because you did not say *what could go wrong without them*. For instance: "Require approval before delete commands, *because an agent running `rm -rf` on the wrong directory could cause irreversible data loss.*" The safeguard shows you know the tool. The risk shows you understand why it exists.
- **Part (c): make it concrete.** "The prompt log shows what happened" is true but general. A stronger answer: "If production broke after an agent change, the prompt log tells me which instruction triggered it, and DECISIONS.md tells me whether we accepted the agent's output deliberately or by accident." One example turns a definition into an argument.

**Next step:** In any future design doc, practice the "safeguard → risk" pattern. It is the difference between a checklist and a justification.

---

## Quick-Reference Comment Bank (for TAs and the Canvas AI)

| Situation | Suggested comment |
|---|---|
| Strong spec | "This spec is clear enough that I could implement it without asking you a single question. That is the bar." |
| Vague prompt log | "Your log tells me what you asked for but not what was wrong. Add what you observed and what you expected." |
| Missing edge case | "Try the empty input. Then try one element. Then try something nasty." |
| Unexplained claim | "You identified the issue correctly. Now explain the consequence: what breaks, and for whom?" |
| Over-reliance on AI | "I cannot tell which parts of this you understand. Add a short explanation of lines X–Y in your own words." |
| Great catch | "Noticing this is exactly what separates a reviewer from a rubber stamp." |
| Late but honest | "Thank you for being straightforward about the delay. Please see the late policy for the adjustment." |

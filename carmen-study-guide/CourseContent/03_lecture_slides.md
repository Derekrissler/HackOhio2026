---
marp: true
theme: default
paginate: true
title: "VIBE 101 Lecture Slides"
---

<!-- Slides are separated by "---". Compatible with Marp; also readable as plain text. -->

# VIBE 101
## Lecture 1: What Is Vibe Coding?
Dr. Quinn Ferrous

*Textbook: Chapter 1*

---

# Today's Agenda
- Define vibe coding
- Where it shines, where it burns
- The Vibe Coding Loop
- Live demo: "Build me a to-do app" (what could go wrong?)

---

# Definition
**Vibe coding:** building software by describing intent in natural language and having an AI generate most of the code.

Your job changes from **typing** to **directing, reviewing, verifying**.

---

# Abstraction, Again
Machine code → Assembly → C → Python → **Natural language**

Key difference: compilers are deterministic. Language models are **not**.

> Same prompt, different code. Plan accordingly.

---

# Where It Works
- Prototypes and throwaway scripts
- Boilerplate and config
- Learning new libraries
- Translating between languages
- First drafts of tests

---

# Where It Struggles
- Big codebases with unwritten rules
- Safety- or performance-critical code
- Novel algorithms
- Anything where "mostly right" is not right

---

# The Vibe Coding Loop
1. **Describe**
2. **Generate**
3. **Read**
4. **Test**
5. **Refine**

Steps 3 and 4 are not optional. They are the whole course.

---

# Key Takeaway
**You own the output.**

"The AI wrote it" has the same legal and professional weight as "autocomplete wrote it."

*Next time: Prompting as Specification*

---

# Lecture 2: Prompting as Specification
*Textbook: Chapter 2*

---

# A Prompt Is a Spec
**Weak:** "Make a to-do app."

**Strong:** "Python CLI to-do app. Commands: `add`, `done`, `list`. JSON storage. IDs start at 1, never reused. Standard library only."

Which one would *you* want to implement?

---

# Five Parts of a Good Prompt
1. **Goal**
2. **Context**
3. **Constraints**
4. **Examples**
5. **Format**

---

# Examples Beat Adjectives
- ❌ "Make it robust."
- ✅ "Return `None` for an empty list. Raise `ValueError` on negative values."

Edge cases in the prompt = fewer surprises in the code.

---

# Iterating Without Spiraling
- Name **what** is wrong
- Change **one** thing at a time
- If you've rewritten the prompt 6 times, **the spec is the problem**

---

# Prompt Logs
Record: prompt → response → what you changed and why.

Purpose: reproducibility, accountability, and grading. (Yes, we read them. Yes, all of them. Maya has opinions.)

---

# Lecture 3: Reading Code You Didn't Write
*Textbook: Chapter 3*

---

# The Reading Checklist
1. Matches the spec?
2. Trace by hand
3. Check boundaries
4. Check hidden assumptions
5. Check dependencies
6. Look for smells

---

# Spot the Bug
```python
def average(nums):
    return sum(nums) / len(nums)
```
What happens on `[]`?

**Answer:** `ZeroDivisionError`. Is that in the spec? If not, it's a bug.

---

# Spot the Other Bug
```python
def add_item(item, items=[]):
    items.append(item)
    return items
```
Call it twice. What do you get?

**Answer:** the default list is shared across calls. The second call returns both items.

---

# Common AI Failure Modes
- Hallucinated APIs
- Plausible but wrong logic
- Silent `except: pass`
- Mutable default arguments
- Outdated practices
- Overengineering (a factory for a 10-line script)

---

# Lecture 4: Tests First, Vibes Second
*Textbook: Chapter 4*

---

# Tests Are the Seatbelt
"It seems to work" → "It works on these cases."

---

# Test-First Prompting
1. Write the spec
2. Write the tests
3. Generate code to pass them
4. Run the tests

⚠️ AI-written tests for AI-written code can share the **same blind spots**. Review both.

---

# What to Test
- Normal cases
- Edge cases (empty, one, huge, duplicates)
- Error cases
- Regression cases (every fixed bug gets a test)

---

# Systematic Debugging
1. **Reproduce** minimally
2. **Locate** the divergence
3. **Hypothesize**
4. **Fix** one thing
5. **Re-run** everything

Do not accept a "fix" that deletes the failing test.

---

# Lecture 5: Security, Privacy, Ethics
*Textbook: Chapter 5*

---

# Secrets
- Never paste keys into prompts
- Never commit them
- Use environment variables and `.gitignore`

```python
API_KEY = "sk-12345"   # Delete this immediately
```

---

# Vulnerabilities in Generated Code
- SQL injection (string-built queries)
- No input validation
- Insecure defaults (debug mode, weak hashing)
- Fake or malicious packages

---

# Licensing, Privacy, Responsibility
- Generated code can resemble open-source code
- Don't send others' personal data to tools without permission
- **You are accountable for what you ship**

---

# Lecture 6: Agents and Guardrails
*Textbook: Chapter 6*

---

# Chat vs. Agent
**Chat:** answers questions.
**Agent:** takes multiple steps, edits files, runs commands.

More power. More ways to ruin your afternoon.

---

# Guardrails
- Use version control
- Minimum permissions
- Approval for destructive actions
- Review every diff
- Human checkpoint before production

---

# When Not to Vibe
- Security-critical code you must fully understand
- Concepts you are trying to learn
- High-stakes code where review costs more than writing

---

# Course Wrap-Up
You can now:
- Write specs, not wishes
- Read before trusting
- Test before shipping
- Say "no" to the AI when needed

*May your builds be green and your diffs be small.*

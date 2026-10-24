# VIBE 101: Quizzes

Each quiz is 15 minutes, closed notes, closed AI. Answer keys are included for instructors and the Canvas AI.

---

## Quiz 1 (Week 3): Chapters 1–2
**Total: 20 points** (8 MCQ × 2 pts, 2 short answer × 2 pts)

### Multiple Choice

**1.** Which best defines vibe coding?
- A. Writing code while listening to lo-fi music
- B. Using an IDE with syntax highlighting
- C. Letting an AI write and deploy code without human review
- D. Building software by describing intent to an AI and directing, reviewing, and verifying its output

**2.** What is the key difference between a compiler and a language model?
- A. Compilers are deterministic; language models are not
- B. Language models cannot write Python
- C. Compilers are faster
- D. Compilers only work on small programs

**3.** Which task is generally a GOOD fit for vibe coding?
- A. Flight-control software
- B. A cryptographic library
- C. A medical dosage calculator
- D. A throwaway script to rename 200 files

**4.** In the Vibe Coding Loop, which steps are NOT optional?
- A. Describe and Generate
- B. Read and Test
- C. Describe and Refine
- D. Generate and Refine

**5.** Which prompt is the strongest?
- A. "Write a Python function `sort_desc(nums)` that returns a new list sorted high to low, leaving the input unchanged. Example: `[3,1,2]` → `[3,2,1]`."
- B. "Write a sorting function, make it fast and robust."
- C. "Write a good sorting function."
- D. "Write a sorting function."

**6.** The five parts of a good prompt are:
- A. Input, Output, Process, Storage, Display
- B. Who, What, When, Where, Why
- C. Goal, Context, Constraints, Examples, Format
- D. Goal, Tone, Length, Audience, Format

**7.** You've rewritten your prompt six times with small tweaks and still get wrong output. The most likely problem is:
- A. You should switch programming languages
- B. Your spec is unclear or incomplete
- C. The model is broken
- D. You need a longer prompt regardless of content

**8.** What is the purpose of a prompt log?
- A. To satisfy the compiler
- B. To record prompts, responses, and your changes so the process is documented and reproducible
- C. To make the AI remember you
- D. To increase code speed

### Short Answer

**9.** Give one reason "the AI wrote it" is not an acceptable defense for a bug in production. (2 pts)

**10.** Rewrite this weak prompt into a stronger one: *"Make a calculator."* Include at least three of the five parts. (2 pts)

### Answer Key
1. D · 2. A · 3. D · 4. B · 5. A · 6. C · 7. B · 8. B
9. Full credit: the developer owns and is accountable for shipped code; the AI is a tool, like autocomplete. (1 pt for the idea of accountability, 1 pt for connecting it to ownership or professional responsibility.)
10. Sample: "Write a Python function `calc(a, op, b)` supporting `+ - * /` on numbers. Return the result as a float. Raise `ValueError` for unknown operators and for division by zero. Example: `calc(6, '/', 3)` → `2.0`." (Goal + Constraints + Example = full credit. 1 pt per two parts, max 2.)

---

## Quiz 2 (Week 6): Chapters 3–4
**Total: 20 points**

### Multiple Choice

**1.** What does this return on its second call?
```python
def add(x, items=[]):
    items.append(x)
    return items
add(1); add(2)
```
- A. `[1, 2]`
- B. `[1]`
- C. `[2]`
- D. Error

**2.** What is a "hallucinated API"?
- A. An API that responds slowly
- B. An API with a graphical interface
- C. A call to a function or library that does not exist
- D. An undocumented but real endpoint

**3.** Which is the best first step when reviewing AI-generated code?
- A. Ask the AI if it is correct
- B. Delete the comments
- C. Deploy it and see
- D. Check whether it matches the spec and trace it on a small example

**4.** What is wrong with `except: pass`?
- A. It is a syntax error
- B. Nothing, it is best practice
- C. It silently hides all errors, making failures hard to detect
- D. It makes the code run slower

**5.** Which is an edge case for a function that finds the maximum of a list?
- A. A list sorted in ascending order
- B. A list of three positive numbers
- C. A list of five numbers
- D. An empty list

**6.** In test-first prompting, you should:
- A. Generate code, then write tests to match whatever it does
- B. Write the spec and tests first, then have the AI generate code to pass them
- C. Skip tests if the AI is confident
- D. Only test error cases

**7.** Why can AI-written tests for AI-written code be risky?
- A. They cannot run in pytest
- B. They are not allowed in Python
- C. They may share the same blind spots as the code
- D. They are always too long

**8.** What is a regression test?
- A. A test written in a statistical regression library
- B. A test of the oldest code
- C. A test added to ensure a previously fixed bug does not return
- D. A test for slow code

### Short Answer

**9.** Name two items from the six-item reading checklist and explain one in a sentence. (2 pts)

**10.** The assistant "fixed" your failing test by deleting the test. Explain what you should do instead. (2 pts)

### Answer Key
1. A · 2. C · 3. D · 4. C · 5. D · 6. B · 7. C · 8. C
9. Any two of: matches spec, trace by hand, check boundaries, hidden assumptions, dependencies, smells (1 pt), plus a correct one-sentence explanation (1 pt).
10. Restore the test; determine whether the test or the code is wrong using the spec; fix the actual cause. (1 pt for restoring or not accepting deletion; 1 pt for using the spec to decide.)

---

## Quiz 3 (Week 10): Chapter 5
**Total: 20 points**

### Multiple Choice

**1.** Where should an API key be stored?
- A. Hard-coded in the source file
- B. In an environment variable that is not committed to version control
- C. In a code comment
- D. In a public README

**2.** Which code is vulnerable to SQL injection?
- A. An ORM query with bound parameters
- B. A prepared statement
- C. `cur.execute("SELECT * FROM t WHERE n = '" + name + "'")`
- D. `cur.execute("SELECT * FROM t WHERE n = ?", (name,))`

**3.** "Slopsquatting" refers to:
- A. A type of SQL injection
- B. Over-commenting code
- C. Attackers registering package names that AI tools commonly hallucinate
- D. Writing messy code

**4.** Which password storage approach is acceptable?
- A. Reversible encryption with a key in the code
- B. Base64 encoding
- C. Plaintext
- D. Salted hash using a dedicated algorithm (e.g., bcrypt or argon2)

**5.** You want to paste a customer database into an AI tool to help clean it. You should:
- A. Paste it immediately
- B. Check permissions and policies first, and remove or anonymize personal data
- C. Paste only the first half
- D. Rename the file first

**6.** Generated code closely resembles a known open-source library. The best response is to:
- A. Delete the license file
- B. Check licensing implications and cite, rewrite, or comply as needed
- C. Ignore it
- D. Assume AI output is always license-free

**7.** Which is an insecure default often found in generated web apps?
- A. Debug mode enabled in production
- B. Rate limiting
- C. Input validation
- D. HTTPS

**8.** Who is accountable for harm caused by shipped AI-assisted code?
- A. The developer or team that shipped it
- B. Nobody
- C. The user only
- D. The AI vendor only

### Short Answer

**9.** You accidentally committed an API key to a public repo. List two steps you should take. (2 pts)

**10.** Give one example of a privacy risk when using AI coding tools. (2 pts)

### Answer Key
1. B · 2. C · 3. C · 4. D · 5. B · 6. B · 7. A · 8. A
9. Any two: revoke or rotate the key immediately; remove it from the code and use an environment variable; scrub history if needed; check logs for misuse. (1 pt each; rotation is the most important.)
10. Sample: pasting customer data, proprietary code, or credentials into a third-party tool. (2 pts for a concrete example, 1 pt for vague.)

# Vibes, Prompts, and Production
## A Field Guide to Vibe Coding

*"The code compiles. The vibes are good. What could go wrong?" — Famous last words, every semester*

---

## Chapter 1: What Is Vibe Coding?

### 1.1 Definition
**Vibe coding** is a style of software development in which the programmer describes intent in natural language and relies on an AI assistant to generate most of the code. The programmer's job shifts from *typing* to *directing, reviewing, and verifying*.

### 1.2 A Short History
Programming has always moved toward higher abstraction: machine code, assembly, compilers, high-level languages, frameworks. Vibe coding is the next step in that sequence. The difference is that earlier abstractions were deterministic. A compiler given the same input produces the same output. A language model does not. That single fact explains most of this book.

### 1.3 Where It Works
- Prototypes and throwaway scripts
- Boilerplate (config files, CRUD endpoints, data parsing)
- Learning a new library or language
- Translating code between languages
- Writing first drafts of tests

### 1.4 Where It Struggles
- Large codebases with unwritten conventions
- Performance-critical or safety-critical code
- Novel algorithms with no good public examples
- Anything where "mostly right" is not good enough

### 1.5 The Vibe Coding Loop
1. **Describe** what you want.
2. **Generate** code with the assistant.
3. **Read** what came back.
4. **Test** it.
5. **Refine** the prompt, the code, or both.

Skipping step 3 or 4 is how you end up deploying a login page that accepts any password. This has happened. Not in this class, but somewhere.

### 1.6 Key Idea: You Own the Output
The assistant writes the code. You ship it. If it breaks production, "the AI did it" is not a defense, in the same way "autocomplete did it" never was.

---

## Chapter 2: Prompting as Specification

### 2.1 A Prompt Is a Spec
A vague prompt produces vague code. Compare:

> **Weak:** "Make a to-do app."
>
> **Strong:** "Write a Python command-line to-do app. Commands: `add <text>`, `done <id>`, `list`. Store tasks in a JSON file `tasks.json`. IDs are integers starting at 1 and never reused. `list` prints `[ ] 1 Buy milk` or `[x] 1 Buy milk`. Use only the standard library."

The second prompt names the language, interface, storage, ID rules, output format, and constraints.

### 2.2 The Five Parts of a Good Prompt
1. **Goal:** what the code should do
2. **Context:** language, framework, existing code
3. **Constraints:** libraries allowed, style, performance, what *not* to do
4. **Examples:** sample inputs and expected outputs
5. **Format:** how you want the answer (full file, diff, explanation)

### 2.3 Examples Beat Adjectives
"Make it robust" means nothing. "Return `None` if the list is empty; raise `ValueError` if any element is negative" means something. Give edge cases explicitly.

### 2.4 Iterating Without Spiraling
When the output is wrong, resist re-rolling. Instead:
- Identify *what* is wrong (wrong behavior, wrong style, wrong approach).
- Tell the assistant specifically.
- Change one thing at a time.

If you have rewritten the same prompt six times with minor tweaks, the problem is probably your spec, not the model.

### 2.5 Prompt Logs
A **prompt log** records your prompts, the assistant's key responses, and what you changed. It documents your process and lets others (and future you) understand why the code looks the way it does.

---

## Chapter 3: Reading Code You Didn't Write

### 3.1 Why Reading Matters More Now
When you write code yourself, you understand it by default. When an assistant writes it, understanding is a separate step that you must do deliberately.

### 3.2 A Reading Checklist
1. **Does it match the spec?** Check each requirement.
2. **Trace it by hand** on a small example.
3. **Check boundaries:** empty input, single element, maximum size, negative numbers, `None`/null.
4. **Check hidden assumptions:** is it assuming sorted input? Unique elements? Specific encodings?
5. **Check dependencies:** does it import a library that exists? (Assistants sometimes invent them.)
6. **Look for smells:** unused variables, duplicated logic, swallowed exceptions, magic numbers.

### 3.3 Common AI Code Failure Modes
- **Hallucinated APIs:** calls to functions or packages that do not exist.
- **Plausible but wrong logic:** off-by-one errors, wrong comparison operators.
- **Silent error handling:** a bare `except: pass` that hides every failure.
- **Mutable default arguments:** `def f(x, items=[])` in Python shares one list across calls.
- **Outdated practices:** deprecated functions, old library versions.
- **Overengineering:** a factory pattern for a 10-line script.

### 3.4 Example
```python
def average(nums):
    return sum(nums) / len(nums)
```
Looks fine. But `average([])` raises `ZeroDivisionError`. Is that acceptable? Only if the spec says so. Otherwise, it is a bug.

---

## Chapter 4: Tests First, Vibes Second

### 4.1 Why Tests Are the Seatbelt
Tests turn "it seems to work" into "it works on these cases." With AI-generated code, tests are your main defense against confident nonsense.

### 4.2 Test-First Prompting
1. Write the spec.
2. Write tests (by hand, or ask the assistant and then *review them*).
3. Ask the assistant to write code that passes the tests.
4. Run the tests.

Note that AI-written tests for AI-written code can share the same blind spots. Review both.

### 4.3 What to Test
- **Normal cases:** typical inputs
- **Edge cases:** empty, one item, very large, duplicates
- **Error cases:** invalid input, missing files
- **Regression cases:** every bug you fix gets a test so it stays fixed

### 4.4 A Minimal Example
```python
def test_average_basic():
    assert average([2, 4, 6]) == 4

def test_average_empty():
    # spec: return 0 for empty list
    assert average([]) == 0
```

### 4.5 Systematic Debugging
When something fails:
1. **Reproduce** it with the smallest input possible.
2. **Locate** where actual behavior diverges from expected (print statements, debugger, tracing).
3. **Hypothesize** a cause.
4. **Fix** one thing.
5. **Re-run** all tests.

Do not paste the error into the assistant and accept the first fix without reading it. Sometimes the "fix" is deleting the test.

---

## Chapter 5: Security, Privacy, and Ethics

### 5.1 Secrets
Never paste API keys, passwords, or private data into a prompt. Never commit them to a repository. Use environment variables and `.gitignore`. Assistants will cheerfully generate code with `API_KEY = "sk-12345"` hard-coded. Do not keep it.

### 5.2 Common Vulnerabilities in Generated Code
- **SQL injection:** building queries with string concatenation instead of parameterized queries.
- **Missing input validation:** trusting user input.
- **Insecure defaults:** debug mode on, wide-open CORS, weak password hashing.
- **Dependency risk:** installing packages that are abandoned, malicious, or non-existent ("slopsquatting").

### 5.3 Privacy
Do not send other people's personal data to a third-party assistant unless you are permitted to. Know where your data goes and how the tool's provider uses it.

### 5.4 Licensing
Generated code may resemble existing open-source code. Check your tool's policies and your project's license requirements. When in doubt, cite, rewrite, or choose a different approach.

### 5.5 Ethics and Responsibility
You are accountable for what you ship. Consider who might be harmed by errors, bias, or misuse, and be honest with users and teammates about what was AI-assisted.

---

## Chapter 6: Agents, Tools, and Automation

### 6.1 From Chat to Agents
Early assistants answered questions. Modern ones can run commands, edit files, and call tools. An **agent** is an assistant that takes multiple steps toward a goal with some autonomy.

### 6.2 Benefits and Risks
**Benefits:** faster multi-file changes, automated test-fix loops, less copy-pasting.
**Risks:** unintended file changes, runaway costs, deleted data, actions you did not approve.

### 6.3 Guardrails
- Work in a **version-controlled** repository so every change can be reverted.
- Give the agent the **minimum permissions** it needs.
- Require **approval** for destructive or irreversible actions.
- **Review the diff** before accepting changes.
- Keep a **human checkpoint** before anything reaches production.

### 6.4 When Not to Use AI
Use your own hands when the code is security-critical and you need full understanding, when you are learning a concept and need the struggle, or when the cost of a mistake is high and review time exceeds writing time.

---

## Glossary

| Term | Definition |
|---|---|
| **Agent** | An AI system that takes multiple actions toward a goal with some autonomy |
| **Boilerplate** | Repetitive, standard code with little unique logic |
| **Edge case** | An input at the extreme or unusual end of the allowed range |
| **Hallucination** | AI output that is confident but false, such as a nonexistent function |
| **Prompt** | The instruction given to an AI assistant |
| **Prompt log** | A record of prompts and responses used during development |
| **Regression test** | A test added to ensure a fixed bug does not return |
| **Spec** | A precise description of required behavior |
| **Vibe coding** | Building software by directing an AI assistant in natural language |

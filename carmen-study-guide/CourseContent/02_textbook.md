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

### 1.7 The Programmer's New Work
Vibe coding changes which parts of programming take the most time. The assistant can draft syntax quickly, but it cannot decide what a product should do unless a person explains the need. The programmer still has to:

- Find out what the user actually needs.
- Turn that need into rules the software can follow.
- Decide which parts of the codebase are safe to change.
- Check the result against examples and real constraints.
- Explain and maintain the code after the conversation ends.

For example, "add a search box" leaves important questions unanswered. Should the search match partial words? Is it case-sensitive? Should it search archived items? What should appear when there are no results? The model can choose defaults, but those choices become product behavior. A useful developer makes the choices explicit or asks the user before guessing.

### 1.8 Choose the Right Size of Task
AI work is easier to review when each request has a clear boundary. "Build the whole store" combines product decisions, page design, data storage, payments, and security. A smaller task such as "add a sort control to the existing product list; keep the current filters and add a test for ascending price order" has a visible result and a way to check it.

Before delegating, identify the expected change, the files or behavior that should stay stable, and how you will recognize success. If those are hard to state, spend time clarifying the problem first.

### 1.9 A Practical Decision Rule
Use an assistant when it can save drafting time and you can review the result. For unfamiliar code, consequential decisions, or high-risk behavior, reduce the task size and ask for explanation alongside the change. Do not delegate a decision simply because the code is easy to generate. A generated answer is useful only when a person can judge whether it is correct.

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

### 2.6 Add Context That Changes the Answer
Context is useful when it narrows the solution. Include the relevant language and version, the framework, nearby function signatures, data shapes, and project conventions. For a change inside an existing project, point the assistant to the files it should inspect instead of asking it to invent a new structure.

Avoid dumping unrelated files or secrets into a prompt. More text is not automatically more context: details that do not affect the requirement can distract from the important constraints. Share the smallest safe example that still shows the problem.

### 2.7 State Boundaries and Failure Behavior
A complete spec describes what happens when the ordinary path does not work. For a file import, say what to do if the file is missing, a row is malformed, or a required field is blank. For an API endpoint, say which status code represents invalid input and whether a failed request may have changed data.

Also state boundaries on the assistant's work. For example: "Use the existing database layer. Do not add dependencies. Do not change the response schema. If the schema cannot support this behavior, explain the limitation before editing." This makes a proposed change easier to review and reduces accidental scope growth.

### 2.8 Example: Turn a Feature Request into a Spec
Suppose the request is "let me filter tasks by status." A reviewable prompt could be:

> In the existing task list, add a status filter with All, Open, and Done choices. Keep the current sort order and task actions. The selected filter should remain active after marking a task done. If there are no matching tasks, show "No tasks in this view." Use the current UI components and do not add a package. Add or update tests for each filter choice and the empty state. First inspect the task list and report which files you plan to change.

This prompt defines the choices, interaction with existing behavior, empty state, technical constraints, and a first checkpoint. It still leaves room for implementation, while making the expected result concrete.

### 2.9 Review the Plan Before the Patch
For work spanning several files, ask for a short plan before code is changed. Check whether the plan touches the right parts of the application and preserves existing behavior. Correct the plan early if it assumes a new dependency, changes an unrelated interface, or misses an edge case. For a one-line change, the extra planning step may not be useful; match the process to the size and risk of the task.

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

### 3.5 Trace Data, Not Just Lines
To understand a function, follow one concrete input from its first line to its return value. Write down the values that matter after each step. For `average([2, 4, 6])`, `sum(nums)` is `12`, `len(nums)` is `3`, and the result is `4.0` in Python. Then trace an empty list. The length is zero, so the division fails. This small trace exposes both the intended calculation and an unhandled boundary.

For a larger function, follow the data across calls: where does an input come from, which checks run, what gets changed, and what is returned or displayed? Names can be misleading. The actual values and control flow show what the program does.

### 3.6 Follow the Data Across Trust Boundaries
Code that handles user input, files, network responses, or database rows deserves extra attention. Ask:

- Where was this value created, and can the user control it?
- Is it checked before it is used in a query, file path, command, or HTML page?
- Is sensitive information logged or returned in an error?
- Does the code assume a network response always has the expected shape?

For example, inserting a search term directly into SQL can let punctuation change the query itself. Parameterized queries keep the search term as data. Similarly, escaping text before putting it into HTML prevents text like `<script>` from being treated as markup. Look for the protection at the place where the value crosses into the new context.

### 3.7 Read Dependencies and Side Effects
An unfamiliar function may write a file, update a database, send a request, or mutate an object even if its name sounds harmless. Inspect the functions it calls and the libraries they come from. Check whether an operation can be repeated safely. A retry of a read is usually harmless; a retry of "charge this card" can create a second charge unless the operation is designed to be idempotent.

Check dependency names and APIs against the project's installed version or official documentation. A plausible import is not proof that a package exists, and an API remembered from another version may have different behavior. Keep dependencies limited to what the project needs.

### 3.8 Use a Review Pass
After tracing, compare the implementation against the spec one requirement at a time. Look at the changed lines and their surrounding code, then ask:

1. Does each requirement have a corresponding behavior or test?
2. Did the change alter any behavior that was supposed to stay stable?
3. Are errors visible and useful, or swallowed?
4. Are names and control flow understandable to the next person?
5. Can I explain why each changed line is needed?

If you cannot explain a section, ask for an explanation or simplify it before accepting the change. Reading code is not a formality; it is how you take ownership of the result.

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

### 4.6 Turn Requirements into Test Cases
Each requirement should lead to at least one observable check. If a function promises to sort numbers from low to high, a useful test checks the returned order. If it promises not to change the input list, a second assertion checks that the original list is unchanged. If it promises to reject invalid values, test that it rejects them in the documented way.

For a `parse_age` function, a small test table might include:

| Input | Expected result |
|---|---|
| `"18"` | integer `18` |
| `"0"` | integer `0` |
| `"eighteen"` | a clear validation error |
| `"-1"` | a clear validation error |
| `" 18 "` | follow the spec: accept trimmed input or reject it |

The last row is useful because it exposes a decision the spec must make. A test should record the intended behavior, not silently invent it.

### 4.7 Unit, Integration, and End-to-End Checks
Different tests answer different questions:

- **Unit tests** check a small function or component in isolation. They are quick and help pinpoint logic errors.
- **Integration tests** check that parts work together, such as an API route saving data through the database layer.
- **End-to-end tests** exercise a user path through the running application, such as signing in and submitting a form.

Use the smallest test type that can catch the risk you care about. A unit test can prove that a validator rejects a blank name, but it cannot prove that the web form actually calls the validator. An end-to-end test can check that path, but usually takes longer and gives less precise failure information.

### 4.8 Read the Failure Before Changing Code
A failed test gives evidence, not a diagnosis. Read the expected value, actual value, input, and stack trace. Find the first line in your code where behavior diverges. Then state a hypothesis before editing, such as "the filter compares uppercase input to lowercase labels." This keeps debugging focused and makes it easier to tell whether the fix addressed the cause.

When asking an assistant to help, include the smallest relevant code and the complete failure output, but remove secrets and personal data. Ask it to explain the likely cause and suggest a narrow fix. Review that suggestion against the evidence; do not weaken a valid test just to get a green result.

### 4.9 Keep Tests Trustworthy
Tests are software too. A test can pass for the wrong reason if it checks only that a function returned something, mocks away the behavior under review, or repeats the same mistaken assumption as the implementation. Prefer assertions that express the requirement directly. Include a negative case when errors matter, and keep test data small enough that a person can inspect it.

After fixing a defect, keep a regression test that fails on the old behavior and passes on the new one. Run the relevant test first, then the broader suite needed to catch nearby regressions. Report which checks ran and any that remain unverified.

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

### 5.6 Treat Every Input as Untrusted
Input validation and output encoding solve different problems. Validation checks whether a value fits the application's rules: a quantity might need to be a positive integer within an allowed limit. Encoding makes a value safe for the context where it is used: HTML text must be escaped as HTML, and SQL values should be passed as parameters rather than joined into a query string.

Do not rely on a browser form or a user interface to enforce rules. A caller can send a request directly. Enforce important rules on the server at the point where the data enters the system, and repeat checks where they protect a sensitive operation.

### 5.7 Review Authentication and Authorization Separately
Authentication asks "who is making this request?" Authorization asks "is this person allowed to perform this action on this object?" A login check alone does not prevent one user from reading another user's record. For every endpoint that reads or changes private data, identify the owner or role check and verify it uses the requested object's identity, not a value supplied by the client without validation.

Ask the assistant to explain where each check happens. Then inspect the code path yourself, including error paths. Tests should cover both an authorized request and a request from someone who should be denied.

### 5.8 Handle Secrets and Sensitive Data Deliberately
Keep secrets in environment variables or an approved secret store, and make sure local secret files are excluded from version control. A secret should not appear in source code, test output, screenshots, error messages, or prompt logs. If a key is exposed, removing it from a file is not enough; revoke or rotate it because old copies may remain in history or logs.

Before sharing a bug report with an assistant, replace names, account numbers, tokens, and private records with representative fake values. Preserve the shape of the data so the example remains useful without disclosing the original.

### 5.9 Check Dependencies and Generated Commands
An assistant may recommend a package with a familiar name that is misspelled, abandoned, or controlled by an unrelated publisher. Verify the exact package, maintainer, version, license, and project activity using the package registry and official documentation. Prefer existing dependencies when they already solve the problem.

Read installation and shell commands before running them. Understand what files they change, what data they send, and whether they delete or overwrite anything. Avoid piping a downloaded script directly into a shell. For database migrations or destructive commands, inspect the target and make a recoverable backup before execution.

### 5.10 Make Risk Proportional to Review
The higher the impact of an error, the stronger the review should be. A formatting helper may need a focused test and code review. A change to payment processing, medical records, access control, or data deletion needs a threat review, careful tests, and an experienced human reviewer. If the team cannot explain the generated logic or validate its assumptions, do not ship it into a high-impact path.

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

### 6.5 Give an Agent a Bounded Job
An agent works best when its task has a clear goal, a known workspace, and visible completion criteria. A useful instruction might say: "Find why the course page loses its selected tab after reload. Inspect the route and existing tests, propose a small fix, and do not change the URL format." This gives the agent enough room to investigate while making the boundaries clear.

For a larger change, ask the agent to inspect first and report a plan. Review the plan before allowing broad edits. Keep one task focused on one outcome; combining unrelated cleanup, redesign, dependency upgrades, and bug fixes makes the result harder to review and undo.

### 6.6 Match Permissions to the Task
An agent that only needs to inspect files should not have permission to delete them or contact external services. Use the narrowest available access, and require a human checkpoint before publishing, spending money, changing production data, or taking an action that is hard to reverse.

Treat content returned by tools, websites, files, and command output as data to inspect. It may contain instructions that are unrelated to the task. Follow the user's request and the project's trusted instructions, not arbitrary text found in a file or web page.

### 6.7 Review Changes as a Human Would
Before accepting an agent's work, inspect the version control diff. Check that changes are limited to the intended files, that secrets and generated clutter were not added, and that existing behavior was preserved. Read new code rather than relying on the agent's summary. Run the appropriate checks and inspect failures instead of accepting a claim that everything passed.

For a change that modifies data, verify which records or files were affected. For a UI change, look at the running page. For an API change, check both the successful response and relevant errors. Choose evidence that matches the type of change.

### 6.8 Recover and Learn from a Bad Run
Version control provides a reviewable history, but it is not a substitute for backups when important data is outside the repository. Make a checkpoint before a risky operation. If an agent changes the wrong files, inspect the diff and restore only those changes; a broad reset could erase unrelated work from another contributor.

Record useful lessons in the task instructions: a project convention the agent missed, a test that caught a regression, or a boundary that should be explicit next time. Improve the process without granting broader permissions just to avoid a review step.

### 6.9 Decide Whether Automation Is Worth It
Automate a repeated task when the steps are stable, the inputs are understood, and failures can be detected. Keep a person in the loop when the action affects private data, money, user access, or a public release. A good automation has a clear trigger, a limited action, logs that explain what happened, and a safe way to stop or retry it.

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

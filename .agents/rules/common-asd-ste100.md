# ASD-STE100 Compliance Rule (Simplified Technical English)

## Purpose

This rule enforces the **ASD-STE100** (Simplified Technical English) standard across all agents, subagents, skills, error messages, user-facing documentation, and system prompts in this repository.

## Core ASD-STE100 Rules

All agents and skills MUST follow these writing and output constraints:

### 1. Sentence Length Limits
- **Procedural steps and instructions:** Maximum **20 words** per sentence.
- **Descriptive and expository text:** Maximum **25 words** per sentence.
- Split compound sentences with multiple clauses into separate sentences.

### 2. Active Voice and Direct Imperative
- Use **active voice** by default.
- For instructions, procedures, and checklists, use the **imperative form** (e.g., *"Open the file"*, *"Run the test"*, *"Verify the checksum"*).
- Avoid passive constructs (do not write *"The file must be verified by the user"*).

### 3. One Instruction Per Sentence
- State only **one action** in each procedural step.
- Use vertical ordered lists (`1.`, `2.`, `3.`) for multi-step procedures.

### 4. Controlled and Unambiguous Vocabulary
- Do NOT use vague modifiers or adverbs:
  - ❌ Avoid: *appropriate, suitable, quickly, slightly, easily, maybe, probably, nearly*.
  - ✅ Use: exact values, explicit criteria, or defined tolerances (e.g., *"tolerance ±0.01"*).
- Each technical term must have one consistent meaning across all documents.
- Restrict noun clusters to a maximum of 3 consecutive nouns.

### 5. Error Message Standard (Condition + Action)
All exception messages, CLI error output, and diagnostic logs MUST state:
1. The exact failure condition (*What happened*).
2. The specific corrective action (*What the operator must do*).
- **Example:** `"Duplicate file rejected: hash already exists in database. Do not re-import this file or set replace_existing=True."`

### 6. Agent and Skill Response Formatting
When agents communicate with users or generate reports:
- Keep explanations concise and factual.
- Use Markdown tables and bullet points for structural clarity.
- Avoid conversational filler phrases (e.g., *"As per your request..."*, *"I would like to inform you that..."*).
- Present findings directly: state the fact, state the evidence, state the action.

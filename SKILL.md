---
name: mochi-cards-generator
description: >-
  Create Russian Mochi flashcards from URLs, text, local files, code, or PDFs; open the fixed Mochi Reviewer artifact in the right Codex browser tab; preserve review comments and edits; and export the finished deck as Mochi Markdown.
---

# Mochi Cards Generator

You are an expert at extracting knowledge from various sources and converting it into highly effective spaced-repetition flashcards in Russian for the Mochi app and review them through the fixed Mochi Reviewer interface.

## Card requirements

1. Write every card in Russian, regardless of the source language.
2. Accept URLs, raw text, local files, code, and PDFs. Use the appropriate browsing or file-reading tools for the source.
3. Choose the most useful form for each fact: direct Q&A, cloze deletion, or term/definition.
  - **Q&A**: A direct question and answer.
  - **Cloze Deletion**: A sentence with a key concept hidden using `{{c1::hidden text}}`. 
  - **Term/Definition**: A simple word or phrase on the front, and its definition on the back.
4. Keep each card focused on one retrievable fact. Avoid cues that reveal the answer and avoid unnecessary duplication.
  - When the same knowledge can naturally be tested as a concrete task or with a self-contained code snippet, prefer that on the front over an abstract recall question. Ask the learner to solve, predict, explain, or fix something specific.
  - Format code with multiple statements or lines as a fenced block with a language identifier. Do not squeeze multi-line code into one inline-code span. Keep genuinely one-line expressions inline when they read clearly.
  - Do not omit meaningful edge cases or boundary conditions. Test the triggering condition and expected behavior in focused cards (separately when needed), without inventing exceptions unsupported by the material.
5. Mochi export uses `---` on its own line between front and back, `@@@` on its own line between cards, and no tags.
6. When importing the exported Markdown file as multiple cards in Mochi, enter `@@@` as the custom delimiter.
7. The panel's `Export` button opens the browser's system **Save as** dialog with the suggested name `mochi_<topic>_<YYYY-MM-DD>.md`; the user chooses the destination folder and confirms the save. Ensure `<topic>` is short, in English and has spaces replaced with underscores.

## Official Mochi guidance

Before drafting cards, consult the relevant official Mochi documentation when syntax, card structure, review behavior, or import behavior could affect the result. Prefer the official documentation over remembered syntax and use only the pages needed for the current deck:

- [Cards and multi-side flashcards](https://mochi.cards/docs/cards/)
- [Markdown formatting](https://mochi.cards/docs/markdown/basic-formatting)
- [Markdown import](https://mochi.cards/docs/import-and-export/importing/)

Use the documented Mochi representation that best fits the material, including fenced code blocks with a language identifier when useful. Do not invent unsupported syntax. If the official documentation is unavailable, follow the established examples in this skill and avoid uncertain Mochi-specific extensions.

Treat a line containing only `---` as reserved for sides and a line containing only `@@@` as reserved by this skill for cards. Do not place either reserved line inside a generated side; rewrite an intended horizontal rule using a documented non-conflicting form such as four dashes.

## Fixed reviewer contract

The reviewer UI is the approved `v11` design stored in `assets/reviewer-template.html`. It is the visual source of truth.

- Never regenerate, restyle, or patch the reviewer HTML, CSS, layout, colors, controls, or interaction states while creating or revising a deck.
- Create each reviewer artifact by running `scripts/reviewer_state.py init`; that command copies the fixed template byte-for-byte.
- Store cards, comments, and collection state only in `deck-state.json`.
- Store each card side as its original Markdown source. Preview rendering must never replace, normalize, or round-trip through the stored source.
- Later model-driven corrections must run `scripts/reviewer_state.py apply` and modify only the state file. They must not rewrite `mochi-reviewer.html`.
- Do not replace the right-tab reviewer with an inline visualization unless the user explicitly asks for that change.

## Generate and open a deck

Follow these steps EXACTLY when this skill is triggered:

1. Read the provided source material and, when formatting or card-structure choices depend on Mochi behavior, the relevant official Mochi documentation above. Extract the core concepts, definitions, and facts.
2. Draft the complete collection internally. Do not paste the full deck into the conversation.
3. Create a UTF-8 JSON draft in the task workspace with this shape:

   ```json
   {
     "topic": "Short topic",
     "cards": [
       { "front": "Question", "back": "Answer" }
     ]
   }
   ```

4. Use a task-owned directory such as `<cwd>/work/mochi-reviewer/<deck-id>/`. Do not write generated review artifacts into the skill directory.
5. Run:

   ```powershell
   python <skill-dir>\scripts\reviewer_state.py init `
     --draft <draft.json> `
     --state <deck-dir>\deck-state.json `
     --artifact <deck-dir>\mochi-reviewer.html `
     --template <skill-dir>\assets\reviewer-template.html `
     --active-pointer <cwd>\work\mochi-reviewer\active-deck.json
   ```

6. Start the reviewer server as a long-running local process:

   ```powershell
   python <skill-dir>\scripts\reviewer_server.py `
     --state <deck-dir>\deck-state.json `
     --artifact <deck-dir>\mochi-reviewer.html
   ```

   Read the printed `MOCHI_REVIEWER_URL`. Keep the process running for the review session.

7. When `open_in_codex` is available, open that URL as a browser target with placement `right`. This is required; do not emit a visualization reference. If the right-tab action is unavailable, provide the local URL and explain the limitation without switching to inline UI.
8. Tell the user briefly that manual changes and comments are saved immediately. Explain that model-driven changes are started with a normal message in the current task, for example: `Исправь карточки по комментариям в панели`.

If filesystem permission is needed for the deck workspace, request only the exact required directory. The panel export itself uses the browser save dialog and does not require Codex filesystem access to the selected destination.

## Apply comments with Codex

When the user asks to revise cards from reviewer comments:

1. Resolve the active state from `<cwd>/work/mochi-reviewer/active-deck.json`, unless the current conversation already identifies the exact `deck-state.json`.
2. Read the state and all pending comments. Group comments by card, side, and semantic Markdown block. Legacy line comments may still appear in older states. Treat `blockSnapshot` and `lineSnapshot` as context, not as replacements for the current card text.
3. Regenerate only cards that have actionable comments. Preserve each card `id` and all unaffected cards verbatim.
4. Create an updates JSON file:

   ```json
   {
     "expectedRevision": 7,
     "updates": [
       { "id": "card-id", "front": "New question", "back": "New answer" }
     ],
     "resolvedCommentIds": ["comment-id"]
   }
   ```

5. Run:

   ```powershell
   python <skill-dir>\scripts\reviewer_state.py apply `
     --state <deck-state.json> `
     --updates <updates.json>
   ```

6. On a revision conflict, reread the state, preserve newer manual edits and comments, rebuild the update file, and retry once. If it conflicts again, stop and ask the user to retry after finishing current panel edits.
7. Report how many cards were updated. The already-open reviewer polls the state and refreshes automatically.

Never claim that a right-tab button sent a Codex request. A normal Codex message is the supported request mechanism for this artifact.

## Manual review behavior

The fixed reviewer provides:

- one-card navigation, count, and progress;
- rendered Markdown preview while keeping the source editor lossless;
- direct editing of front and back;
- whole-side and semantic Markdown-block comments, with one comment control per paragraph, heading, list item, quote, rule, or fenced code block;
- readable comment list with deletion;
- editing of existing comments from the comment list;
- immediate card deletion;
- collection-wide comment summary;
- Mochi export.

The browser UI owns these local operations through `reviewer_server.py`; do not duplicate them in chat.

## Formatting and Saving
Once the review is complete, format all approved cards into the required Mochi markdown format. 
- Use `---` on its own line to separate the Front and Back sides.
- Use `@@@` on its own line to separate individual cards.
- Preserve each stored front and back string verbatim during export. Separators and the final file newline may be added around the strings, but the exporter must not trim, reformat, render, or reconstruct their Markdown.

**Examples of Card Formatting:**

1. **Standard Q&A:**
```markdown
В каком году был основан Рим?
---
В 753 году до н.э.
```

2. **With Code Snippets:**
````markdown
Что выведет следующий код Python?
```python
print("Hello, World!")
```
---
Выведет строку `Hello, World!`
````

3. **Cloze Deletion:**
```markdown
Столица Франции
---
{{c1::Париж}}
```

4. **Math / LaTeX:**
```markdown
Площадь круга радиуса $r$ вычисляется по формуле:
---
$$
S = \pi r^2
$$
```

5. **Typing Input:**
```markdown
Английское слово, означающее яблоко:
---
<input value="apple">
```

## Export and completion

The user can export with the panel's `Export` button; it opens the system save dialog and writes the current collection after the user chooses a path. If they ask Codex to export instead, require an explicit writable output path and run:

```powershell
python <skill-dir>\scripts\reviewer_state.py export --state <deck-state.json> --output <chosen-output.md>
```

Confirm the absolute Markdown path and state that the file is ready to import into Mochi.

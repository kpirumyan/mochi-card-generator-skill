# Mochi Cards Generator

A Codex skill that turns URLs, text, local files, source code, and PDFs into focused Russian flashcards for [Mochi](https://mochi.cards/).

It creates a local reviewer alongside each deck, so cards can be edited and annotated before export to Mochi Markdown.

## What it does

- Writes every card in Russian and keeps each one focused on a single retrievable fact.
- Selects an appropriate card form: question/answer, term/definition, or cloze deletion.
- Preserves card Markdown, including syntax-highlighted code blocks.
- Opens a local reviewer with card navigation, editable front and back sides, line and side comments, and editable saved comments.
- Exports the approved collection as Mochi-compatible Markdown using `---` between sides and `***` between cards.

## Use it in Codex

Invoke the skill and give it a source:

```text
$mochi-cards-generator https://example.com/article
```

You can also provide pasted text, a local file, code, or a PDF. The reviewer opens in the right panel when Codex supports it. Changes made there are stored immediately in the deck's `deck-state.json` file.

To ask Codex to apply reviewer feedback, send a normal message such as:

```text
Исправь карточки по комментариям в панели
```

Use the reviewer's **Export** button when the deck is ready; it opens the system save dialog for the final Markdown file.

## Repository layout

```text
SKILL.md                         Skill instructions and workflow contract
agents/openai.yaml               Codex-facing metadata
assets/reviewer-template.html    Fixed reviewer interface
scripts/reviewer_state.py        State initialization, updates, and export
scripts/reviewer_server.py       Local reviewer HTTP server
```

## Development notes

The reviewer template is deliberately fixed. Deck-specific content, comments, and review state belong in `deck-state.json`, not in the template. When changing the reviewer, keep the browser client and `reviewer_server.py` actions in sync, then validate the affected Python and JavaScript paths.


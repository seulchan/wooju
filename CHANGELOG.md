# Changelog

All notable changes to Wooju. Versions follow [Semantic Versioning](https://semver.org);
until 1.0, a minor version may change how things work.

## Unreleased

- Search finds notes by meaning too, grouped into knowledge, ideas and sources.
- Related notes on every note: what it links to, what links to it, what is close in meaning.
- A new source that says nearly the same as an existing note is pointed out (never merged).
- Markdown links between notes count as connections (they were missing from the map).
- Notes record which AI agent and model wrote to them, shown under Details.
- Retiring a note can name the note that replaces it.

- Weekly summary on Telegram: Sunday evening, what is waiting on Home.
- Keyboard shortcuts: ⌘K to search, ⌘N for a new note.

## 0.4.0 — 2026-10-27

The first version meant for testers. Everything below is new since the start of
the project.

### Taking things in
- Drop PDF, text, Markdown or HTML files; paste a link or write a memo.
- Capture from the phone: an iCloud Drive folder ("Wooju Inbox") and a Telegram bot.
- The local AI organizes each file into a source note in the material's own language,
  with its original kept in the Brain. Duplicate links are not saved twice.
- A new source that disagrees with existing notes is flagged with a Conflicts section.

### Finding and asking
- Search by keyword and by meaning (local embeddings), in Korean and English.
- Ask your Brain: answers cite the notes they rest on, sentence by sentence, say
  what the notes don't cover, and appear as they are written.
- Connect Claude Desktop with one click (MCP): Claude can search, read and propose notes.

### Thinking
- Write your own notes and thoughts that rest on other notes.
- One-line takeaways, questions the AI asks you about a note, and recall before rereading
  with spaced review dates.
- Insights move candidate → provisional → established; the Challenger writes down what
  could make one wrong before it is trusted.

### Keeping it right
- Every change is a proposal: validated, approved when it matters, committed to history,
  and undoable. Edit a proposal or a note directly; retire wrong notes instead of deleting.
- Home shows what needs attention: review dates, conflicts, notes whose grounds changed.

### The app
- Mac app (Apple Silicon) with a local AI through Ollama; OpenAI or Claude API keys optional.
- App language in Settings (follows the Mac by default).
- Sample notes to look around with on an empty Brain.
- The local server answers only this Mac, keeps no access log, and one copy of the app
  runs at a time.

# Changelog

All notable changes to Wooju. Versions follow [Semantic Versioning](https://semver.org);
until 1.0, a minor version may change how things work.

## 0.5.0 — 2026-10-28

Notes you can check against the original, long files read to the end, and
answers that look in the originals when your notes fall short.

- Every key point of a new source note shows the original's own sentence that
  states it. The AI picks the sentence; the app copies it from the original,
  so it cannot be made up. Points the original does not state are left out.
- Long files are read to the end, in parts (up to about 16 × 6K tokens with the
  local AI), instead of only their first pages. The inbox shows how far a long
  file has got, questions can be asked in between, and a file that had to
  wait continues where it stopped.
- Ask looks in the originals: when your notes don't cover part of a question,
  Wooju reads the original documents behind the notes it found and answers
  that part from them, shown apart and quoted, since no note vouches for it.
- A saved link sent again is checked for changes. If the page changed, it is
  saved as a new version that lists the sentences added and removed; the
  earlier version is retired and notes resting on it are flagged on Home.
- Settings shows this month's usage of an OpenAI or Claude API key: calls and
  tokens per model, and an estimated cost where the model's price is known.
- Korean PDFs whose text comes out with a space between every syllable
  ("주 요  뉴 스") are read as normal text, and invisible control characters
  in a file no longer show up as "�".
- Settings shows the build an installed app was made from, next to the version.

## 0.4.0 — 2026-10-28

The first public version. Everything below is new since the start of the project.

### Finding and connecting
- Search finds notes by meaning too, grouped into knowledge, ideas and sources.
- Related notes on every note: what it links to, what links to it, what is close in meaning.
- A new source that says nearly the same as an existing note is pointed out (never merged).
- Markdown links between notes count as connections (they were missing from the map).
- Notes record which AI agent and model wrote to them, shown under Details.
- Retiring a note can name the note that replaces it.
- Topics: overview notes gather the notes about one subject. The topics agent
  files new notes into them, suggests new topics when notes cluster, and a tap
  creates one with an AI-written name and summary.
- Weekly summary on Telegram: Sunday evening, what is waiting on Home.
- Keyboard shortcuts: ⌘K to search, ⌘N for a new note.
- Search previews show link names instead of Markdown.

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

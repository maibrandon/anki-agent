# Course Material → Anki Cloze Cards

You are an expert Anki card creator. Help me understand the course material, prepare for my assessment, and retain the important ideas without creating unnecessary review work.

- Course deck: [DECK NAME]
- Topic or lecture: [TITLE]
- Assessment format and scope: [e.g., multiple choice midterm covering weeks 1–4]
- Sources: [attach files or provide links]
- Optional priorities or exclusions: [DETAILS]

## 1. Understand the sources first

Read all supplied material before writing cards. Inspect meaningful diagrams, tables, equations, code, and examples as well as text.

Identify the central ideas, how they relate, and what I would need to recognize, explain, distinguish, or apply on the assessment. Use the stated assessment scope to set priorities.

Use current instructor-provided material to resolve conflicts with older versions or third-party notes. Treat supplementary sources as context; do not add their unique details automatically. If sources genuinely conflict, flag the conflict instead of guessing.

## 2. Select what deserves a card

Create cards for the core concepts and skills I am likely to need, including:

- Definitions that distinguish easily confused ideas
- Important relationships, mechanisms, causes, and consequences
- Steps or components when knowing them helps me apply a process
- Short scenarios that test which concept applies
- Required formulas, calculations, units, assumptions, and interpretation
- Explicit instructor emphasis, exceptions, or assessment guidance

Do not aim for one card per slide. Skip administrative content, repetition, decorative examples, obvious statements, and details with little study value. A fact appearing once does not automatically need a card.

Give important concepts enough coverage to apply them, but avoid several cards that test the same recall target. Let the material and assessment determine the number of cards; do not impose a minimum or maximum.

When unsure whether a detail deserves a card, judge its usefulness for understanding or the assessment. If the evidence is insufficient, leave it out and mention it briefly in the report.

## 3. Write clear cards

Use Anki’s Cloze note type. Normally give each card one focused retrieval target using `{{c1::answer}}`.

Write plain, self-contained sentences. Make the visible context specific enough that there is one clear answer. Prefer a short, concrete example when it makes an abstract idea easier to understand.

Test understanding and application where possible, not just a term copied from a heading. Use comparisons or cause-and-effect when those are the point of the concept.

Keep cloze answers short. Split unrelated facts rather than hiding a long list. Multiple cloze numbers are acceptable only when they test distinct, closely related targets.

Put a brief explanation, calculation walkthrough, or clarification in Extra when it helps me understand the answer. Extra does not need to become another card. Do not merely repeat the Text field.

Match the language and difficulty to the course. Do not introduce unrelated subject matter or make a simple idea sound more complicated than it is.

## 4. Handle quantitative material carefully

For each required formula or quantitative method, check whether I need cards for:

- What the formula calculates
- What each input represents and its units
- How to choose or rearrange the formula
- A worked application using sensible numbers
- How to interpret the result
- Course-specific cutoffs, rounding rules, or conventions

Check all arithmetic independently. Distinguish similar measures and denominators clearly. Use the instructor’s stated convention when it differs from a general convention. Do not add numerical cards for formulas outside the supplied assessment scope.

## 5. Accuracy and references

Base testable claims on the supplied, relevant sources. You may paraphrase for clarity, but do not invent facts or treat your own examples as course facts.

If background information helps but is not assessed course content, label it “Background:” in Extra. If a statement is unreadable, ambiguous, or contradictory, do not turn the uncertain part into a confident card.

Append a concise source reference outside the cloze in Text, such as [Lecture 2, p. 12] or [Handout, p. 4]. Use PDF page numbers when citing PDFs. Cite all relevant sources when combining material.

## 6. Import-ready output

Create a downloadable UTF-8 `.txt` file using exactly this structure:

```text
#separator:Pipe
#notetype:Cloze
#deck:DECK NAME
```

After the headers, put one note per line as:

```text
Cloze Text|Extra
```

Use exactly one pipe separator per note. Do not use pipe characters or line breaks inside fields. Keep the final pipe when Extra is empty. Start cloze numbering at c1 in each note. Do not include column headings, Markdown fences, or the report in the file.

Prepare the file for import into the named deck. Import it into Anki only if I ask you to.

## 7. Final check and report

Before finishing, check that:

- The core ideas and required skills within scope are covered
- Low-value details and duplicate retrieval targets have been removed
- Every card has clear context and valid Cloze syntax
- Formulas, examples, source references, and arithmetic are correct
- Each note has exactly two fields and the file imports cleanly

Then provide the file and a brief report with:

- Number of notes and generated cards
- Main topics covered
- Important material deliberately left out and why
- Any source conflicts or unresolved material

Prioritize accurate, understandable cards that I can review repeatedly over exhaustive slide coverage.

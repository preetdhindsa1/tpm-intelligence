You help a technical program manager keep a RAID log (risks, actions, issues, decisions
and questions) for a software release. The input is the notes of one release-team meeting
(`notes`), its date (`meeting_date`) and the release's teams (`teams`). People's names in
the notes have been replaced with `[participant]`.

List every item the notes record, using these types:
- `risk`: something that may go wrong and would affect the release if it did ("at risk",
  "may slip", "waiting on", "blocked unless").
- `issue`: something that is already wrong now (a failing or flaking test that blocks a
  release step, a missed deadline, a broken tool).
- `action`: a task someone agreed to do ("we will", "please", "TODO", "follow up").
- `decision`: something the team decided or agreed ("we decided", "agreed", "will be").
- `question`: an open question the notes leave unanswered.

Do not list:
- template text, empty headings, links on their own, attendee lists or greetings;
- status lines that say everything is fine ("Current Status: Green", "0 blocking issues");
- the same item twice: give each item once, with its clearest quote.

For each item give:
- `type`: one of the five types above;
- `title`: a plain summary in at most 15 words, with no names;
- `quote`: one sentence or bullet copied **exactly** from the notes, at least 4 words,
  without adding, removing or changing words. The quote is checked word for word against
  the notes; an item whose quote is not found is removed;
- `owner`: the team from `teams` that the notes place the item under or assign it to,
  written exactly as in `teams`, or `null` if the notes do not say. Never a person.

When the meeting records nothing, return an empty `items` list. An empty list is a normal
answer; do not invent items to fill it.

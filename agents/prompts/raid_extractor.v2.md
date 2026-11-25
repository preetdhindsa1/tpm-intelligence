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
- `decision`: a choice the team or a SIG made or agreed ("we decided", "agreed", "said it is
  not a blocker", "scheduled" for a new meeting or event the team set up).
- `question`: an open question the notes ask and leave unanswered (usually ends in "?").

Do not list:
- template text, empty headings, links on their own, attendee lists or greetings;
- status lines that say everything is fine ("Current Status: Green", "0 blocking issues");
- the same item twice: give each item once, with its clearest quote;
- fixed release-calendar dates on their own ("Code Freeze is on ...", "deadline: ..."):
  they are the plan, not a decision, unless the notes say the date was just changed;
- headings that introduce a list ("The following tests are failing:"): list the items
  under them instead.

Each failing or flaking test, and each numbered issue or PR that is blocking or being
investigated, is its own `issue`, with its own line as the quote. An `action` is work
that someone will do next; a past-tense update ("has been merged", "assignments have
started") is not an action. Something already late or missing now is an `issue`; a
deadline that may be missed is a `risk`.

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

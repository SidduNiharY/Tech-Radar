# TechRadar Brain: Idea and Daily Use

**Written 2026-11-07; updated 2026-11-08** with the agreed improvements: Jarvis, the Library and study material, answers in my way, exam sources, and the security additions. This file covers *why* the app is useful, before any code is written. The latest direction comes first; the sections after it are earlier thinking it builds on. The original technical design is section A2 of [02_AI_Automation_Simple_Stack.md](../02_AI_Automation_Simple_Stack.md), which still describes the tech-only plan. The current tech stack, model plan and security are in [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md), the research behind the model picks is in [03_Local_Models_Research.md](03_Local_Models_Research.md), and a short old-vs-new comparison is in [04_Old_vs_New_SLMs.md](04_Old_vs_New_SLMs.md). The build architecture is in [05_Architecture.md](05_Architecture.md), later improvement ideas (study packs, feedback and self-improvement, Jarvis) are in [06_Improvements.md](06_Improvements.md), the list of attack types and their defences is in [07_Attack_Types.md](07_Attack_Types.md), and the step-by-step build plan starts at [docs/superpowers/plans/2026-11-07-techradar-00-overview.md](docs/superpowers/plans/2026-11-07-techradar-00-overview.md).

## Latest direction: one learning system for my goals

The project has grown from a tech-only second brain into a personal learning system that serves all my goals from one daily routine.

### My goals

1. **Become a full-stack AI automation developer** who knows the modern tech stack.
2. **Prepare for GATE** within the next couple of years.
3. **Prepare for government exams** such as SSC CGL and banking exams (SBI, RRB officer and manager posts).
4. **Stay current and truly understand** every area that matters day to day: tech, GK, politics, the economy, global finance and more. This is for my own knowledge, not only for exams.
5. **Improve my English and soft skills:** grammar, vocabulary, pronunciation, fluency, confidence, interviews and group discussions.

### Key insight: study once, count many times

| What I study | AI developer | GATE | SSC CGL | Bank exams | My own knowledge |
|---|---|---|---|---|---|
| Computer science (DSA, DBMS, OS, networks) | ✅ | ✅ | computer basics | computer aptitude | |
| Quant and reasoning | | ✅ (General Aptitude) | ✅ | ✅ | |
| English | ✅ (interviews, docs) | ✅ (verbal aptitude) | ✅ | ✅ (+ essay and letter) | ✅ (daily life) |
| Soft skills (speaking, interviews, discussions) | ✅ (interviews, teamwork) | PSU interviews | | ✅ (interview, SBI PO group exercise) | ✅ (daily life) |
| Current affairs and GK | | | ✅ | ✅ | ✅ |
| Economy, banking, global finance | | | ✅ | ✅ (big part) | ✅ |
| Tech news and new tools | ✅ | | | | ✅ |

The app's main job: make one hour of study count for as many goals as possible.

**GATE paper choice:** GATE has had a **Data Science and AI (DA)** paper since 2024. It may fit goal 1 better than the Computer Science (CS) paper.

### How the app works: five parts

1. **Radar (collect):** daily news on tech, India, the world, economy and finance, science, and daily-life changes.
2. **Brain (organise):** notes linked to syllabus topics (GATE, SSC CGL, bank exams), to my tech stack, and to foundation pages on the economy, finance, politics, the world and GK.
3. **Practice (remember):** quizzes, flashcards with spaced repetition, and a mistakes notebook, all on Telegram.
4. **Planner (stay on track):** a daily plan, syllabus progress and exam alerts.
5. **Jarvis (talk):** one voice assistant for the whole app. I ask, and it does the job; the Voice Coach is one of its skills.

**The Library** is part of the Brain: whole books, PDFs and long videos I add, searchable to the page or minute, with small study packs (see *Study material* below).

**Where I use it:**
- **Mostly by talking to Jarvis:** "Hey Jarvis" on the laptop, or tap the orb on the phone.
- **The Next.js web app** for things I want to read or see: Today, Ask, Library, Practice, Jarvis, Exams, World, Progress, Models, My profile and Security. See section 5.14 of [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md).
- **Telegram** for push messages and alerts.
- **Obsidian** for my notes.

### Features for each goal

**Goal 1: Full-stack AI automation developer**
- **Skill map:** my stack docs become a checklist. Each tool has a status: *not started → learning → built something with it*.
- **Tech Radar:** releases and rising tools, filtered to my stack.
- **Building this app is practice too:** it uses RAG, agents, scheduling, AI-made quizzes with verification, and evals, which are the skills the job asks for.

**Goal 2: GATE**
- **Syllabus tree:** one page per GATE topic. Notes link to it, and a coverage view shows which topics are done and which are untouched.
- **Past-paper bank:** official previous-year questions sorted by topic, with accuracy tracked per topic so weak areas show up on their own.
- **Mistakes notebook:** every wrong answer is saved with *why* it was wrong and comes back for review.
- **Formula flashcards** with spaced repetition (engineering maths, theory of computation and so on).
- **My GATE books in the Library:** textbooks I own and NPTEL course notes, searchable to the page. Cards are made only for chapters I've marked as read.
- **Sources for every topic:** each syllabus topic links its book pages, NPTEL weeks and past papers. Topics with no source yet show up on the coverage map, and Jarvis suggests one.

**Goal 3: Government exams (SSC CGL, banking)**
- **News → exam questions:** each important news item becomes a one-line fact and an MCQ, so daily news reading becomes exam prep automatically.
- **Monthly current-affairs capsule** built from my own daily notes.
- **Banking and economy awareness:** RBI decisions, the budget, government schemes, appointments, summits and important days, explained simply.
- **Daily aptitude set:** 10 quant and 10 reasoning questions, timed, tracking speed and accuracy.
- **Vocabulary from reading:** new words from editorials become flashcards for the English section.
- **Exam notification watcher:** watches the official SSC, IBPS, SBI and GATE websites and alerts me about new notifications and application deadlines.
- **Starter packs:** NCERT books, RBI and Budget documents, official syllabi and past papers, downloaded once after I approve the list (see *Study material* below).

**Goal 4: Always current, with real understanding**
- **Daily briefing in sections:** Tech · India · World · Economy and finance · Science · Daily life.
- **Each item tagged** *exam-relevant* (it also becomes a fact and an MCQ) or *knowledge only* (read it, understand it, connect it).
- **Daily-life changes:** new rules from the 1st of each month, such as bank charges, UPI limits, tax deadlines and schemes I can use.
- **Finance explainers** (inflation, repo rate, bond yields) at my level, useful day to day and for bank exams.
- **Real understanding, not just headlines:** see *Understand, not just remember* below.
- **Outdated facts get updated:** when an official number changes (for example the repo rate), old cards and questions are updated, and I'm told what changed.

**Goal 5: English and soft skills**
- **Feedback on the reading, writing and speaking I already do** with this app, plus daily grammar and vocabulary practice.
- **Voice Coach (a Jarvis skill):** coaches grammar, vocabulary, pronunciation, filler words, fluency and soft skills. Coaching starts when I ask ("Jarvis, coach my English") or at my set practice time; normal conversations aren't analysed.
- **Details:** see *English and soft skills*, *Voice Coach* and *Jarvis* below.

### Understand, not just remember (GK, finance, economy, politics)

I want to understand GK, finance, the economy and politics for my own knowledge, not only to score in exams. So understanding is the main goal, and exam practice comes from the same reading as a side benefit.

**Two modes for every topic**

| | Remember (for exams) | Understand (for myself) |
|---|---|---|
| Answers | What, who, when | Why, how, what next, how it affects me |
| Output | One-line fact + MCQ | Explainer, cause-and-effect chain, my own view |
| Example | "RBI kept the repo rate at X%" | Why RBI held rates, and what it means for loans, prices and the rupee |

Understanding makes remembering easy: if I know *why* the RBI changes rates, the number sticks without effort.

**Features**

1. **Foundation pages, built once per area.** News only makes sense on top of basics:
   - **Economy:** GDP, inflation, interest rates, the budget and deficit, taxes, the rupee.
   - **Finance:** banks, the stock market, bonds, mutual funds, how money moves around the world.
   - **Politics:** how Parliament, states, courts and elections work; how laws are made; Constitution basics.
   - **World:** geopolitics, trade, oil, the dollar, the UN, IMF and WTO.
   - **GK:** history, geography and science basics.

   Every news item links back to the foundation it depends on. Over months, these pages become my own picture of how the world works.
2. **Every news item answers four questions:** What happened? Why? What does it change? **How does it affect me** (my money, my job, my daily life)?
3. **Cause-and-effect chains.** For example: oil prices rise → transport costs rise → prices go up → RBI keeps rates high → loan EMIs stay high. Saved chains help me see patterns instead of separate headlines.
4. **Politics: facts kept apart from opinions.** Facts are confirmed by several sources. "What supporters say" and "what critics say" are clearly labelled as opinion. I add my own view; the app never tells me what to think.
5. **My opinions and predictions.** After big news I write one line: "What do I think?" Predictions such as "prices will fall by March" come back later with what actually happened, so my judgement grows, not just my knowledge.
6. **Weekly deep dive.** One question a week, explained properly in a 20–30 minute read built from several good sources, picked from what kept showing up in my news. Examples: "Why does the rupee fall against the dollar?", "How does GST work?", "Why do countries impose tariffs?"
7. **A glossary that grows.** Every new term ("fiscal deficit", "bond yield", "no-confidence motion") gets a simple page in plain words, linked wherever it appears. After a year it's my own encyclopedia.
8. **Story timelines.** Long stories (a trade war, a major reform, an election) get one page that grows over months, so I see the whole arc instead of scattered headlines.
9. **Later: connect to LifeLedger.** LifeLedger knows my spending and this app knows the economy. Together they could say: "Prices rose 5% this year, and my grocery spending rose 8%."

**Rhythm**
- **Daily (10–15 min):** 3–5 items explained well, each with "why it matters" and "how it affects me". Better than skimming 30 headlines.
- **Weekly (30 min):** one deep dive, foundation pages updated, past predictions checked.
- **In the background:** the exam layer (facts and MCQs) is built from the same reading, so I learn once, deeply, and exam prep comes free.

**Sources:** facts from official sources (RBI, government press releases, budget documents); analysis from several outlets with different viewpoints.

### English and soft skills

Good English and soft skills matter for every goal:
- **SSC CGL and bank exams** have an English section, and bank PO mains also has a descriptive paper (essay and letter writing).
- **Bank officer selection** ends with an interview, and SBI PO also has a group exercise. Many PSUs that hire through GATE scores also interview.
- **AI developer jobs** are won in interviews: explaining my projects clearly, writing good messages and docs, and working in a team.
- **Daily life:** confidence, and saying what I think clearly.

With this app I already read, write and speak every day. What gets added is **feedback** and **practice**.

**English: read, write, speak, listen**
1. **Reading:** the daily briefing and weekly deep dive are reading practice. Once a week, one article becomes a comprehension quiz, and my reading speed is tracked.
2. **Vocabulary:** new words from my own reading, each with the sentence where I found it, its meaning, synonyms and antonyms. Idioms and one-word substitutions get extra attention for the exams.
3. **Grammar:** 10 exam-style questions a day (error spotting, sentence improvement, cloze test). A **grammar mistakes notebook** tracks the rules I keep breaking, such as confusing *since* and *for*.
4. **Writing:** my daily "My take" line gets corrected, with a short explanation of *why*. Once a week, a timed essay or letter in the bank-exam style, with feedback on structure, grammar and vocabulary.
5. **Speaking:** with the Voice Coach (next section).
6. **Listening:** I watch an English video or podcast, write a 3-line summary, and the app checks it against the transcript.

**Soft skills**
- **With the Voice Coach:** mock interviews, group discussions, "explain it simply", debates and daily-life role plays.
- **Story bank:** my real experiences written as short STAR stories (Situation, Task, Action, Result), ready for "Tell me about a time when…" questions.
- **Writing check:** paste an email, message or README and get a clearer, more polite version, with the reason for each change.
- **Weekly reflection:** one real conversation from the week: what went well, and what I'd do differently.

**Rhythm**
- **Daily (about 15–20 minutes extra):** 5 new words (picked automatically from my reading), 10 grammar questions, and a 10–15 minute Voice Coach session at my set practice time.
- **Weekly:** 1 timed essay or letter, 1 mock interview, 1 group-discussion practice, 1 reflection.

### Voice Coach: a speaking coach for English and soft skills

> **Update (2026-11-07):** the voice side is now **Jarvis**, one voice assistant for the whole app. The Voice Coach below becomes one of Jarvis's skills, used only when I ask for English coaching or at my set practice time. I start each practice mode just by saying it ("Interview me for SBI"). See *Jarvis* below and Part C of [06_Improvements.md](06_Improvements.md).

A voice agent I talk to every day. It coaches my English and soft skills, remembers my mistakes, and uses my own news, projects and stories. It's also the "Voice" part of the AI stack I want to learn (LiveKit, Pipecat, realtime voice models), so building it is goal-1 practice too.

**What it listens for**

| Area | What it checks | Example feedback |
|---|---|---|
| **Grammar** | Tenses, articles, prepositions, subject–verb agreement | "I go to bank yesterday" → "I **went** to **the** bank yesterday" |
| **Sentence formation** | Run-on or broken sentences, word order, linking words | "Split this into two sentences and join them with *but*" |
| **Vocabulary** | Variety, overused words, better word choices | "You said *very good* 9 times; try *excellent* or *impressive*" |
| **Filler words** | um, uh, like, basically, actually, you know | "14 fillers in 8 minutes (basically ×5)" |
| **Fluency** | Speaking speed, long pauses, repeats, false starts | "132 words/min, 4 long pauses mid-sentence" |
| **Pronunciation** | Wrong sounds, word stress, silent letters, dropped sounds | "*v* and *w* sounded the same in *very well*"; "**PHO**tograph but pho**TO**graphy" |
| **Intonation** | Flat voice, statements that rise like questions | "Your statements end on a rising tone, so they sound unsure" |
| **Structure** | Answering clearly: point → reason → example | "2 of 5 answers had no example" |
| **Confidence and tone** | Hedging, politeness, assertiveness | "*I think maybe we can* → *I recommend we*" |
| **Conciseness** | Rambling, answer length | "2 minutes for a one-line question" |
| **Listening** (in role plays) | Did I answer what was actually asked? | "They asked *why*; you answered *what*" |

**Practice modes**
1. **Daily conversation** about today's Radar news. The coach corrects me by *recasting*: it repeats my sentence correctly in its reply, so the conversation keeps flowing. I learn the news and practise English together.
2. **Mock interviews:** tech ("Explain LifeLedger"), HR ("Tell me about yourself", answered with STAR stories) and bank panel ("Why banking?", current affairs). Friendly mode or pressure mode.
3. **Group discussion simulator:** the coach plays 2–3 people with different views. I practise getting into the discussion, disagreeing politely and summarising.
4. **Explain it simply:** I explain a concept I studied, and the coach keeps asking "why?"
5. **Read-aloud:** I read a paragraph from my briefing and get word-by-word pronunciation scores. This is the most accurate mode, because the coach knows the exact text.
6. **Shadowing:** the coach says a sentence with natural rhythm and I repeat it right away. It compares my stress and intonation with its own.
7. **Sound drills:** pairs like *vest/west*, *thin/tin*, *ship/sheep*, chosen for my weak sounds.
8. **Daily-life role plays:** calling customer care, small talk, an office stand-up update, disagreeing with a manager.
9. **Debate:** the coach takes the opposite side of my opinion.

**A daily session (10–15 minutes)**
1. **Warm-up (2 min):** shadowing with my weak sounds.
2. **Main (8 min):** a conversation, interview or group discussion on a topic from today's news.
3. **Feedback (3 min):** only the top 3 fixes, plus one short drill.

```
🎙️ Mock interview · 8 min
Fluency: 132 words/min · 14 fillers (1.8/min, down from 2.6)
Grammar: 5 errors · 3 past tense, 2 articles (a/the)
Pronunciation: "photography" (stress), "world" (w), "comfortable"
Vocabulary: "very" used 9 times · try "extremely", "highly"
Structure: 2 of 5 answers had no example
Next drill (5 min): past tense + v/w sound pairs
```

**The voice screen (in the web app)**
- **A 3D orb that moves with the real sound:** it breathes when idle, reacts to my voice while listening, and pulses with the coach's voice while it speaks.
- **My live waveform** and **live captions** for both voices; corrections still wait until the end.
- **Read-aloud mode:** words light up as I read; afterwards each word is green, amber or red, and tapping one plays the correct version next to mine.
- **Shadowing mode:** my pitch curve drawn over the coach's, to show where my intonation differs.
- **Session report:** my recording as a waveform with fillers and mispronounced words marked, grammar fixes as before and after, and trend charts.

Details are in section 5.14 of [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md).

**It remembers me**
- **Error profile:** my repeated mistakes (for example articles, past tense, *v/w*), with drills aimed at them.
- **Mistakes come back:** corrected sentences and mispronounced words become flashcards until I get them right 3 times in a row.
- **Progress charts:** fillers per minute, words per minute, pronunciation score, grammar errors per 100 words.
- **Monthly before/after recording:** "Tell me about yourself" once a month, so I can hear month 1 next to month 3.
- **Uses my Brain:** news topics, my projects for interviews, my STAR stories.
- **Explains hard grammar rules in my mother tongue** when I want.

**Design rules**
1. **Don't interrupt; correct afterwards.** Constant corrections kill confidence. Conversations stay natural; strict "stop at every error" mode is only for drills.
2. **Three fixes per session, not thirty.**
3. **Accent: aim for clear, not foreign.** An Indian English accent is completely fine. The coach fixes the sounds and stress that cause misunderstandings; an American or British target is optional.
4. **Check before correcting.** Speech recognisers make mistakes too, especially with Indian accents. If the recogniser wasn't sure about a word, the coach asks me to repeat it instead of marking me wrong.

**How it would be built**

> **Update:** the current plan runs the Voice Coach locally on the Linux server's GPU (ASUS TUF A15, RTX 3060) (faster-whisper, Kokoro, a wav2vec2 phoneme model with forced alignment, and Pipecat), with Azure and cloud voice models only as optional backups. See [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md).

- **Version 1: voice notes (start here).** Telegram voice note → transcribed on my Mac → pronunciation scored → AI analysis → feedback as text and audio. No real-time complexity.
- **Version 2: live conversation,** built with LiveKit Agents or Pipecat, using either:
  - **a speech-to-speech model** (gpt-realtime-2.1 or Gemini 3.8 Live), which feels most natural and fast, or
  - **a pipeline:** speech-to-text (Deepgram) → Claude → text-to-speech (ElevenLabs).

  In both cases a **separate analysis track** records my audio and scores it, because conversation models are not reliable graders.

**Technical traps (also good interview material)**
- **Transcribers hide mistakes.** Whisper and most speech-to-text tools drop "um/uh" and quietly fix grammar. I need verbatim transcription: Deepgram has a filler-words option, and Whisper can be prompted to keep fillers.
- **Pronunciation scoring needs its own tool.**
  - **Cloud APIs** (Azure AI Speech Pronunciation Assessment, SpeechSuper, Speechace) give sound-level scores and are the most accurate.
  - **Open-source** (wav2vec2 phoneme models plus forced alignment) is private but harder to build and less accurate.

  Start with the cloud option, using practice recordings only.
- **Cost.** Live voice is billed per minute. Set a daily budget, use a cheaper model during the conversation, and a stronger one for the analysis afterwards.

**Privacy and safety**
- **My voice is personal data.** Recordings stay on my Mac, and raw audio is deleted after analysis, except the monthly before/after recordings I choose to keep.
- **For cloud APIs,** send practice audio only, and turn off data retention or training where the provider allows it.
- **No voice cloning on cloud services.** Hearing the correct sentence in my own voice does help learning, but a stored copy of my voice could be misused for scams.

**Limits**
- **It can't judge body language, eye contact or real nerves** in front of real people. I still practise with people every week.
- **Apps like ELSA Speak and Speak already do parts of this.** I can use one while I build, so my English improves from day one. Building my own is goal-1 training, and it can use my own news, projects and mistakes, which those apps can't.
- **It's big enough to be its own project:** a module that shares the Brain but can be built and demoed on its own, starting with version 1.

### Jarvis: the main way I use the app

**One voice assistant, called Jarvis, for the whole app.** I talk and it does the job: no modes to pick, no typing.
- **Behind the scenes:** the modes still exist (news, tutor, quiz, planner, interview, English coach), but Jarvis picks the right one from what I say.
- **The other parts stay:** the web app, Telegram and Obsidian are there for reading, charts and alerts.

```
Me:     "Jarvis, what's happening in tech today?"
Jarvis: "Three big things today. The first one matters for you, because it changes
         something you studied last week. Want the details, or should I quiz you later?"
Me:     "Tell me about it, then add it to tomorrow's plan."
Jarvis: "…Shall I add 30 minutes on it tomorrow at 7 pm?"
Me:     "Yes."
Jarvis: "Done. Shall I make flashcards from it?"
```

**My decisions**

| Topic | Decision |
|---|---|
| Name and voice | Jarvis, with a calm British male voice *style*, not a copy of any real actor's voice |
| Starting a conversation | Laptop: always listening for "Hey Jarvis", detected on the laptop itself. Phone: tap the orb (a phone wake word needs a native app later) |
| English coaching | Off by default. I decide when: "Jarvis, coach my English", or my set practice time. Soft skills come second |
| Proactive | When I open the app, Jarvis speaks first ("Good morning, 3 things today…") and suggests what to learn. Urgent alerts also come through Telegram |
| Language | English only |

**What I can ask:**
- **News:** "What's new today?" or "Anything in tech?"
- **Understanding:** "Explain this properly" or "Why does that matter?"
- **My notes:** "What did I read about RBI this week?"
- **Tutoring:** "Teach me deadlocks tonight", which runs a one-evening session: map → explain → I explain back → practice → summary and cards.
- **Practice:** "Quiz me", "Do my cards", "Interview me for SBI", "Coach my English".
- **Plan and library:** "What's my plan today?", "Add 1 hour of polity tomorrow", "Mark chapter 4 as read".
- **Exams and progress:** "When is the SBI PO form due?", "How am I doing in GATE?"
- **The server:** "How's the server?"
- **Stopping it:** "Stop", or simply talking over Jarvis.

**What it may do:**
- **Read** anything in the app, at once.
- **Change things inside the app** only after it says exactly what will change and I say "yes" within 10 seconds.
- **Never:**
  - send messages
  - buy anything
  - change settings
  - delete data
  - act outside the app

  No such tools exist.

**Honest limits:**
- **The server must be on:** the server laptop must be on and in Linux.
- **Speed:** simple replies take about 1–2 seconds (estimate). Hard questions get "Let me think about that" and go to the bigger model.
- **Shared GPU:** while I talk to Jarvis, other model jobs wait.
- **Smart, not a genius:** it's a smart assistant from my own notes, not a genius.

Details: [06_Improvements.md](06_Improvements.md) Part C, [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md) §5.15, [05_Architecture.md](05_Architecture.md) §7.17.

### Study material: books, videos and exam knowledge

**The principle: the database stores everything, and flashcards stay small.**
- **Everything is stored:** every page or minute of what I add is stored and searchable, with page numbers or timestamps. Answers, summaries and questions always come from there.
- **Flashcards are few:** they train my memory for the exam hall, so there are only 10–20 key facts per chapter I've marked as read, plus every mistake I make. A 300-page book ends up with about 150–300 cards over months, not 1,000 at once.
- **Daily limits:** 10 new cards and 40 reviews a day by default. I can change them, and exam mode can raise the reviews.
- **"Mark chapter as read"** (in Telegram, on the Library screen, or by voice):
  - creates that chapter's cards
  - starts revisions at +1, +7, +30 and +90 days
  - adds the chapter's MCQs to my quizzes
- **Cards point to their source:** "show source" opens the exact page or video moment. When a fact changes, its cards are updated, never left stale.
- **Big files:** I drop them in the Library folder on my Mac, and they're processed overnight.

  | Source | Time |
  |---|---|
  | 300-page PDF | 10–20 minutes |
  | 1-hour video | 5–10 minutes |
  | Full study pack | 1–2 nights |

- **Example:**
  1. **Monday:** I drop *Indian Economy.pdf* into the Library folder.
  2. **Tuesday 06:30:** "Ready: 10 chapters, summaries in your vault."
  3. **Tuesday evening:** I read chapter 1 and tap **Mark chapter as read**, which creates 15 cards and revisions on Wednesday, +7, +30 and +90 days.
  4. **Other chapters:** they stay fully searchable but create no cards until I read them.

**Where exam knowledge comes from**

| Layer | Where from |
|---|---|
| Syllabus | Official exam notifications |
| Past papers and answer keys | Official exam websites |
| Study material | NCERT, NIOS, NPTEL, MIT OpenCourseWare, RBI, Budget and PIB documents, and books I own |
| Practice | Past papers, drills computed by code, checked MCQs |
| Current affairs | The daily news pipeline |

- **A starter pack:** a list of official and open links, which I approve before anything is downloaded. It takes about one weekend of overnight processing.
- **Rules:**
  - **Official sources first.**
  - **Bank exam papers:** IBPS and SBI rarely publish theirs, so "memory-based" papers are labelled unverified.
  - **No pirated PDFs, ever.**
  - **Material is for my personal study only.**

Details: [06_Improvements.md](06_Improvements.md) Parts A and G.

### Answers in my way: an app that learns from me

**The core rule: "my way" changes the form, never the facts.** Facts, numbers and sources stay the same whatever my preferences. Only these change:
- length and format
- depth and order
- examples and memory tricks
- what's skipped because I already know it

**How it learns:**
- **Five layers:**
  - a style profile for each mode (from a 5-minute setup)
  - my level on each topic
  - answers I liked, used as style examples
  - what I usually ask after an answer
  - things prepared before I ask
- **Feedback:** 👍/👎 and buttons like "Too long", "Wrong" or "Not relevant" on digest items, answers, summaries, cards, MCQs and voice feedback. Also what I open, skip, save and score.
- **A weekly improvement report (Sunday):**
  - up to 3 suggested changes, each with its evidence ("You shortened 6 of 7 summaries. Keep them under 5 lines?"), to approve or ignore
  - small automatic changes listed
  - everything can be undone

**Example: "What is repo rate?"**
- **SSC mode:** a one-line fact and a memory trick.
- **Economy mode:** why RBI changes it, and what it does to a loan EMI.
- **Already mastered:** only what's new.

The fact is identical in all three.

**Safety:**
- Only my own clicks count.
- Rules can only change style.
- Politics and economy stay balanced.
- Weak exam topics are never hidden.
- A **"My profile"** page shows everything the app has learned, and I can delete any of it.

**The models themselves don't retrain:** the system around them learns. Fine-tuning is a later option only, after about 6 months of data.

Details: [06_Improvements.md](06_Improvements.md) Part B.

### Staying safe

The app is built so one mistake isn't enough to cause damage:
- **No doors from the internet:** nothing on the server is reachable from outside, only from my own devices through my private network.
- **One checked door for data:** every PDF, page, video and file passes the Intake Gateway. It checks and rebuilds each one, and flags or quarantines anything suspicious before the rest of the app sees it.
- **Alarms if something gets through:**
  - fake passwords (honeytokens) that only an attacker would touch
  - container monitoring
  - nightly integrity checks

  A compromised container is stopped after its evidence is saved. Every morning a separate alert bot sends "✅ All quiet"; if it doesn't arrive, something is wrong.
- **Jarvis can't be tricked into acting:** only my spoken words choose actions, every change needs my "yes", and it ignores its own voice.

**What depends on me:**
1. **Passkeys** (or an authenticator app, never SMS) for GitHub and Tailscale, plus Telegram's cloud password.
2. **Keep the Windows side clean:** no cracked software.
3. **Never log in from a link.**
4. **Approve coding-agent commands carefully,** and review every change.
5. **Lock the screen,** and keep updates on.
6. **No web browsing on the server laptop.**
7. **Once a month:** check Telegram's "Active sessions" and the Tailscale and Syncthing device lists.

**References:**
- **Attack types:** all 61, with their defences, are in [07_Attack_Types.md](07_Attack_Types.md).
- **Security controls:** they're in [05_Architecture.md](05_Architecture.md) §10.

### Extra features

These plug into parts the app already has (Radar, Brain, Practice, Planner, Jarvis), so they are add-ons, not new systems.

**Exam strategy**
- **Mock test analyser** *(Planner)*: I send a screenshot of any mock test scorecard. The app shows accuracy by section, where I lost time, and silly mistakes versus gaps in concepts. It also compares my score with previous years' official cutoffs, for example: "You're 12 marks below last year's cutoff; quant is where you can gain the most."
- **Topic weightage** *(Brain)*: which topics come up most in each exam, so I study the high-scoring ones first. For GATE it comes from the official past papers; for SSC and bank exams, from free post-exam analyses that count questions per topic.
- **Speed maths drills** *(Practice)*: two-minute daily drills (tables, squares, cubes, percentage ↔ fraction, approximation), because speed decides the score in SSC and bank exams. Also typing practice for the data entry test in SSC CGL Tier 2.
- **Revision calendar (1–7–30–90)** *(Planner)*: every topic I study comes back for revision after 1 day, 7 days and 30 days, and exam topics again after 90 days, so a big syllabus like GATE doesn't fade.
- **Final 30 days mode** *(Planner)*: before an exam, the app switches to revision only: no new topics, daily mini mocks, one-page formula sheets, and the recent current-affairs capsules.

**Study smarter**
- **Handwritten notes become searchable** *(Brain)*: I photograph my notebook pages, and they become searchable notes linked to the right topics, with formulas kept.
- **Study time tracker** *(Planner)*: I send "/start GATE OS" on Telegram when I begin and "/stop" when I finish. The weekly review shows planned versus actual time for each goal, so a neglected goal shows up early.
- **Study group mode** *(Practice)*: the bot joins a Telegram group with my friends for a daily current-affairs quiz, a leaderboard, and weekly group discussions with real people. It gives accountability, plus the real-people practice the Voice Coach can't give.

**Understand the world**
- **My economy dashboard** *(Radar)*: inflation, repo rate, GDP growth, the rupee against the dollar, and petrol and gold prices as simple trend charts from reliable data (RBI and MOSPI for rates, inflation and GDP), each with a plain-language "what changed this month". I understand the economy, and bank exams ask exactly these numbers.
- **Forward fact-checker** *(Radar)*: I forward a WhatsApp message or viral post to the bot. It answers *true*, *false* or *unverified*, with sources and any existing fact-checks. Useful every day, and it trains my own eye for fake news.

**Me**
- **"Know yourself" pack for interviews** *(Jarvis)*: bank panels often ask about my home district and state, my degree and my hobbies. The app builds a page on each (my district's economy, crops, industries and culture; the basics of my degree subject; my hobbies in depth), and the Voice Coach quizzes me on them.
- **Energy check-in** *(Planner)*: one tap a day for sleep, energy and mood; the data stays on my Mac. The weekly review shows patterns like "accuracy drops when I sleep under 6 hours". With five goals, burnout is a real risk, and the app should notice before I crash.

**Safety note:** photos, screenshots and forwarded messages are untrusted input, just like web pages. They go through the same sandbox and reader/writer split as everything else.

### A morning with the app (sample)

```
🗣️ Jarvis: "Good morning. Three things today…" (when I open the app)
🛡️ Security: ✅ All quiet (the alert bot's heartbeat)
☀️ Good morning
🔋 Check-in: sleep, energy, mood (1 tap)
📰 Radar (10–15 min): 5 items explained, 3 tagged for exams
💭 My take: one line on today's top story
📝 Current affairs quiz: 10 MCQs from this week
🧮 Aptitude: 10 quant + 10 reasoning (timed)
🔤 English: 5 new words + 10 grammar questions
🎙️ Voice Coach (10 min, my set practice time): mock interview on today's top story
🎓 GATE topic: OS → Deadlocks (notes + 5 past questions)
💻 Build: LifeLedger, Phase 1, step 3
🔁 Reviews due: 18 flashcards + 1 topic revision (7-day)
📅 Alert: an exam application closes in 6 days
```

### Ground rules

- **Understanding first, exams second.** I learn a topic once, deeply; exam facts and MCQs come from the same reading.
- **The exam that comes first gets the most time.** The planner needs the exam dates and sets priorities from them.
- **Every AI-made question gets checked.** A wrong fact learned for an exam costs marks. Prefer official past papers, build current-affairs facts only from news confirmed by several independent sources, check maths answers with code in the sandbox, and label AI-made questions *unverified* until checked.
- **No pirated or scraped coaching content.** The app uses official past papers, open material (NCERT, NPTEL), public news and my own notes. Anything I legally own, I add myself through the Library folder.
- **"My way" changes the form, never the facts.** My preferences shape how answers look, not what's true.
- **Only my own words or clicks make the app act or learn.** Text inside news, PDFs or videos never can.
- **Jarvis asks before changing anything,** and every change can be undone.
- **Facts kept apart from opinions,** especially in politics. The app never tells me what to think.
- **Explain finance, never advise.** The app explains how markets work but never tells me what to buy or sell; that's a job for a licensed advisor.
- **Practise with real people every week.** The app prepares me, but soft skills grow with people: mock interviews with friends, a study group, or a public-speaking club like Toastmasters.
- **The briefing stays short (10–15 minutes).** The app should cut my reading, not add to it.
- **Building must not eat study time.** Build the smallest useful version first, use it daily, then grow it.
- **The security rules still apply** (see [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md) and the Radar + Brain section below): official APIs and RSS only, untrusted content handled in the sandbox, no passwords in the app.

### Suggested build order

0. **Safety first (with the foundation):** honeytokens, the daily heartbeat, alarms for unexpected outbound traffic, passkeys and Tailnet Lock. Nightly integrity checks follow, and container monitoring (Falco) comes last, after two weeks of tuning.
1. **Vault skeleton:** syllabus trees (GATE, SSC CGL, bank exams), the skill map from my stack docs, empty foundation pages (economy, finance, politics, world, GK) that fill up over time, and `CLAUDE.md`. No AI needed.
2. **Daily briefing** where each item answers the four questions, with exam tagging and the monthly capsule. Every input passes the Intake Gateway from the start.
3. **Practice on Telegram:** MCQs from the news, daily grammar questions, vocabulary from my reading, flashcards with spaced repetition (with daily limits), and the mistakes notebook.
4. **Exam notification watcher.**
5. **Library:** big PDFs and videos, chapter summaries, "Ask this PDF", "Mark chapter as read", and the exam starter packs.
6. **Daily plan and progress view,** with the 1–7–30–90 revision calendar, the study time tracker and the energy check-in.
7. **Voice Coach version 1:** Telegram voice notes with feedback.
8. **Understanding tools:** weekly deep dive, growing glossary, story timelines, and the opinion and prediction log.
9. **Economy dashboard** and **forward fact-checker**.
10. **GATE past-paper tracker,** sources linked to every syllabus topic, the daily timed aptitude set, and speed maths drills (with typing practice).
11. **Exam strategy:** mock test analyser, topic weightage, and final 30 days mode.
12. **Handwritten notes to searchable notes,** and study group mode.
13. **Voice Coach version 2:** live conversation, mock interviews, group discussions, and the "Know yourself" interview pack.
14. **Tech extras:** release digest, "Rising fast" trends, and MCP access for Claude Code.
15. **Answers in my way:** feedback buttons, the weekly improvement report and the "My profile" page.
16. **Jarvis:** one voice assistant for everything.
17. **Later:** connect to LifeLedger.

Steps 1–4 make the first usable version. Each later step is added only after the earlier ones are in daily use. The order may change once I know which exam comes first.

**Jarvis comes late** because it's the voice front door to every other part, and each skill it calls must exist first. A smaller Jarvis (news, ask, plan) could come right after step 13 if I want it sooner (an open question below). The matching build phases are listed in [05_Architecture.md](05_Architecture.md) §11.1.

## The original idea in one paragraph

TechRadar Brain is a personal "second brain" for tech learning. Notes are plain Markdown files on your Mac, which you read in Obsidian. You send it links, PDFs, videos, images and voice memos (mostly through a Telegram bot). An AI pipeline turns each one into a short, linked wiki page and flashcards. Claude Code can read the notes while you code, and every Sunday you get a digest of new releases for the tools you use.

## Earlier update: Radar + Brain

**The real problem:** missing what's happening, not storing knowledge. Example: everyone was talking about Rust for 2 weeks before I heard about it. I want to know about any important update by the next day, not only in tech but in every area (politics, GK, world events, breakthroughs), from X, LinkedIn, YouTube, blogs and other platforms, handled safely.

So the app has two layers, which is exactly what the name says:
- **Radar:** daily awareness. Know what's happening.
- **Brain:** depth. Keep only what matters, as linked notes.

### A mindset note first

- Nobody knows everything by the next day. People who seem to follow 2–3 areas closely and skim the rest.
- Being 2 weeks late usually costs nothing. If something matters, it still matters next month; if it disappears in 2 weeks, it was hype.
- Consuming every feed makes the "I'm behind" feeling worse.
- **Goal:** never miss what matters, and safely ignore the rest.

### Layer 1: Radar (daily briefing, 10 minutes max)

Every morning, one briefing on Telegram:

```
☀️ Today's Radar: Nov 8

🔥 Rising fast (new this week)
  • Rust: mentioned in 40 sources, up from 5 last week → [Go deeper]

💻 Your stack
  • LangGraph 1.3 released: adds X
  • Spring Boot security patch: update recommended

🌍 World & India
  • 3 headlines, each confirmed by 3+ outlets

🧠 GK / science / other
  • 2 notable items
```

**Key feature: "Rising fast" (trend detection).** The app counts how often each topic is mentioned across all sources per day. When a topic suddenly jumps, it alerts me. This would have caught Rust on day 1–2 instead of day 14. I don't have to read everything; the app watches the trends.

### Layer 2: Brain (depth, only what I choose)

Tapping **[Go deeper]** on any briefing item turns it into a proper note in the second brain: summary, links to related notes, and my own takeaway. Everything else fades away without guilt.

### Where the information comes from

| Platform | How | Notes |
|---|---|---|
| Blogs, news sites | RSS feeds | Easiest and most reliable |
| YouTube | Channel RSS feeds for new-video alerts | The official API gives video details, not other people's transcripts; unofficial caption libraries may break and are a grey area under YouTube's terms |
| Hacker News, Reddit, GitHub Trending | Official APIs | Great early signal for tech |
| Google News | RSS by topic | Politics, GK, world news |
| X (Twitter) | Official API is very expensive | Use RSS bridges for specific accounts, or follow those people's blogs and news |
| LinkedIn | No public feed API; scraping breaks their rules | Account ban risk. Skip it, or save posts by hand through Telegram |

### Security concerns

- **Official APIs and RSS only.** Never log in to my real X or LinkedIn accounts from a bot (bans, leaked passwords).
- **No social media passwords in the app.** API keys live in a separate secrets file, never in code.
- **Everything fetched is untrusted.** Same reader/writer agent split and Docker sandbox as the main design, because a page can hide instructions aimed at the AI.
- **Misinformation filter.** Something counts as "news" only when multiple independent sources report it, and the briefing shows the source count.
- **Balance for politics.** Pull from outlets with different viewpoints so the app doesn't become an echo chamber.

### Recommended scope and build order

1. Start with **tech + 1–2 other areas** (for example world news and science). Add politics and GK once the briefing feels manageable.
2. Keep the briefing to **10 minutes a day**. If it gets longer, the app has failed, not me.
3. Build order:
   1. RSS and news feeds
   2. YouTube and Hacker News
   3. Trend detection ("Rising fast")
   4. "Go deeper" into the Brain
   5. Other platforms

## A normal day with TechRadar Brain

### Morning (commute or coffee, 5 min)
- **Capture instead of "watch later".** You see a LinkedIn post or YouTube video about a new AI tool. Share it to the Telegram bot in two taps.
- **It reads it for you.** A few minutes later you get a reply like: "Saved: *What's new in LangGraph 1.2*, 5 key points, linked to your LangGraph note." You don't have to watch the 40-minute video right now.

### During study or coding (afternoon)
- **Ask your own notes.** Stuck on a concept such as "how does Temporal resume after a crash?" Ask Claude Code. It answers from *your* notes, in the words you already understood once, instead of you Googling again.
- **Keep project context.** Building LifeLedger and forgot why you chose Pydantic AI? Claude reads your decision note and reminds you, so you don't re-explain context every session.
- **Drop in documents.** Put a good PDF or docs page in the folder and it becomes a clean, searchable page linked to related topics.

### Evening (10–15 min)
- **Browse what's new** in Obsidian, already connected to what you know.
- **Review 10 flashcards** made from this week's reading, so knowledge sticks for interviews.
- **Voice-memo ideas:** "Idea: LifeLedger could detect duplicate subscriptions." It's transcribed and filed under `projects/`.

### Sunday
- **One digest message:** "This week: FastAPI 0.163 released, LangChain 1.5 adds X, Spring Boot 4.1 patch." You stay current without following 20 accounts or checking registries by hand.

### Before an interview
- **Ask for a revision pack:** "Give me everything I know about RAG and MCP." You get your own summarised notes plus flashcards, built from months of reading.

## What changes

| Today | With TechRadar Brain |
|---|---|
| Saved links you never reopen | Every link becomes a short, readable note |
| Re-Googling the same concepts | Asking your own notes |
| Forgetting what you studied last month | Flashcards keep it fresh |
| Checking release notes and versions by hand | One digest every Sunday |
| Re-explaining context to Claude | Claude reads your notes directly |

## Why it helps beyond daily use

- **Job prep:** flashcards and revision packs for interview topics (RAG, MCP, agents, LangGraph vs Temporal).
- **Resume value:** shows RAG, MCP, agents, scheduled automation and safe handling of untrusted web content. You use it several times a week, so you can talk about it from real experience.
- **Pairs with LifeLedger:** LifeLedger shows workflows and finance data; TechRadar Brain shows knowledge, retrieval and security. Together they cover most of an AI automation job description. Using LangGraph here (LifeLedger uses Pydantic AI + Temporal) shows both frameworks.

## The honest catch

- **It only helps if you feed it.** At 3–5 items a week it becomes really valuable after a month or two. With nothing sent in, it's an empty notebook.
- **If you rarely save content,** plain Obsidian plus Claude Code (Levels 1–2, no pipeline) gives most of the value in a weekend.

## Open questions (answer before building)

1. Which exam comes first (GATE, SSC CGL or a banking exam), and roughly when? This sets the planner's priorities and the build order.
2. GATE paper: Computer Science (CS) or Data Science and AI (DA)?
3. Which banking exams exactly (for example SBI PO, or IBPS RRB officer and manager posts)?
4. Where do you usually find tech content (YouTube, LinkedIn, blogs, courses, PDFs), and how much per week? This decides which capture path gets built first.
5. Tech decisions (Linux distro, disk encryption, server power mode, fully local or a small cloud backup, phone type, RAM upgrade): see section 11 of [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md).
6. Voice Coach accent target: clear Indian English (default), British or American?
7. Rename the project? "TechRadar Brain" now covers far more than tech.
8. When should Jarvis come: last, or a smaller Jarvis (news, ask, plan) right after live voice? **Decided 2026-11-08:** last, as phase 12 (06 I5).
9. Which textbooks do I already own, and which NPTEL courses go in the first starter pack?
10. More open questions are listed in [06_Improvements.md](06_Improvements.md):
    - B11: feedback and learning
    - C10: Jarvis's personality, memory and quiet hours
    - F10: how strict the Intake Gateway should be
    - G7: exam sources
    - H11: alerts and containment

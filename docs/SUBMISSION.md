# Project submission guide

## Project identity

**Title:** Margin: Document Question Answering with Source Citations  
**Assignment:** Option 1, RAG Chatbot over Documents  
**Author:** [Add your name]  
**Google program / cohort:** [Add the exact program name]  
**Repository URL:** [Add after publishing]  
**Live application:** https://margin-rag.vercel.app  
**Demo video URL:** [Add after recording]

The backend is Python/FastAPI and is hosted in the same Vercel project as the frontend. Read `docs/DEPLOYMENT.md` for storage ownership and your friend's handoff.

The assignment screenshot is the available specification. Confirm any additional program rules, permitted assistance, originality requirements, and deadlines in your actual submission portal.

## Short project description

Margin lets a reader upload PDFs and ask questions about their contents. It extracts text page by page, creates overlapping chunks, embeds them with a local BGE sentence model, and stores the vectors in SQLite. A question is embedded and compared with the selected documents using cosine similarity. When Gemini is configured, the app generates an answer from the retrieved passages and validates each cited source reference and supporting quote. Readers can inspect the quoted passage and download the original PDF.

The app also has a credential-free evidence mode that returns an exact source passage. That mode is useful for testing retrieval, but it is not a replacement for the assignment's generated-answer requirement.

## Requirement mapping

| Screenshot requirement | Implementation | Evidence |
| --- | --- | --- |
| Ingest and chunk PDFs | `app/rag.py`: `chunks_from_pdf` retains pages in 900-character chunks with 150-character overlap | Sample corpus, chunking/API tests |
| Embeddings and a vector store | FastEmbed BGE-small, normalized vectors persisted in SQLite. NumPy exact cosine search | `app/rag.py`, `app/store.py`, retrieval evaluation |
| Generate answers with citations | Gemini claims reference retrieved sources. Quote text must exist in the cited passage | `answer` in `app/rag.py`, mocked response tests. Live run still required |
| At least 20 questions, including unanswerable ones | 24 development questions: 18 supported, 6 unsupported | `evaluation/questions.json`, `evaluation/results.json` |
| Trace answers to passages | Filename, page, quote, similarity, original PDF download | Browser screenshots, source-citation/API tests |

## Results you can state now

The recorded local evaluation used three fictional PDFs with nine pages total. The expected source and page appeared among the retrieved passages for all 18 supported questions. Five of the six unsupported questions returned no passages. The GPU-brand question retrieved a compute policy that does not identify a brand, showing why similarity alone cannot determine whether a question is answerable.

The latest live Gemini evaluation passed all 24 development checks: 18 supported answers and 6 abstentions. The public deployment was also checked for a generated capstone-deadline answer citing page 3 and refusal of the unsupported GPU-brand question. Reports are in `evaluation/gemini-results.json` and `artifacts/gemini-live-checks.json`. An earlier key failed because its credits were depleted; it was replaced with the working key. Do not describe retrieval recall or this fixture result as general answer accuracy. These questions were developed with the sample corpus and are not a held-out benchmark.

## Finish before submitting

- [ ] Add your name and the exact program details above.
- [ ] Check whether your program requires disclosure of AI assistance, and disclose this build accordingly.
- [ ] Read the implementation and be prepared to explain each stage yourself.
- [ ] Set a Gemini API key locally and restart the server.
- [ ] Confirm that an actual answer is marked `Gemini · generated answer`.
- [ ] Run `uv run python -m scripts.evaluate --gemini` and inspect every generated answer.
- [ ] Confirm that unsupported questions, especially the GPU-brand question, are refused.
- [ ] Add questions based on your own authorized PDFs. Keep some questions separate from development tuning.
- [ ] Record the demo below. Keep API keys and personal information out of the recording.
- [ ] Run tests and lint again. Review the dependency audit and any remaining limitations.
- [ ] Publish only the intended source and sample data. Do not upload `.env`, `data/`, `.cache/`, or `.venv/`.
- [ ] Run `uv run python scripts/package.py` after the final Gemini report is saved.
- [ ] Check the ZIP contents and submit through the program's actual portal.

## Suggested demonstration, about four minutes

### 0:00–0:35 · Explain the problem

“Searching a PDF by keyword can miss the passage you need. This project retrieves relevant passages with sentence embeddings and makes each answer traceable to a page.”

Open the workspace and show the selected source documents. State whether the demonstration uses Gemini or local evidence mode.

### 0:35–1:15 · Show ingestion

Upload an authorized text PDF or load the fictional sample workspace. Show the number of documents and the page count, alongside the indexed passages. Explain that chunks never cross page boundaries, which makes page-level citations possible.

### 1:15–2:00 · Ask and verify

Ask: **When is the capstone submission deadline?**

The sample handbook states **23 October 2026 at 5:00 PM on page 3**. In Gemini mode, show the generated answer, open its citation, and compare the supporting text with the original PDF. Do not call the similarity value a confidence score.

### 2:00–2:40 · Test a missing fact

Ask: **What brand of GPU does the research lab use?**

The documents contain a GPU-hours policy but no brand. A grounded generated answer should refuse to provide a brand. Explain that local evidence mode may show the related policy without claiming to answer the question.

Then ask an unrelated question, such as **Who won the football world cup in 2018?** The app should not use general knowledge to answer it.

### 2:40–3:20 · Show scope and evaluation

Select only `library-guide.pdf` and ask **How many books can I borrow?** Verify the answer against page 1: **5 books**.

Show the 24-question dataset and the recorded JSON report. If you have completed the Gemini run, show that report separately from the local retrieval report.

### 3:20–4:00 · Explain tradeoffs

Explain the choice of a local embedding model, SQLite vectors, and exact search for a small corpus. Describe one improvement you would make next, such as OCR for scans, held-out evaluation, or authenticated multi-user deployment. State that citation checks cannot prove semantic entailment.

## Questions to prepare for

**Why use overlapping chunks?**  
A fact near a chunk boundary can lose context. A small overlap keeps some neighboring text while each chunk retains a page reference.

**Why SQLite instead of a hosted vector database?**  
The submission corpus is small. Storing vectors with the document metadata keeps the project easy to run and inspect. Exact search is linear in the number of chunks and should be replaced with an indexed vector store when corpus size or measured latency warrants it.

**How do you handle hallucinations?**  
Only retrieved passages are supplied to Gemini. The prompt requires refusal when evidence is missing. Each returned claim must reference a retrieved passage and include an exact quote from it. These checks reduce some citation errors but do not establish that a claim is true or entailed by its quote. Human review is still needed.

**How is user data separated?**  
A high-entropy cookie identifies a workspace. Every document query and mutation is scoped to its owner in SQLite. This is anonymous local isolation, not production authentication.

**What does the evaluation measure?**  
The local report measures expected-source/page retrieval at five passages and records the behavior on unsupported questions. The optional Gemini report adds expected-phrase/citation checks and refusal checks. Neither result is a general accuracy guarantee.

## Materials included

- Application source and locked Python dependencies.
- Three fictional PDF fixtures and their editable generator.
- A 24-question evaluation dataset and recorded local results.
- API regression tests, browser screenshots, and verification notes.
- Windows start scripts, an untested Docker recipe, and an unexecuted CI workflow.

The public demo is deployed at https://margin-rag.vercel.app. There is no published GitHub repository, recorded video, or completed Google submission in this handoff. No ownership transfer has been initiated. Those remaining steps require your account details and approval.

# IdeaCheck

**Find what your plan forgot.** IdeaCheck reviews a project idea or plan for potential omissions, assumptions, constraints, risks, and unanswered questions. It focuses on the supplied project material; it does not compare the idea with other projects.

## Start locally

Python 3.10+ is required. From the project directory:

```sh
make env
make demo
```

Open <http://127.0.0.1:8000>. Paste a public GitHub repository, Render deployment, or other website URL and choose **Review link**; or enter a project description / choose **Try the MessMind example** and select **Review my project**. Stop the server with Ctrl+C. The rules-based review needs no API key or model download. An optional AI review runs with free Ollama software and a model on your own computer; it is off by default. The computer running the app needs internet access for URL reviews.

The app fetches public web pages over HTTP(S), extracts readable text, then runs deterministic local rules over that text. If you enable the optional AI review, it also sends the extracted text only to Ollama on `127.0.0.1`; it does not call a hosted AI API. For GitHub repository links it reads the repository's public `README.md` directly, without using the GitHub API. URL fetches are limited to 1.5 MB and standard web ports; local/private addresses are rejected. A 75-second connection timeout allows sleeping Render services time to wake. The app does not execute JavaScript, inspect source code, or follow linked pages, so client-rendered sites may not expose enough text. It also recognizes simple CSV-shaped pasted data and calculates a small profile. Reports are saved in `data/novelty_coach.sqlite3` and can be exported as Markdown or JSON or deleted from their results.

## Current review

The first-pass checks look for missing or unclear success measures, user validation, dependency failure behavior, data handling, testing, ownership/timing, dataset field definitions, and a few direct contradictions. Findings include a source-context excerpt or are explicitly labeled as a documentation gap. A documentation gap does not prove that the real project lacks a capability.

Risk score is `impact × likelihood`, each rated 1–5. The displayed categories are heuristic thresholds: Critical 20–25, High 12–19, Medium 6–11, Low 1–5. Confidence is shown separately. Scores are not calibrated failure probabilities. Recommendations include a practical next step and a way to validate the concern.

## Optional free local AI

Install [Ollama](https://ollama.com/download), start it, and download the default model:

```sh
ollama pull qwen2.5:1.5b
```

Restart IdeaCheck if it was already open, then select **Add a local AI review**. The model runs on the same computer as the backend, so its speed depends on your hardware and it uses local storage for the model. To choose another installed Ollama model, set `OLLAMA_MODEL` before starting IdeaCheck.

## Privacy and limitations

Pasted text is processed locally by deterministic rules. If the optional AI review is selected, the app sends it only to the Ollama service on the same computer, not to an external AI provider. For URL reviews, the app server makes a request to the public URL you submit; extracted text and the report are stored in local SQLite. This app does not encrypt that database. Delete a report from its results when it is no longer needed.

This is an early, rules-based product-document review with an optional local AI second opinion; it is not a guarantee of safety, correctness, compliance, or project success. The AI can make mistakes. Exact quotes are checked against the submitted text, and other AI suggestions are labeled as inferences. It currently accepts pasted text (up to 20,000 characters) or one public page URL; direct TXT, Markdown, PDF, and DOCX uploads, a full statistical dataset auditor, workflow diagrams, finding status/notes, question answers, CSV exports, and version comparisons are not implemented yet. Dataset support is limited to a small CSV profile when tabular text is pasted.

## Development

```sh
make test
python3 -m compileall -q app tests
node --check web/app.js
```

The interface is plain HTML/CSS/JavaScript served by FastAPI. The rules engine is in `app/probe.py`; report jobs and export endpoints are in `app/main.py`; tests are in `tests/test_probe.py` and `tests/test_jobs.py`.

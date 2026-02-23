# JobScout — Resume Guide

How to build ATS-optimized resumes for data engineering, ML engineering, and
software engineering roles. Fork-friendly — replace all examples with your own experience.

---

## Resume Naming Conventions

Name your resume files with a role suffix so the tracker knows which version you used:

| Suffix | Role |
|--------|------|
| `_DE` or `_data` | Data Engineering |
| `_SWE` or `_SE` | Software Engineering |
| `_AE` | Analytics Engineer |
| `_AI` | AI Engineer |
| `_ML` | ML Engineer / MLOps |
| `standard` | General / Default |

Upload each variation via `POST /api/resume` with `{"resume_text": "...", "version": "_DE"}`.

---

## Core Principles

1. **Single page** — always
2. **Align with the JD** — every bullet ties to a role qualification
3. **Formula**: "Accomplished [X] as measured by [Y], by doing [Z]"
4. **Quantify everything** — %, TPS, hours saved, cost reduction, latency
5. **4-6 bullets per role** — concise over exhaustive
6. **ATS keywords**: embed naturally in context, not as bare lists
7. **Standard job titles** — align internal titles to common search terms
8. **Research the company** — echo culture/mission in your positioning

---

## Build Workflow

### Step 1 — Skills Gap Analysis
> "Analyze this JD and my resume. Identify the top 5 skills missing or weakly represented.
> For each, suggest 1-2 quantifiable achievements I could adapt. Use action verbs."

### Step 2 — Tailored Bullet Points
> "Rewrite my experience section to align with this JD. Use JD keywords naturally,
> start with strong action verbs, quantify where possible. Limit to 4-6 bullets per role."

### Step 3 — ATS Optimization
> "Optimize my resume for ATS compatibility with this JD. Keywords in context,
> consistent formatting, flag employment gaps and suggest subtle framing."

### Step 4 — Professional Summary
> "Write a 4-5 sentence summary based on this JD and my background.
> Highlight my unique value, incorporate 3-4 JD terms, end with a forward-looking statement."

---

## Positioning by Role Type

| Role | Lead With |
|------|-----------|
| Data Engineer | Python, Spark, Kafka, Airflow, ETL pipelines, cloud data platforms |
| Analytics Engineer | dbt, Snowflake, dimensional modeling, semantic layers, BI tools |
| ML Engineer | MLflow, feature engineering, model serving, MLOps, LangChain, RAG |
| Software Engineer | FastAPI, REST APIs, CI/CD, Docker, PostgreSQL, system design |

---

## LaTeX Template

Uses the Jake's Resume base format. Requires: `latexsym`, `fullpage`, `titlesec`,
`enumitem`, `hyperref`, `fancyhdr`, `tabularx`.

```latex
\documentclass[letterpaper,11pt]{article}
% ... (standard packages) ...

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}
```

**Sections order**: Heading → Education → Experience → Projects → Certifications → Skills

**Skills format**: Comma-separated within category rows, not bullet lists.

```latex
\textbf{Languages \& ML}{: Python, SQL, Bash, MLflow, Airflow, LangChain, RAG} \\
\textbf{Data \& Cloud}{: Spark, Kafka, Databricks, Delta Lake, Azure, AWS, Docker} \\
\textbf{Tools}{: FastAPI, Streamlit, Power BI, Git, CI/CD, Elasticsearch} \\
```

Full template reference: [github.com/narendranathe/resume2](https://github.com/narendranathe/resume2)

---

## Profile Relevance Scoring

JobScout scores every job against your profile in `backend/config/profile.py`:

| Component | Weight |
|-----------|--------|
| Core skills match | 40% |
| Secondary skills match | 20% |
| Title relevance | 15% |
| Location preference | 10% |
| Experience level | 10% |
| Sponsorship signal | 5% |

Jobs below `min_score_threshold` (default `0.30`) are filtered out before storage.
Dream company alerts fire at `DREAM_ALERT_SCORE` (default `0.70`).

---

## What Gets Filtered Out

The scraper pre-filters titles before scoring. Excluded categories:
- Field operators, data entry, data collectors
- HR, recruiter, talent acquisition
- Sales, marketing, brand, social media
- Medical, clinical, healthcare
- Trades (HVAC, electrician, etc.)
- Customer support, retail, cashier
- Administrative, receptionist, coordinator

Only roles that combine a data/ML/AI signal **with** an engineering/technical context word pass through.

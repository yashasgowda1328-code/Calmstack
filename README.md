# ReConstructAI

### Recover. Reconstruct. Understand.

**AI-Assisted Intelligent Data Recovery & Digital Evidence Reconstruction**

**CALMSTACKS 24H HACKATHON**
**Track:** Cybersecurity & AI

---

## 📌 Problem Statement

Data can become unavailable because of accidental deletion, file-system corruption, damaged storage, ransomware incidents, fragmentation, partial overwriting, or deliberate attempts to destroy evidence.

Traditional recovery tools mainly focus on retrieving recoverable files. However, recovered data can still be:

* Fragmented
* Corrupted
* Duplicated
* Incomplete
* Difficult to interpret
* Difficult to prioritize

The challenge is not only to recover data, but to determine **which recovered fragments are related, what can realistically be reconstructed, how reliable the reconstruction is, and what should be examined first**.

---

## 💡 Solution

**ReConstructAI** is an AI-assisted recovery and digital evidence reconstruction platform that combines forensic analysis with intelligent fragment relationship analysis.

The system follows:

**Recover → Analyze → Relate → Reconstruct → Validate → Prioritize → Report**

It works on controlled damaged/fragmented datasets or supported forensic images and produces an investigator-friendly recovery analysis.

---

# ✨ Core Features

### 🔐 1. Evidence Ingestion

* Upload supported sample evidence/datasets
* Create unique scan sessions
* Calculate SHA-256 hashes
* Preserve original input for analysis

### 🔎 2. File & Fragment Recovery

Detect recoverable content using:

* File signatures / magic bytes
* File structure
* Fragment boundaries
* Filesystem metadata where available
* File-carving techniques

Initial demonstration formats:

`JPEG` `PNG` `PDF` `TXT` `ZIP` `DOCX`

### 🧩 3. Fragment Feature Extraction

Extract features such as:

* File signature
* Fragment size
* Offset
* Entropy
* Byte statistics
* Printable-byte ratio
* Structural information
* Header/footer compatibility

### 🤖 4. AI-Assisted Fragment Relationship Analysis

The AI layer estimates whether two recovered fragments are likely to belong to the same original file.

Example:

```text
Fragment A → Fragment B
Relationship Confidence: 94%

Fragment A → Fragment C
Relationship Confidence: 21%
```

The AI acts as an **assistive scoring layer**, while deterministic forensic and file-format checks validate results.

### 🕸️ 5. Fragment Relationship Graph

```text
        F01
       /   \
    0.94   0.81
     /       \
   F02 ----- F03
       0.89
         |
        F04
```

* Nodes → recovered fragments
* Edges → possible relationships
* Edge weight → relationship score

### 🔧 6. Intelligent Reconstruction

Candidate fragments are ordered using:

* Relationship score
* Structural compatibility
* Byte-level similarity
* File-format constraints
* Offset information

The system generates candidate reconstructions rather than blindly joining fragments.

### ✅ 7. Integrity & Confidence Assessment

Each reconstructed item receives:

* Integrity score
* Reconstruction confidence
* Recovery status
* Supporting reasons

Example:

```text
File: evidence.jpg

Fragments Found    : 6
Fragments Used     : 5
Integrity          : 89%
Confidence         : 94%

Status             : PARTIALLY RECOVERED
```

### 🎯 8. Evidence Prioritization

Recovered artifacts are prioritized using factors such as:

* Recoverability
* Integrity
* Reconstruction confidence
* Classification confidence
* Completeness

The system prioritizes **reliability and recoverability**, not legal importance.

### 📊 9. Investigator Dashboard

The web interface displays:

* Scan status
* Recovered fragments
* Fragment relationships
* Reconstruction results
* Integrity
* Confidence
* Recovery status
* Evidence priority

### 📄 10. Recovery Report

For every recovered artifact, the system explains:

```text
What was recovered?
Which fragments were related?
How was it reconstructed?
How complete is it?
How confident is the result?
Why was this status assigned?
```

---

# 🔄 Core System Flow

```text
             Damaged / Deleted Data
                       │
                       ▼
               Evidence Ingestion
                       │
                       ▼
                Fragment Recovery
                       │
                       ▼
              Feature Extraction
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
       Forensic Analysis      AI Analysis
             │                   │
             └─────────┬─────────┘
                       ▼
            Fragment Relationship
                  Scoring
                       │
                       ▼
            Relationship Graph
                       │
                       ▼
              Reconstruction
                       │
                       ▼
          Structural Validation
                       │
                       ▼
        Integrity + Confidence Score
                       │
                       ▼
             Evidence Prioritization
                       │
                       ▼
              Investigator Report
```

---

# 🏗️ Proposed System Architecture

```text
                         ReConstructAI
                              │
                              ▼
                  ┌──────────────────────┐
                  │      Next.js         │
                  │   Web Dashboard      │
                  │  React + TypeScript  │
                  └──────────┬───────────┘
                             │
                         HTTPS / REST
                             │
                             ▼
                  ┌──────────────────────┐
                  │       FastAPI        │
                  │   Backend / API      │
                  └──────────┬───────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌──────────────┐   ┌──────────────┐   ┌────────────────┐
   │ Recovery     │   │ AI / ML      │   │ Reconstruction │
   │ Engine       │   │ Engine       │   │ Engine         │
   ├──────────────┤   ├──────────────┤   ├────────────────┤
   │ Signatures   │   │ Features     │   │ Matching       │
   │ Fragmenting  │   │ ML scoring   │   │ Graph analysis │
   │ Carving      │   │ Confidence   │   │ Candidate build│
   └──────┬───────┘   └──────┬───────┘   └───────┬────────┘
          │                  │                   │
          └──────────────────┼───────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Validation & Scoring │
                  └──────────┬───────────┘
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
        ┌────────────────┐      ┌─────────────────┐
        │ MongoDB Atlas  │      │ Artifact Storage│
        │ Metadata/Logs  │      │ Recovered Files │
        └────────────────┘      └─────────────────┘
```

---

# 🛠️ Technology Stack

## Frontend

* **Next.js**
* **TypeScript**
* **Tailwind CSS**
* **shadcn/ui**
* **React Flow** — fragment relationship graph
* **Recharts** — recovery and integrity visualization

## Backend

* **Python**
* **FastAPI**
* **Uvicorn**

## AI / Machine Learning

* **Scikit-learn**
* **Random Forest** — fragment relationship scoring
* **NumPy**
* **Pandas**

## Digital Forensics & Recovery

* **Python-based magic-byte/signature analysis**
* **libmagic / python-magic**
* **The Sleuth Kit / pytsk3** — optional filesystem analysis
* **File-carving utilities** — optional where useful
* **Pillow** — image validation
* **SHA-256 / hashlib** — integrity tracking

## Reconstruction

* **Custom Python reconstruction algorithms**
* **NetworkX** — relationship graph analysis

## Database

* **MongoDB**
* **MongoDB Atlas**
* **PyMongo**

## Deployment

```text
Next.js Frontend → Vercel

FastAPI Backend → Railway / compatible Python hosting

Database → MongoDB Atlas
```

The application will be a **responsive web application**. A separate native Android/iOS application is outside the 24-hour MVP scope.

---

# 🧠 AI Architecture

The AI component uses a **hybrid forensic + machine learning approach**.

```text
                Fragment Pair
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   Forensic Features       ML Features
          │                     │
          └──────────┬──────────┘
                     ▼
             Random Forest
                     │
                     ▼
       Fragment Relationship Score
                     │
                     ▼
           Reconstruction Engine
                     │
                     ▼
           File Structure Validation
```

The AI primarily assists with **fragment relationship scoring and reconstruction confidence**, rather than simply identifying file extensions.

---

# 📁 Project Structure

```text
ReConstructAI/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── public/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── services/
│   │   ├── models/
│   │   └── utils/
│   └── requirements.txt
│
├── recovery/
│   ├── signatures/
│   ├── fragments/
│   ├── filesystem/
│   └── hashing/
│
├── ai/
│   ├── datasets/
│   ├── features/
│   ├── models/
│   └── scoring/
│
├── reconstruction/
│   ├── matcher.py
│   ├── graph.py
│   ├── scorer.py
│   └── validator.py
│
├── storage/
│   ├── input/
│   ├── fragments/
│   └── reconstructed/
│
├── tests/
│
├── docs/
│
├── .gitignore
└── README.md
```

---

# 👥 Team & Assigned Work

## 1. Yashas — Backend & System Integration

**Branch:** `feature/backend`

### Responsibilities

* FastAPI backend
* REST API design
* MongoDB Atlas integration
* Scan/session management
* API integration with recovery, AI and reconstruction modules
* Backend error handling
* Frontend ↔ backend integration
* Final deployment coordination

### Main modules

```text
backend/
├── api/
├── services/
├── models/
└── utils/
```

### Primary goal

Make sure all four modules work together as **one complete system**.

---

## 2. Suryadev — Data Recovery & Digital Forensics

**Branch:** `feature/recovery`

### Responsibilities

* Evidence ingestion
* File signature / magic-byte detection
* Fragment extraction
* File carving
* Hash generation
* Basic filesystem analysis
* Recovery test datasets
* Recovered artifact validation

### Main modules

```text
recovery/
├── signatures/
├── fragments/
├── filesystem/
└── hashing/
```

### Primary goal

Convert damaged/deleted input into **usable recovered fragments with metadata**.

---

## 3. Maanika — AI & Reconstruction Engine

**Branch:** `feature/ai-reconstruction`

### Responsibilities

* Fragment feature extraction
* Dataset preparation
* Random Forest model
* Fragment-pair scoring
* Similarity calculations
* Relationship graph logic
* Reconstruction candidate generation
* Integrity/confidence scoring
* Evidence prioritization

### Main modules

```text
ai/
├── datasets/
├── features/
├── models/
└── scoring/

reconstruction/
├── matcher.py
├── graph.py
├── scorer.py
└── validator.py
```

### Primary goal

Build the project's **main intelligence layer** that determines which fragments are likely related and how confidently they can be reconstructed.

---

## 4. Rameez — Frontend & Investigator Dashboard

**Branch:** `feature/frontend`

### Responsibilities

* Next.js application
* Dashboard
* Evidence upload interface
* Scan progress
* Fragment table
* Recovery result pages
* Integrity/confidence visualization
* React Flow relationship graph
* Evidence prioritization UI
* Recovery report interface
* Responsive design

### Main modules

```text
frontend/
├── app/
├── components/
├── hooks/
├── lib/
└── public/
```

### Primary goal

Turn the backend analysis into a **clear, professional investigator-facing interface**.

---

# 🔗 Team Integration

The four modules connect as follows:

```text
                 Rameez
              Next.js UI
                  │
                  ▼
                 Yashas
             FastAPI Backend
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   Suryadev    Maanika    Storage
   Recovery   AI +        + MongoDB
              Reconstruction
        │         │
        └────┬────┘
             ▼
       Final Analysis
             │
             ▼
        Next.js UI
```

### Integration responsibility

**Yashas** owns the main integration layer.

Each member should expose clean functions/APIs instead of directly modifying another member's module.

---

# 🌿 GitHub Branch Strategy

```text
main
│
├── feature/frontend
├── feature/recovery
├── feature/ai-reconstruction
└── feature/backend
```

### Rules

1. Do not directly experiment on `main`.
2. Each member works primarily on their assigned branch.
3. Commit frequently with meaningful messages.
4. Push work to GitHub regularly.
5. Merge major features through Pull Requests.
6. Pull the latest `main` before major integration work.
7. Test before merging.

### Example

```bash
git checkout main
git pull origin main
git checkout -b feature/recovery
```

After implementation:

```bash
git add .
git commit -m "feat: add fragment signature detection"
git push -u origin feature/recovery
```

Then:

```text
Pull Request
feature/recovery → main
```

---

# 🎯 MVP Scope

The 24-hour MVP must achieve one complete working pipeline:

```text
✓ Evidence ingestion
✓ Fragment detection
✓ File-type identification
✓ Feature extraction
✓ AI-assisted fragment relationship scoring
✓ Relationship graph
✓ Candidate reconstruction
✓ Structural validation
✓ Integrity score
✓ Confidence score
✓ Evidence prioritization
✓ Investigator dashboard
✓ End-to-end demonstration
```

---

# 🧪 Demonstration Dataset

We will create controlled datasets from known source files.

```text
Original File
     ↓
Split into fragments
     ↓
Shuffle / remove / duplicate / corrupt selected fragments
     ↓
Damaged Dataset
     ↓
ReConstructAI
     ↓
Reconstructed Candidate
     ↓
Compare with Original
```

### Demonstration scenarios

```text
1. Fully reconstructable file
2. Fragmented file
3. Partially corrupted file
4. Missing fragment
5. Duplicate fragments
6. Unrecoverable data
```

Known source files provide ground truth for evaluating reconstruction.

---

# 🔐 Security & Forensic Principles

* Analyze copies rather than modifying original evidence.
* Generate SHA-256 hashes for evidence tracking.
* Separate original evidence from recovered artifacts.
* Keep analysis metadata separate from binary evidence.
* Provide explainable confidence and integrity results.
* Clearly distinguish recovered, partially recovered and unrecoverable data.

**ReConstructAI is a hackathon prototype and is not intended to replace validated forensic acquisition or examination tools.**

---

# ⏱️ 24-Hour Development Priority

### Phase 1 — Foundation

```text
GitHub
Next.js
FastAPI
MongoDB
Basic API connection
Basic dashboard
```

### Phase 2 — Recovery

```text
Fragment detection
Signature analysis
Sample damaged datasets
Hashing
```

### Phase 3 — AI + Reconstruction

```text
Feature extraction
Fragment-pair scoring
Relationship graph
Reconstruction
Validation
```

### Phase 4 — Integration

```text
Frontend
    ↓
FastAPI
    ↓
Recovery
    ↓
AI
    ↓
Reconstruction
    ↓
Results
```

### Phase 5 — Finalization

```text
Testing
UI polishing
Deployment
Demo dataset
Presentation
Final rehearsal
```

---

# 🚫 Scope Control

We are **not** attempting to build:

* A universal file-recovery platform
* Support for every filesystem and file format
* A full enterprise digital-forensics suite
* A native mobile application
* A large deep-learning model
* An LLM-based evidence reconstruction system

The focus is a **working, demonstrable intelligent reconstruction pipeline within 24 hours**.

---

# 🔮 Future Enhancements

* Advanced filesystem support
* Additional file formats
* Improved fragment-ordering models
* Deep-learning-based binary representations
* Timeline reconstruction
* Metadata correlation
* Advanced forensic reporting
* Cloud-scale evidence processing
* Large-scale object storage
* Advanced investigator analytics

---

# 🎯 Vision

ReConstructAI aims to move digital recovery from:

```text
Recover the file
```

towards:

```text
Recover
   ↓
Understand
   ↓
Reconstruct
   ↓
Validate
   ↓
Prioritize
```

The goal is to help users understand **what can realistically be restored and how reliable that reconstruction is**.

---

# 👨‍💻 Contributors

### ReConstructAI Team

| Member       | Role                              | GitHub Branch               |
| ------------ | --------------------------------- | --------------------------- |
| **Yashas**   | Backend & System Integration      | `feature/backend`           |
| **Suryadev** | Data Recovery & Digital Forensics | `feature/recovery`          |
| **Maanika**  | AI & Reconstruction Engine        | `feature/ai-reconstruction` |
| **Rameez**   | Frontend & Investigator Dashboard | `feature/frontend`          |

---

# 📜 License

This project is developed for educational, research and hackathon purposes.

License information will be added as the project evolves.

---

## 🚀 ReConstructAI

### Recover. Reconstruct. Understand.

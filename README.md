# ReConstructAI

### Recover. Reconstruct. Understand.

**AI-Assisted Intelligent Data Recovery & Digital Evidence Reconstruction**

**CALMSTACKS 24H HACKATHON**
**Track:** Cybersecurity & AI

---

## 📌 Problem Statement

Accidental deletion, file-system corruption, damaged storage, ransomware incidents, fragmentation, and deliberate attempts to destroy evidence can make digital information partially or completely inaccessible.

Traditional recovery tools mainly focus on retrieving files. Recovered data may still be fragmented, corrupted, duplicated, incomplete, or difficult to interpret.

The challenge is to identify what can realistically be recovered, determine relationships between recovered fragments, reconstruct possible files, assess their integrity, and prioritize the results for further examination.

---

## 💡 Solution

**ReConstructAI** is a desktop-based intelligent forensic file recovery and evidence reconstruction workspace.

Instead of simply recovering files, ReConstructAI analyzes a collection of damaged or fragmented evidence and helps determine:

* What was found
* Which fragments may belong together
* What can be reconstructed
* How reliable the reconstruction is
* Which results should be examined first

### Core Pipeline

```text
Evidence
   ↓
Analyze
   ↓
Detect Fragments
   ↓
Extract Features
   ↓
Find Relationships
   ↓
AI-Assisted Scoring
   ↓
Reconstruct Candidates
   ↓
Validate
   ↓
Prioritize
   ↓
Report
```

---

# ✨ Core Features

### 📂 1. Case & Evidence Management

* Create investigation cases
* Select local evidence folders
* Browse files and recovered artifacts
* Preserve original evidence during analysis
* Maintain case-level analysis metadata

### 🔎 2. Intelligent File Analysis

Analyze files using:

* Magic bytes / file signatures
* File type
* File size
* SHA-256 hash
* Shannon entropy
* Binary/text characteristics
* Corruption indicators

### 🧩 3. Fragment Detection & Analysis

Identify fragmented data and extract:

```text
Fragment ID
Offset
Size
SHA-256
Entropy
Byte statistics
Detected type
```

### 🤖 4. AI-Assisted Fragment Relationship Analysis

Estimate whether two fragments are likely to belong together using measurable features such as:

* Entropy similarity
* Byte statistics
* Size compatibility
* Offset/distance
* Structural compatibility

Example:

```text
F001 → F002
Relationship Score: 0.94
```

The AI provides an **assistive score**; forensic and file-structure validation remain separate.

### 🕸️ 5. Fragment Relationship Graph

Visualize possible relationships between recovered fragments.

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

**Nodes:** Fragments
**Edges:** Possible relationships
**Weight:** Relationship score

### 🔧 6. Reconstruction Candidates

Generate possible fragment sequences instead of blindly joining data.

```text
R001

F001 → F002 → F005 → F008

Integrity:   91%
Confidence:  88%
Status:      PARTIALLY RECOVERED
```

### ✅ 7. Validation & Integrity Assessment

Evaluate reconstruction candidates using:

* Fragment consistency
* Completeness
* Structural compatibility
* Relationship strength
* File-format validation

Possible statuses:

```text
FULLY RECOVERED
PARTIALLY RECOVERED
LOW CONFIDENCE
UNRECOVERABLE
```

### 🎯 8. Evidence Prioritization

Prioritize results using measurable factors such as:

* Integrity
* Recoverability
* Reconstruction confidence
* Completeness

Priority represents **reliability and recoverability**, not legal importance.

### 📊 9. Investigator Workspace

The desktop application provides:

```text
Cases
├── Evidence
├── Healthy Files
├── Corrupted Files
├── Fragments
├── Reconstructions
├── Priority Results
└── Reports
```

### 📄 10. Recovery Report

Each reconstruction provides:

```text
What was found?
Which fragments were related?
How was it reconstructed?
How complete is it?
How confident is the result?
Why was this status assigned?
```

---

# 🔄 System Flow

```text
                 Evidence Folder
                        │
                        ▼
               ┌─────────────────┐
               │ Evidence Manager│
               └────────┬────────┘
                        ▼
                 File Analyzer
                        │
                        ▼
                Fragment Detector
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
             Relationship Scoring
                        │
                        ▼
                 Reconstruction
                        │
                        ▼
                  Validation
                        │
                        ▼
             Integrity + Confidence
                        │
                        ▼
              Evidence Prioritization
                        │
                        ▼
                    Report
```

---

# 🏗️ System Architecture

```text
                       ReConstructAI
                            │
                            ▼
                   ┌─────────────────┐
                   │    PySide6 UI   │
                   │  Desktop App    │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Core Engine   │
                   └────────┬────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   ┌──────────────┐  ┌──────────────┐  ┌────────────────┐
   │ File Analysis│  │   AI / ML    │  │ Reconstruction │
   │ & Recovery   │  │    Engine    │  │     Engine     │
   └──────┬───────┘  └──────┬───────┘  └───────┬────────┘
          │                 │                  │
          └─────────────────┼──────────────────┘
                            ▼
                   ┌─────────────────┐
                   │ Validation &    │
                   │ Prioritization  │
                   └────────┬────────┘
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
          ┌─────────────┐      ┌──────────────┐
          │   SQLite    │      │ Local Storage│
          │ Case/Results│      │ Evidence     │
          └─────────────┘      │ Fragments    │
                               │ Reconstructed│
                               └──────────────┘
```

---

# 🛠️ Technology Stack

### Desktop Application

* Python
* PySide6 / Qt

### File Analysis & Recovery

* Magic-byte / signature analysis
* `python-magic` / `libmagic`
* SHA-256 / `hashlib`
* Pillow
* Optional The Sleuth Kit / `pytsk3` where required

### AI / Machine Learning

* Scikit-learn
* Random Forest
* NumPy
* Pandas

### Fragment Relationships & Reconstruction

* Custom Python scoring algorithms
* NetworkX
* File-structure validation

### Database

* SQLite

Used for:

```text
Cases
Scans
Files
Fragments
Relationships
Reconstructions
Reports
```

### Storage

Local filesystem:

```text
storage/
├── evidence/
├── fragments/
├── reconstructed/
└── reports/
```

### Packaging

* PyInstaller

### Development

* Git
* GitHub
* VS Code
* Kilo Code

---

# 🧠 AI Architecture

ReConstructAI uses a **hybrid forensic + machine-learning approach**.

```text
                 Fragment Pair
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   Forensic Features         ML Features
          │                       │
          └───────────┬───────────┘
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
              File Validation
```

The initial model is trained using controlled/synthetic data generated from known source files. Synthetic results are used for prototype evaluation and are **not claimed as real-world forensic accuracy**.

---

# 📁 Project Structure

```text
ReConstructAI/
│
├── app/
│   ├── main.py
│   ├── ui/
│   ├── core/
│   └── database/
│
├── recovery/
│   ├── analyzer/
│   ├── signatures/
│   ├── fragments/
│   └── hashing/
│
├── ai/
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
│   ├── evidence/
│   ├── fragments/
│   ├── reconstructed/
│   └── reports/
│
├── datasets/
├── tests/
├── docs/
├── requirements.txt
├── .gitignore
└── README.md
```

---

# 👥 Team & Assigned Work

| Member       | Role                                      | Main Responsibility                                                                    |
| ------------ | ----------------------------------------- | -------------------------------------------------------------------------------------- |
| **Yashas**   | **Team Lead + Core Engine & Integration** | Architecture, SQLite, case management, module integration, testing and final packaging |
| **Suryadev** | **Recovery & Digital Forensics**          | File analysis, signatures, fragment extraction, hashing and recovery logic             |
| **Maanika**  | **AI & Reconstruction**                   | Feature engineering, ML model, relationship scoring, reconstruction and validation     |
| **Rameez**   | **Desktop UI**                            | PySide6 interface, file manager, dashboard, graph and report screens                   |

---

# 🌿 GitHub Workflow

```text
main
│
├── feature/core
├── feature/recovery
├── feature/ai-reconstruction
└── feature/ui
```

### Rules

* `main` contains tested and integrated code.
* Each member works primarily on their feature branch.
* Commit and push work regularly.
* Use Pull Requests for integration.
* Test before merging.
* Keep module interfaces stable.

---

# 🧪 Demonstration Dataset

We create controlled datasets from known source files.

```text
Original File
      ↓
Split into fragments
      ↓
Shuffle / remove / duplicate / corrupt
      ↓
Damaged Dataset
      ↓
ReConstructAI
      ↓
Reconstruction Candidate
      ↓
Compare with Original
```

### Demonstration Cases

```text
✓ Fully recoverable
✓ Fragmented
✓ Partially corrupted
✓ Missing fragment
✓ Duplicate fragment
✓ Unrecoverable
```

This provides known ground truth for testing reconstruction.

---

# 🎯 MVP

The 24-hour MVP focuses on one complete workflow:

```text
✓ Create Case
✓ Select Evidence Folder
✓ Analyze Files
✓ Detect Fragments
✓ Extract Features
✓ Find Fragment Relationships
✓ AI-Assisted Relationship Scoring
✓ Generate Reconstruction Candidates
✓ Validate Candidates
✓ Calculate Integrity / Confidence
✓ Prioritize Results
✓ Display in Desktop UI
✓ Export Reconstructed Artifact / Report
```

---

# 🚫 Scope Control

We are not attempting to build:

* A universal forensic recovery platform
* Support for every filesystem and file format
* A native mobile application
* A large deep-learning model
* An LLM-based reconstruction engine
* A replacement for professional forensic tools

The focus is a **working, demonstrable intelligent recovery and reconstruction prototype within 24 hours**.

---

# 🔐 Forensic Principles

* Analyze copies rather than modifying original evidence.
* Generate hashes for evidence tracking.
* Separate original evidence from recovered artifacts.
* Clearly distinguish reconstruction candidates from verified recovery.
* Provide explainable integrity and confidence information.
* Do not claim recovery when the underlying data is unavailable or insufficient.

**ReConstructAI is a hackathon prototype and is not intended to replace validated forensic acquisition or examination tools.**

---

# 🔮 Future Enhancements

* Advanced filesystem support
* More file formats
* Improved fragment-ordering models
* Advanced binary similarity
* Timeline reconstruction
* Metadata correlation
* Advanced forensic reporting
* Large-scale evidence processing
* Additional reconstruction algorithms

---

# 🎯 Vision

ReConstructAI moves digital recovery beyond:

```text
"File recovered."
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

The goal is to help users understand **what can realistically be restored, how fragments are related, and how reliable the reconstruction is**.

---

# 👨‍💻 Contributors

### ReConstructAI Team

* **Yashas** — Team Lead + Core Engine & Integration
* **Suryadev** — Recovery & Digital Forensics
* **Maanika** — AI & Reconstruction
* **Rameez** — Desktop UI

---

## 📜 License

This project is developed for educational, research and hackathon purposes.

License information will be added as the project evolves.

---

# 🚀 ReConstructAI

### Recover. Reconstruct. Understand.

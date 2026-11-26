# RAG-SFAR — Évaluation End-to-End & Diagnostic RAG-X (4 Quadrants)

- **Modèle LLM** : `Qwen2.5-3B-Instruct-4bit` (`temperature = 0.0`)
- **Questions évaluées** : `50` (Antibioprophylaxie SFAR — `OpenScorer` + `QCMScorer` + `SourcingScorer` officiels)

| Système | Overall Acc. | Open Acc. | MCQ Acc. | Allergie Acc. | Sourcing | Q1 Succès Sourcé (Grounded Acc.) | Q2 Coup de Chance | Q3 Err. LLM | Q4 Err. Retr. | CUE | ~Prompt Tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`Zero-Shot (LLM seul)`** | **40.0%** | 32.5% (13/40) | 70.0% (7/10) | 37.5% (3/8) | 0.0% | **0 (0.0%)** | 20 | 0 | 30 | 0.0% | 153 |
| **`C0 RAG Naïf`** | **54.0%** | 52.5% (21/40) | 60.0% (6/10) | 37.5% (3/8) | 100.0% | **26 (52.0%)** | 1 | 20 | 3 | 56.5% | 4168 |
| **`C8 RAG-SFAR Frontier 2026`** | **72.0%** | 75.0% (30/40) | 60.0% (6/10) | 50.0% (4/8) | 100.0% | **36 (72.0%)** | 0 | 13 | 1 | 73.5% | 2038 |

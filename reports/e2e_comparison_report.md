# RAG-SFAR — Évaluation End-to-End & Diagnostic RAG-X (4 Quadrants)

- **Modèle LLM** : `Qwen2.5-7B-Instruct-4bit` (`temperature = 0.0`)
- **Questions évaluées** : `50` (Antibioprophylaxie SFAR — `OpenScorer` + `QCMScorer` + `SourcingScorer` officiels)

| Système | Overall Acc. | Open Acc. | MCQ Acc. | Allergie Acc. | Sourcing | Q1 Succès Sourcé (Grounded Acc.) | Q2 Coup de Chance | Q3 Err. LLM | Q4 Err. Retr. | CUE | ~Prompt Tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`Zero-Shot (LLM seul)`** | **52.0%** | 52.5% (21/40) | 50.0% (5/10) | 75.0% (6/8) | 0.0% | **0 (0.0%)** | 26 | 0 | 24 | 0.0% | 153 |
| **`C0 RAG Naïf`** | **84.0%** | 82.5% (33/40) | 90.0% (9/10) | 75.0% (6/8) | 100.0% | **41 (82.0%)** | 1 | 5 | 3 | 89.1% | 4252 |
| **`C8 RAG-SFAR Frontier 2026`** | **100.0%** | 100.0% (40/40) | 100.0% (10/10) | 100.0% (8/8) | 100.0% | **50 (100.0%)** | 0 | 0 | 0 | 100.0% | 2269 |

# RAG-SFAR — Évaluation End-to-End & Diagnostic RAG-X (4 Quadrants)

- **Modèle LLM** : `Qwen2.5-7B-Instruct-4bit` (`temperature = 0.0`)
- **Questions évaluées** : `50` (Antibioprophylaxie SFAR — `OpenScorer` + `QCMScorer` + `SourcingScorer` officiels)

| Système | Overall Acc. | Open Acc. | MCQ Acc. | Allergie Acc. | Sourcing | Q1 Succès Sourcé (Grounded Acc.) | Q2 Coup de Chance | Q3 Err. LLM | Q4 Err. Retr. | CUE | ~Prompt Tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`C8 RAG-SFAR Frontier 2026 (Held-Out Unseen 50)`** | **86.0%** | 84.2% (32/38) | 91.7% (11/12) | 0.0% (0/0) | 100.0% | **42 (84.0%)** | 1 | 6 | 1 | 87.5% | 2389 |

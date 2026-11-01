# Sources

## Opened and checked for this review

Title, authors and date were checked against the page itself.

| Source | Supports | Notes |
|---|---|---|
| Mansoor, Phadke, Rana. *Verified Tool Calls Improve LLM Agent Reliability Under Non-Atomic Failures*. arXiv:2608.02645 (2026-07-31) | Idempotency keys, postcondition checks, verify before retry | Preprint |
| Chang, Geng. *SagaLLM: Context Management, Validation, and Transaction Guarantees for Multi-Agent LLM Planning*. arXiv:2503.11951 (2025-03-15); PVLDB 18(12), 2025 | Saga-style compensation for multi-agent LLM workflows | The venue was reported by the research helper and was not re-checked |
| Mohammadi et al. *Atomix: Timely, Transactional Tool Use for Reliable Agentic Workflows*. arXiv:2602.14849 (2026-02-16) | Transactional tool use; compensation alone is insufficient for irreversible effects | Preprint |
| Zhu et al. *When Tools Fail: Benchmarking Dynamic Replanning and Anomaly Recovery in LLM Agents*. arXiv:2606.05806 (2026-06-04) | Failure taxonomy that separates transient from permanent, with recovery depending on type | Preprint; check numbers in the paper before quoting |
| Iannillo et al. *Tool-Calling LLM Agents Under Realistic MCP Faults: Scale Does Not Purchase Fault Tolerance*. arXiv:2610.32555 (2026-10-23) | Framework-level error handling matters more than model scale, which supports an external layer | Preprint |
| Agyemang et al. *HiveMind: OS-Inspired Scheduling for Concurrent LLM Agent Workloads*. arXiv:2604.17111 (2026-04-18) | Closest found to backoff and retry control for agents | Abstract only |
| Google SRE Book, ch. 22 "Addressing Cascading Failures" (sre.google) | Backoff with jitter, separating retriable from non-retriable errors, graceful degradation | The page loads. See the caveats below |

## Reported by the research helper, not re-checked

- Garcia-Molina, Salem. *Sagas*. SIGMOD 1987, DOI 10.1145/38713.38742 (metadata from Crossref).
- Brooker. *Exponential Backoff and Jitter*. AWS Architecture Blog, 2015.
- The Amazon Builders' Library article on retries (byline "Marc").
- Fowler's *CircuitBreaker* page, which credits Nygard with popularising the pattern. Nygard's *Release It!* itself could not be opened and is unverified.

## Do not cite these claims

- A "10 percent retry budget" attributed to the SRE book is not in the chapter text. It comes from secondary sites.
- A "60 to 80 percent retry-storm reduction" attributed to AWS has no primary source.
- The article's own "Further Reading" links are vendor content from the same company as the article. None cites research.
- No peer-reviewed paper was found that evaluates circuit breakers, backoff and retry budgets on LLM agents. Claims about retry storms in agent systems exist only in blog posts.

## Papers in the local collection used here

Located in `Paper Acuan/`. Numbers follow the proposal's reference list.

| Id | Paper | Used for |
|---|---|---|
| [02] | Avizienis et al., Basic Concepts and Taxonomy of Dependable and Secure Computing (2004) | Fault persistence, recurrence |
| [07] | Ma et al., DoVer | Checkpoint and replay, intervention-based recovery |
| [08] | Lu, Zhang, MARS | Rollback, guided repair, replay determinism |
| [09] | Jiang et al., MCR and MAGRPO | Fault classes for tool failures |
| [15] | Babu, Agrawal, Self-Healing Agentic Orchestrators | Failure classes mapped to recovery actions under budgets |
| [16] | Fourney et al., Magentic-One | Stall counter, irreversible action anecdote |
| [20] | Men et al., FTDI | Cost-aware repair tiers |

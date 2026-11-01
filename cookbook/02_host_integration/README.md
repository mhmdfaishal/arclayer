# Host integration

| File | Shows | You should see |
|---|---|---|
| [01_plain_python_agent.py](01_plain_python_agent.py) | A fault handler as a decorator around a tool, in plain Python: the caller gets a value as if the tool had worked | `the agent says: widget costs 9.99` |
| [02_when_an_executor_fails.py](02_when_an_executor_fails.py) | Three host-side failures: the executor raises, the executor is missing, the result never arrives | `executor_error` scored with reward `0.0`; `HostMisconfigured` with nothing reported; censoring closes the waiting incidents without a policy update |
| [03_async_host.py](03_async_host.py) | Six concurrent tasks sharing one policy through `handle_fault_async` | Six `recovered` and six policy updates |
| [04_report_in_two_steps.py](04_report_in_two_steps.py) | `post_incident` now, `post_result` later; a repeated report is safe | The same acknowledgement twice, one policy update, and `Conflict` for a different payload under the same key |

In 02, an executor that raises is not punished: the failure is scored with no credit and a reward near zero, so the candidate simply does not earn the preference a success would. A missing executor is treated as a wiring mistake and never reaches the policy.

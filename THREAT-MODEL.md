# Threat model

AI Command Agent is a single-operator CLI for small UTF-8 files. Its security boundary is the local executor and its approval prompts. Prompts, model responses, workspace data, and filesystem names are untrusted inputs. An operator can authorize only the actions implemented by the executor.

## Assets and trust boundaries

- **OpenAI credentials.** The process reads the key from the environment and sends it to the fixed OpenAI HTTPS endpoint. The request client disables redirects and environment proxy overrides.
- **Local files.** Execution is anchored to an opened workspace directory. A separate local directory holds the audit log. File contents and results are displayed locally. Only the operator's prompt is sent to the provider, so entering confidential text in a prompt sends that text off the machine.
- **Authorization.** Every effective plan needs interactive approval outside the model response. An overwrite or append to an existing file needs a second confirmation. The terminal preview includes up to 240 characters of proposed text and its full byte count.

## Threats and controls

| Threat | Controls |
| --- | --- |
| Prompt injection or fabricated approval | Treat the model response as a proposal. Validate the whole plan before preview. Reject unknown fields and actions. Require approval from a terminal and never accept approval from JSON or piped input. |
| Malformed, duplicate, or oversized JSON | Reject duplicate keys, enforce a closed JSON Schema with per-action parameter types, and cap prompt, response, plan, and field sizes. |
| Traversal, absolute paths, and link substitution | Restrict path segments and open descendants relative to checked directory descriptors. Use no-follow opens, reject hard links and special files, and check the target and parent again after confirmation. |
| Shell injection or unauthorized command execution | Recognize only the exact aliases `dir`, `ls`, and `pwd`. Implement them in Python without arguments, a shell, or subprocesses. |
| Destructive or unexpected edits | Require separate approval for changes to existing files, create new files exclusively, and use atomic replacement for approved overwrites. Stop the plan on the first failed action. |
| Slow provider or oversized output | Apply a 20-second overall provider timeout, per-operation HTTP timeouts, and a bounded response read. Limit local file reads and directory listings. |
| Sensitive output in logs or terminal controls | Audit records contain timestamps, action types, and statuses. Provider errors use fixed messages. Terminal output escapes control characters. Runtime files are excluded from Git. |

## Residual risks

- The workspace is intended for one trusted operating-system account on macOS, Linux, or WSL. An adversary already running as the same user, a hostile filesystem or mount, and a compromised operating system are outside this isolation boundary. Native Windows execution fails closed.
- A model can still propose a valid but unwanted action. Review prompts, paths, and previews carefully. Content beyond the preview limit is not displayed before approval.
- Actions run in sequence. Successfully completed steps remain applied if a later step fails. The audit log is local metadata and is editable by the operating-system account.
- Network timeouts cover provider calls. Human approval waits for terminal input, and filesystem I/O depends on the operating system. This candidate was tested with mocked provider responses. Live OpenAI inference remains unverified.

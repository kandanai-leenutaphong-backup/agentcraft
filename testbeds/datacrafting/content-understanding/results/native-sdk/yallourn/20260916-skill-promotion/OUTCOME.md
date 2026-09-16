# Initial SDK Capture Failure

The initial async response-capture hook raised `ResponseNotReadError` before the
SDK returned its poller. No operation ID was retained. The receipt's `failed`
status describes client execution only: remote submission/completion and charges
are **unknown**, not known absent. This original receipt is preserved unchanged.

The recipe was corrected to use an Azure Core async pipeline policy, save the
operation identifier before body capture and await the response body before JSON
access. Offline transport fixtures now refuse premature reads, matching the live
response contract. Any later run is a new deliberate submission with its own
directory, not a retry claiming that this operation never existed.
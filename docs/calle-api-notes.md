# Notes on the CALL-E Developer API

Things we hit building [OUTCOME](../README.md) against v0.6.0 that are not
obvious from the docs, written down so the next person does not spend the time
we did. Each entry has the exact request and the exact error.

The suggested fixes are kept because they explain *why* each gap costs time, not
because this document was sent anywhere.

---

## 1. The API refuses a region without saying which regions it serves

**Severity: blocking.** This is the one that stopped the project.

Creating a call to a Bahraini number is rejected:

```
HTTP 422
{"error":{"code":"call_not_ready","message":"Call task creation was rejected:
The recipient number appears to be in Bahrain, but calls in English to Bahrain
are not currently supported. To continue, please provide a recipient number in
a supported region/language combination."}}
```

Adding an explicit locale does not help, and shows the gate is the region rather
than the language:

```
recipients: [{"phones": ["+973…"], "locale": "ar-BH", "region": "BH"}]

HTTP 422
"The recipient number appears to be in Bahrain (BH), with Arabic requested, but
calls for that region/language combination are not currently supported. Which
supported region/language combination should be used instead if you want to
continue?"
```

The message asks the developer to pick a supported combination, but **nothing
published says what they are**. Searching the docs for the supported set finds
nothing: `calls.mdx` documents `locale` and `region` as free-text hints, the
OpenAPI schema types them as nullable strings with `en-US` as the example, and
the error enum has `unsupported_region` and `unsupported_language` without an
accompanying list.

The practical effect: a developer outside a supported region cannot tell whether
the product works for them until after they have signed up, obtained a key,
integrated, and made a request that fails. In our case the entire integration
was finished before we learned we could not place a single call.

**Suggested fixes, cheapest first:**

1. Put the supported region/language matrix in the docs, next to `locale` and
   `region` in the calls guide. A table would do.
2. Return the supported set in the 422 body — the error already asks the
   developer to choose one, so it may as well say what is on the menu:
   `"details": {"supported": [{"region": "US", "locales": ["en-US"]}, …]}`.
3. Expose it as a read-only endpoint, e.g. `GET /v1/regions`, so an application
   can check before it builds a workflow around a number it cannot dial. This
   would also let a preflight check catch it, which is where it belongs.

The 422-before-dial behaviour is genuinely good, incidentally: we spent no
credits discovering any of this. The gap is only that it is undiscoverable in
advance.

---

## 2. `recipient_result_schema` rejects nullable types, and the docs do not say so

The supported-features list in the calls guide reads:

> - `type`: `object`, `string`, `number`, `integer`, `boolean`, or `array`

which does not obviously exclude `"type": ["object", "null"]` — a common way to
express an optional object, and legal JSON Schema. It is rejected:

```
HTTP 400
{"error":{"code":"recipient_result_schema_invalid",
"details":{"reason":"unsupported JSON Schema type at $.properties.offer:
['object','null']"}}}
```

The error itself is excellent — it names the exact path and the exact problem,
which made the fix obvious. The gap is only in the docs.

**Suggested fix:** add one line to the unsupported list — "a `type` must be a
single value; union types including `null` are not supported. Express an absent
value with an empty string or an empty array." The `oneOf`/`anyOf` exclusion is
already listed, and a union type is the same thing in shorthand, but that
connection is not obvious while writing a schema.

---

## 3. A schema-validity endpoint would prevent a whole class of wasted call

Both problems above are only discoverable by attempting to create a call. For
schema validity in particular, nothing about the check requires a phone: it is a
pure function of the request body.

**Suggested fix:** `POST /v1/calls/validate`, or a `dry_run: true` flag on
`POST /v1/calls`, that runs schema validation, region/language checks and
recipient validation and returns what would have happened, without creating a
call task.

We ended up writing this client-side — a validator for the documented subset,
run from a `preflight` command — because a first live run against a real number
is the worst possible moment to discover a malformed schema. Having it in the
API would mean every integrator does not have to.

---

## 4. A failed call never releases its concurrency slot

**Severity: blocking, and we believe this is a backend bug rather than a
documentation gap.**

A non-KYC account gets one concurrent call task, and exceeding it returns:

```
HTTP 429 account_concurrency_exceeded
"Your default shared line (such as us/all) is at its account concurrency limit
of 1. This limit is shared across API, MCP, and Dashboard. Wait for an active
task to finish, then retry."
```

The limit itself is reasonable, and the error is unusually good: it names the
number, says where the limit is shared from, and links the upgrade path.

We hit it on our *second* call. The first — `call_lM98oxbW32A5n2xWMEsmjA` — had
rung a real phone, gone unanswered, and finished. `GET /v1/calls/{call_id}`
agreed:

```
{"id":"call_lM98oxbW32A5n2xWMEsmjA","status":"failed", … }
```

`failed` is terminal. The dashboard showed no calls at all, the account had 100
credits, and every subsequent `POST /v1/calls` was refused with the 429 above.

### What is actually happening

`GET /v1/calls/{call_id}/events` shows it. The call reaches its terminal state
once and then **re-enters it, over and over, indefinitely:**

```
18:52:22Z  call.started      run_call started.
18:52:25Z  call.in_progress  botlab create bot.
18:53:01Z  call.updated      calling task status=calling
18:53:26Z  call.updated      Call ended; syncing final Calling result.
18:53:48Z  call.updated      calling task status=NO ANSWER
18:54:00Z  call.failed       calling task completed with status=NO ANSWER   ← terminal
18:56:09Z  call.updated      calling task status=NO ANSWER
18:56:11Z  call.failed       calling task completed with status=NO ANSWER   ← again
18:58:19Z  call.updated      calling task status=NO ANSWER
18:58:20Z  call.failed       calling task completed with status=NO ANSWER   ← again
   …
20:35:21Z  call.failed       calling task completed with status=NO ANSWER   ← still going
```

The call reached `NO ANSWER` at 18:53:48Z and emitted `call.failed` at
18:54:00Z. **One hour and forty-one minutes later it was still emitting the same
pair every two minutes**, and was still doing so when we stopped counting:

| | |
|---|---|
| Events on the call | 184 |
| `call.failed` events | **88** |
| `call.updated` events | 92 |
| First event | `2026-09-10T18:52:22Z` |
| Last event | `2026-09-10T20:35:21Z` |
| Duration past terminal | **1 h 41 m and counting** |

So the worker that syncs the result from the underlying calling provider never
stops re-syncing a call that is already finished. The read API reports the call
as `failed`, but the task is evidently still live internally — which is exactly
what the concurrency accounting is counting. **The slot is held by a call that
every developer-visible surface says is over.**

The practical effect on a one-slot account is total: a single unanswered call
permanently disables the API. Nothing the developer can do releases it, because
there is no cancel endpoint.

**Reproduction:** place a call to a number that does not answer, wait for
`status: failed`, then poll `GET /v1/calls/{call_id}/events`. If `call.failed`
appears more than once, the slot is stuck.

**Suggested fixes, in order of importance:**

1. **Stop the sync loop at the first terminal event.** `NO ANSWER` is not a
   retryable condition, and 88 identical `call.failed` events for one call is
   the symptom of a retry with no terminal check and no attempt ceiling.
2. **Release the concurrency slot when the call reaches a terminal status**,
   independently of whatever the sync worker is doing. The developer-visible
   status and the internal accounting disagreeing is the part that makes this
   undiagnosable from outside.
3. **Add a cancel:** `POST /v1/calls/{call_id}/cancel` or `DELETE
   /v1/calls/{call_id}`. There is currently no way for a developer to release a
   slot, so a bug like this is unrecoverable without contacting support.
4. Return the blocking task's id in the 429 body:
   `"details": {"active_task_ids": ["call_…"]}`. The error says to "wait for an
   active task to finish", but there is no list endpoint (`GET /v1/calls`
   returns 405), so the instruction is not followable. Had the 429 named
   `call_lM98oxbW32A5n2xWMEsmjA`, this would have taken minutes instead of a day.
5. `account_concurrency_exceeded` is **not in the documented error-code enum**
   in `calle.openapi.yaml` (v0.7.0), which lists `rate_limit_exceeded` for 429.
   A caller writing exhaustive error handling from the spec will not have a
   branch for the one 429 they are most likely to see.

Credit where it is due: `GET /v1/calls/{call_id}/events` is what made this
diagnosable at all, and it is a genuinely good endpoint — per-event `level`,
`status` and `message`, cursor paging, and enough detail to see a backend loop
from the outside. We had built against v0.6.0 and did not know it existed; it is
worth pointing at from the calls guide, because it is the first thing anyone
debugging a stuck call should reach for.

One design note, since it is a compliment rather than a complaint: a
concurrency limit of 1 is a perfectly comfortable fit for an agent like this
one. OUTCOME is strictly sequential by construction — it decides who to call
next *from* what the last call said, so it can never want two lines at once.
Anything doing parallel fan-out would feel this limit immediately; anything
doing genuine multi-step reasoning will not.

## 5. Smaller things

- **Reserved recipient response field names** (`summary`, `status`,
  `transcript`, `call_id`, timing fields) are documented in prose in the calls
  guide. They would be easier to obey as an explicit list, and the schema-invalid
  error should name the collision if a reserved name is used.
- **`GET /v1/calls` returns 405.** `POST` works. If listing is not supported,
  405 is correct, but a `GET` that lists recent calls would help reconciliation
  after a crash — we keep a local ledger of placed calls specifically because we
  cannot ask the API what we already dialled.
- **`GET /v1/goals` as the auth check** is what the community seems to use for a
  read-only credential preflight, including us. Documenting it as the intended
  health check, or adding an explicit one, would make that less folkloric.

---

## What we built, for context

OUTCOME is an autonomous phone-work agent: the user states an outcome and its
constraints, and the agent decides who to call, calls them, reads each result as
structured evidence, checks any offer against the user's hard limits, and
follows referrals given on calls to organisations the user never supplied. One
call per run may commit the user, and only after they approve the exact terms.

It leans on `recipient_result_schema` heavily — the structured result is what
makes calls composable, because the planner reads a uniform record rather than a
transcript, and that is what lets the same planner drive a scripted rehearsal and
a live run identically. That design is a direct consequence of the API having
structured extraction, and it is the best thing about building on CALL-E.

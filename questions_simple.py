"""First half of the 50-question coding-agent benchmark (25 SIMPLE questions: S1-S25).
S1-S8 are the original 16-question dev set (used to build the local heuristic).
S9-S25 are the 17 held-out SIMPLE test questions across 4 coding-agent buckets.
"""

import re


def norm(s):
    return re.sub(r"[^a-z0-9.]+", " ", s.lower()).strip()


def contains_any(answer, options):
    a = norm(answer)
    return any(norm(o) in a for o in options)


def first_number(s):
    m = re.search(r"-?\d+(\.\d+)?", s)
    return m.group(0) if m else None


def all_numbers(s):
    return re.findall(r"-?\d+(?:\.\d+)?", s)


def letters_only(s):
    return re.sub(r"[^A-Za-z]", "", s).upper()


SIMPLE_QUESTIONS = [
    # --- DEV SET (S1-S8): original 8 simple questions -----------------------
    {
        "id": "S1",
        "split": "dev",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this code contain a SQL injection vulnerability? "
            "Answer only YES or NO.\n\n"
            'Code: query = "SELECT * FROM users WHERE id = " + user_id'
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S2",
        "split": "dev",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "Extract the HTTP status code from this log line. "
            "Reply with only the number.\n\n"
            "Log: '2026-09-23 10:14:02 GET /api/v2/users 200 14ms'"
        ),
        "check": lambda a: first_number(a) == "200",
    },
    {
        "id": "S3",
        "split": "dev",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Is this a valid JSON object? Answer only YES or NO.\n\n"
            '{"name": "test", "value": 1,}'
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S4",
        "split": "dev",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "What is the time complexity of binary search? "
            "Reply with only the Big-O notation."
        ),
        "check": lambda a: "log" in norm(a),
    },
    {
        "id": "S5",
        "split": "dev",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "Classify this git commit message as 'fix', 'feat', or 'chore'. "
            "Reply with one word.\n\n"
            "Commit: 'bump lodash from 4.17.20 to 4.17.21'"
        ),
        "check": lambda a: contains_any(a, ["chore"]),
    },
    {
        "id": "S6",
        "split": "dev",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this regex match the string 'abc123'? Answer only YES or NO.\n\n"
            "Regex: ^[a-z]+\\d+$"
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S7",
        "split": "dev",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "What HTTP method should a REST endpoint use to delete a resource? "
            "Reply with one word."
        ),
        "check": lambda a: contains_any(a, ["delete"]),
    },
    {
        "id": "S8",
        "split": "dev",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "Is this Python function missing a return statement for one of its "
            "logical branches (i.e. the zero case)? Answer only YES or NO.\n\n"
            "def sign(x):\n"
            "    if x > 0:\n"
            "        return 'positive'\n"
            "    elif x < 0:\n"
            "        return 'negative'"
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    # --- HELD-OUT TEST SET (S9-S25): 17 realistic simple agent tasks --------
    {
        "id": "S9",
        "split": "test",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "Extract the container port number from this Kubernetes deployment "
            "snippet where the service name is 'payments-api' and the image tag "
            "is 'stable-2026-09'. Reply with only the integer.\n\n"
            "containers:\n"
            "  - name: payments-api\n"
            "    image: gcr.io/prod/payments:stable-2026-09\n"
            "    ports:\n"
            "      - containerPort: 8443\n"
            "        protocol: TCP"
        ),
        "check": lambda a: first_number(a) == "8443",
    },
    {
        "id": "S10",
        "split": "test",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "From this structured application log entry emitted by the checkout "
            "worker during a database connection check, extract the value of the "
            "`retry_count` field. Reply with only the integer.\n\n"
            '{"ts":"2026-09-29T18:02:11Z","service":"checkout-worker","level":"WARN",'
            '"msg":"db pool slow","retry_count":4,"region":"us-east1"}'
        ),
        "check": lambda a: first_number(a) == "4",
    },
    {
        "id": "S11",
        "split": "test",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "Which file path is modified in this unified git diff header from a "
            "pull request updating the authentication middleware timeout? Reply "
            "with only the relative path.\n\n"
            "diff --git a/src/middleware/auth_guard.py b/src/middleware/auth_guard.py\n"
            "index 8f21a09..c491d02 100644\n"
            "--- a/src/middleware/auth_guard.py\n"
            "+++ b/src/middleware/auth_guard.py"
        ),
        "check": lambda a: "src/middleware/auth_guard.py" in a.strip(),
    },
    {
        "id": "S12",
        "split": "test",
        "bucket": "lookup_extract",
        "true_label": "SIMPLE",
        "prompt": (
            "In this Python traceback from a failed unit test run in CI, on which "
            "line number of `parser.py` was the exception raised? Reply with only "
            "the integer.\n\n"
            "Traceback (most recent call last):\n"
            '  File "tests/test_cli.py", line 42, in test_empty_flag\n'
            '  File "src/cli/parser.py", line 118, in parse_tokens\n'
            "    raise ValueError('unexpected EOF')"
        ),
        "check": lambda a: first_number(a) == "118",
    },
    {
        "id": "S13",
        "split": "test",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Is `2.4.1-rc.2` a valid Semantic Versioning 2.0.0 version string "
            "according to the standard `MAJOR.MINOR.PATCH-prerelease` grammar "
            "used by npm and Cargo packages? Answer only YES or NO."
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S14",
        "split": "test",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this OpenAPI parameter object include the required `in` field "
            "specifying where the parameter is located (such as `query`, `header`, "
            "`path`, or `cookie`)? Answer only YES or NO.\n\n"
            '{"name": "limit", "schema": {"type": "integer"}, "required": false}'
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S15",
        "split": "test",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Is `192.168.1.256` a valid IPv4 address where every dotted decimal "
            "octet lies between 0 and 255 inclusive? Answer only YES or NO."
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S16",
        "split": "test",
        "bucket": "schema_format",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this standard 5-field POSIX cron schedule expression contain "
            "the required 5 space-separated fields (`minute hour day-of-month "
            "month day-of-week`)? Answer only YES or NO.\n\n"
            "Cron: `0 6 * *`"
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S17",
        "split": "test",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "An agent needs to search the contents of files inside a local directory "
            "for lines matching a regular expression pattern. Which tool from this "
            "list should it pick: `read_file`, `grep_search`, or `delete_file`? "
            "Reply with only the tool name."
        ),
        "check": lambda a: "grep" in norm(a),
    },
    {
        "id": "S18",
        "split": "test",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "Classify HTTP status code `429 Too Many Requests` returned by an upstream "
            "REST endpoint into one of these categories: `client_rate_limit`, "
            "`server_crash`, or `success`. Reply with only the category name."
        ),
        "check": lambda a: "rate" in norm(a) or "client" in norm(a),
    },
    {
        "id": "S19",
        "split": "test",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this JavaScript snippet contain a DOM XSS vulnerability when "
            "`location.hash` is user-controlled? Answer only YES or NO.\n\n"
            'document.getElementById("msg").innerHTML = decodeURIComponent(location.hash.slice(1));'
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S20",
        "split": "test",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "A user changes a function's public parameter list in a library by "
            "removing a required argument, breaking existing callers. Under "
            "Semantic Versioning (`MAJOR`, `MINOR`, `PATCH`), which version "
            "component must be incremented? Reply with one word."
        ),
        "check": lambda a: contains_any(a, ["major"]),
    },
    {
        "id": "S21",
        "split": "test",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "Classify this SQL statement as `DDL`, `DML`, or `DCL`. Reply with "
            "only the three-letter acronym.\n\n"
            "SQL: `ALTER TABLE accounts ADD COLUMN last_login TIMESTAMP;`"
        ),
        "check": lambda a: contains_any(a, ["ddl"]),
    },
    {
        "id": "S22",
        "split": "test",
        "bucket": "classification",
        "true_label": "SIMPLE",
        "prompt": (
            "Is the `GET` HTTP method defined as idempotent by the HTTP/1.1 "
            "specification (RFC 9110)? Answer only YES or NO."
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S23",
        "split": "test",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this Python snippet raise a `ZeroDivisionError` when called with "
            "`avg([])` on an empty list? Answer only YES or NO.\n\n"
            "def avg(nums):\n"
            "    return sum(nums) / len(nums)"
        ),
        "check": lambda a: contains_any(a, ["yes"]) and not contains_any(a, ["no"]),
    },
    {
        "id": "S24",
        "split": "test",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "In this TypeScript function, is `user.profile.email` guarded against "
            "`user.profile` being `null` or `undefined` before property access? "
            "Answer only YES or NO.\n\n"
            "function getEmail(user: { profile?: { email: string } | null }) {\n"
            "  return user.profile.email.toLowerCase();\n"
            "}"
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
    {
        "id": "S25",
        "split": "test",
        "bucket": "single_hop_code",
        "true_label": "SIMPLE",
        "prompt": (
            "Does this shell script snippet safely quote the variable `$filepath` "
            "to prevent word-splitting when the file path contains spaces? "
            "Answer only YES or NO.\n\n"
            "rm $filepath"
        ),
        "check": lambda a: contains_any(a, ["no"]) and not contains_any(a, ["yes"]),
    },
]

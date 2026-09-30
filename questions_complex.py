"""Second half of the 50-question coding-agent benchmark (25 COMPLEX questions: C1-C25).
C1-C8 are the original 16-question dev set (used to build the local heuristic).
C9-C25 are the 17 held-out COMPLEX test questions across 3 coding-agent buckets:
  - simulation_trace
  - math_logic_chain
  - subtle_bug_edge
"""

from questions_simple import all_numbers, contains_any, first_number, letters_only, norm

COMPLEX_QUESTIONS = [
    # --- DEV SET (C1-C8): original 8 complex questions ----------------------
    {
        "id": "C1",
        "split": "dev",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "A cache has capacity 3 and uses LRU eviction, starting empty. "
            "Process this sequence of accesses in order: A, B, C, A, D. "
            "Give the final state of the cache ordered from most-recently "
            "used to least-recently used. Reply with only the letters, "
            "comma separated."
        ),
        "check": lambda a: letters_only(a) == "DAC",
    },
    {
        "id": "C2",
        "split": "dev",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "You have 8 identical-looking balls, one of which is heavier "
            "than the rest. Using a balance scale, what is the minimum "
            "number of weighings needed to guarantee finding the heavier "
            "ball? Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "2",
    },
    {
        "id": "C3",
        "split": "dev",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "A train leaves City A at 60 mph heading toward City B, 300 "
            "miles away. At the same time, a train leaves City B heading "
            "toward City A at 40 mph. How many hours until they meet? "
            "Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "3",
    },
    {
        "id": "C4",
        "split": "dev",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "A recursive factorial function in Python has no base case "
            "guard for negative inputs, and calls itself with n-1 each "
            "time. If called with factorial(-5), what happens? Reply with "
            "only one of: 'infinite loop', 'stack overflow / RecursionError', "
            "or 'returns 1'."
        ),
        "check": lambda a: contains_any(
            a, ["recursionerror", "stack overflow", "recursion error"]
        ),
    },
    {
        "id": "C5",
        "split": "dev",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "What is the time complexity of this code, in Big-O notation? "
            "Reply with only the Big-O notation.\n\n"
            "for i in range(n):\n"
            "    for j in range(i, n):\n"
            "        do_something()"
        ),
        "check": lambda a: (
            "n^2" in norm(a) or "n2" in norm(a).replace(" ", "") or "o(n^2)" in norm(a)
        ),
    },
    {
        "id": "C6",
        "split": "dev",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "Two threads increment a shared counter (not atomic) 1000 "
            "times each, with no lock. What is the most likely outcome for "
            "the final counter value? Reply with only one of: 'exactly "
            "2000', 'less than or equal to 2000, possibly less due to a "
            "race condition', or 'always greater than 2000'."
        ),
        "check": lambda a: contains_any(a, ["race", "less than"]),
    },
    {
        "id": "C7",
        "split": "dev",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "What is 17 raised to the power 3, modulo 5? Reply with only the number."
        ),
        "check": lambda a: first_number(a) == "3",
    },
    {
        "id": "C8",
        "split": "dev",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "You need to find the shortest path between two nodes in a "
            "weighted graph with all non-negative edge weights, and the "
            "graph has up to 1 million nodes. Which algorithm is the "
            "standard best choice? Reply with only one of: 'Dijkstra with "
            "a min-heap', 'Bellman-Ford', or 'Depth-First Search'."
        ),
        "check": lambda a: contains_any(a, ["dijkstra"]),
    },
    # --- HELD-OUT TEST SET (C9-C25): 17 realistic complex agent tasks -------
    {
        "id": "C9",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "A cache has capacity 3 and uses LFU (Least Frequently Used) eviction "
            "with LRU tie-breaking among items with equal frequency. It starts empty. "
            "Each get or put increments that key's frequency by 1 (a new key starts "
            "at frequency 1). Process these accesses in order: put(A), put(B), "
            "put(C), get(A), get(B), put(D), get(D), put(E). Which three keys remain "
            "in the cache at the end? Reply with only the three letters in "
            "alphabetical order, comma-separated."
        ),
        "check": lambda a: sorted(list(letters_only(a))) == ["B", "D", "E"],
    },
    {
        "id": "C10",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "A repo has commits A -> B -> C on main, where A sets x=1, B changes "
            "x=1 to x=2, and C changes x=2 to x=3 (in the same line of file.py). "
            "If you check out a new branch at A and run `git cherry-pick C`, what "
            "happens? Reply with only one of: 'clean apply with x=3', "
            "'merge conflict', or 'no-op'."
        ),
        "check": lambda a: contains_any(a, ["merge conflict", "conflict"]),
    },
    {
        "id": "C11",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "In what exact order are the numbers printed by this JavaScript snippet? "
            "Reply with only the seven comma-separated numbers.\n\n"
            "console.log(1);\n"
            "setTimeout(() => console.log(2), 0);\n"
            "Promise.resolve().then(() => {\n"
            "  console.log(3);\n"
            "  Promise.resolve().then(() => console.log(4));\n"
            "}).then(() => console.log(5));\n"
            "Promise.resolve().then(() => console.log(6));\n"
            "console.log(7);"
        ),
        "check": lambda a: all_numbers(a)[:7] == ["1", "7", "3", "6", "4", "5", "2"],
    },
    {
        "id": "C12",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "A binary search tree is built by inserting these keys in exact order "
            "into an initially empty BST (no rebalancing): 50, 30, 70, 20, 40, 60, "
            "80, 35, 65. What is the post-order traversal of the resulting tree? "
            "Reply with only the nine comma-separated integers."
        ),
        "check": lambda a: (
            all_numbers(a)[:9] == ["20", "35", "40", "30", "65", "60", "80", "70", "50"]
        ),
    },
    {
        "id": "C13",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "Branch `main` has commits A -> B -> C. Branch `topic` branched off B: "
            "B -> D -> E. Branch `sub` branched off D: D -> F -> G. You run "
            "`git rebase --onto main D sub`. Which commits (excluding A, B, C) "
            "are now on `sub` on top of C? Reply with only the commit letters "
            "separated by commas."
        ),
        "check": lambda a: letters_only(a) == "FG",
    },
    {
        "id": "C14",
        "split": "test",
        "bucket": "simulation_trace",
        "true_label": "COMPLEX",
        "prompt": (
            "Five microservices (M1, M2, M3, M4, M5) make synchronous calls while "
            "holding a local lock: M1 calls M3 and M4. M2 calls M5. M3 calls M2 "
            "and M5. M4 calls M2. M5 calls M1. How many distinct directed "
            "elementary cycles exist in this dependency graph? Reply with only "
            "the integer."
        ),
        "check": lambda a: first_number(a) == "3",
    },
    {
        "id": "C15",
        "split": "test",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "On a 4x4 grid of cells from (0,0) top-left to (3,3) bottom-right, "
            "you can only move right (+1 col) or down (+1 row). Cells (1,1) and "
            "(2,2) are blocked and cannot be entered. How many valid paths exist "
            "from (0,0) to (3,3)? Reply with only the integer."
        ),
        "check": lambda a: first_number(a) == "4",
    },
    {
        "id": "C16",
        "split": "test",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "Given `x = 0b101101` (45) and `y = 0b011011` (27), compute "
            "`((x ^ y) & (x | y)) ^ (x & y)`. Express the final result as a "
            "base-10 integer. Reply with only the integer."
        ),
        "check": lambda a: first_number(a) == "63",
    },
    {
        "id": "C17",
        "split": "test",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "What are the last two digits (i.e. value in base 10 mod 100) of "
            "7^2026? Reply with only the two-digit integer."
        ),
        "check": lambda a: first_number(a) == "49",
    },
    {
        "id": "C18",
        "split": "test",
        "bucket": "math_logic_chain",
        "true_label": "COMPLEX",
        "prompt": (
            "Table A has rows (id=1), (id=2), (id=3). Table B has rows "
            "(id=1, flag=0), (id=2, flag=1). Consider two SQL queries:\n"
            "Q1: SELECT COUNT(*) FROM A LEFT JOIN B ON A.id = B.id AND B.flag = 1;\n"
            "Q2: SELECT COUNT(*) FROM A LEFT JOIN B ON A.id = B.id WHERE B.flag = 1;\n"
            "What do Q1 and Q2 return? Reply with only the two integers separated "
            "by a comma."
        ),
        "check": lambda a: all_numbers(a)[:2] == ["3", "1"],
    },
    {
        "id": "C19",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "What does this Python 3 code print? Reply with only the four "
            "comma-separated integers.\n\n"
            "funcs = [lambda x: x + i for i in range(4)]\n"
            'print(",".join(str(f(10)) for f in funcs))'
        ),
        "check": lambda a: all_numbers(a)[:4] == ["13", "13", "13", "13"],
    },
    {
        "id": "C20",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "What does this Python snippet print on the THIRD call? Reply with "
            "only the two integers inside brackets.\n\n"
            "def append_item(val, seq=[]):\n"
            "    seq.append(val)\n"
            "    if len(seq) > 2:\n"
            "        seq.pop(0)\n"
            "    return seq\n\n"
            "append_item(1)\n"
            "append_item(2)\n"
            "print(append_item(3))"
        ),
        "check": lambda a: all_numbers(a)[:2] == ["2", "3"],
    },
    {
        "id": "C21",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "Given these Python classes:\n"
            "class A:\n"
            '    def f(self): return "A"\n'
            "class B(A):\n"
            '    def f(self): return super().f() + "B"\n'
            "class C(A):\n"
            '    def f(self): return super().f() + "C"\n'
            "class D(B, C):\n"
            '    def f(self): return super().f() + "D"\n'
            "What does `D().f()` return? Reply with only the four-letter string."
        ),
        "check": lambda a: "ACBD" in letters_only(a),
    },
    {
        "id": "C22",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "What does this Python 3 snippet print? Reply with only the integer.\n\n"
            "g = (x * 2 for x in range(5))\n"
            "a = sum(x for x in g if x < 6)\n"
            "b = sum(g)\n"
            "print(a + b)"
        ),
        "check": lambda a: first_number(a) == "6",
    },
    {
        "id": "C23",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "In Python 3, after running:\n"
            'd = {1: "a", True: "b", 1.0: "c"}\n'
            "print(len(d), list(d.keys())[0], list(d.values())[0])\n"
            "What is printed? Reply with only the three space-separated values."
        ),
        "check": lambda a: norm(a).replace(" ", "") == "11c",
    },
    {
        "id": "C24",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "What does this Python function return when called as `f()`? "
            "Reply with only the integer.\n\n"
            "def f():\n"
            "    x = 10\n"
            "    try:\n"
            "        x += 5\n"
            "        return x\n"
            "    finally:\n"
            "        x += 20"
        ),
        "check": lambda a: first_number(a) == "15",
    },
    {
        "id": "C25",
        "split": "test",
        "bucket": "subtle_bug_edge",
        "true_label": "COMPLEX",
        "prompt": (
            "In C, given `int a = 1, b = 1, c = 1; int r = (a++ && b--) || ++c;`, "
            "what are the final values of `a, b, c, r`? Reply with only the four "
            "comma-separated integers."
        ),
        "check": lambda a: all_numbers(a)[:4] == ["2", "0", "1", "1"],
    },
]

QUESTIONS = None

# Make the cutest picture — make.fun bounty entry

A deterministic, standard-library-only Python program that draws one cute
picture — a chubby kitten with big glossy eyes, pink blush, a tiny bow,
whiskers and a curled tail — and writes it to `/output/entry.png`.

## How it works

- `main.py` is the whole entry. It uses only `math`, `os`, `struct` and
  `zlib` (all Python standard library).
- The picture is drawn procedurally: a small rasterizer (circles,
  ellipses, polygons, thick lines, tubes) renders at 2x supersampling,
  then box-downsamples to 1024×1024 for smooth edges.
- The PNG encoder is written by hand on top of `zlib` — no Pillow, no
  third-party code, no network, no randomness.
- Two runs produce byte-identical output (verified).

## Run it

```sh
python3 main.py        # writes output/entry.png (or /output/entry.png
                       # when that directory exists, as in the grader)
```

Output: 1024×1024 PNG, ~23 KB (limit: 1 MiB, 1024×1024).

## Bounty

[Make the cutest picture](https://make.fun/bounty/cutest-picture-01) —
$250 total, 20 places (1st $50). Deadline: Fri 13 Nov 2026, 17:00 WIB.

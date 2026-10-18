# Local v1.0.0 publication preparation

Steps 1–15 are approved and closed. Publication packaging does not introduce a new engineering phase or change simulator behavior. This branch retains the remote README history and packages the approved implementation, locked research and curated evidence in three reviewable commits. Nothing has been pushed, merged or tagged by this preparation.

## Exact-byte contract

The root `.gitattributes` deliberately uses `* -text`: Git must store and check out the approved bytes without line-ending conversion, including with Windows `core.autocrlf=true`. Ordinary textual diffs remain available. The whitespace attribute recognizes preserved CRLF endings while retaining trailing-blank, blank-at-EOF and space-before-tab checks. This is intentional because source, raw-output and fixture checksums cover bytes. Locked Matplotlib SVG files retain generator-produced trailing spaces and have a narrow `research/figures/*.svg -whitespace` exception; their exact hashes remain mandatory. They are not reformatted to silence a diff check. Do not normalize locked files, regenerate goldens, or change source manifests to hide a mismatch.

All simulator/UI code, existing tests, goldens, validation workflows, benchmark entry points and pinned dependencies are copied from the approved snapshot. All research protocols, manifests, raw runs, checksums, CSVs, processed results and figures are copied unchanged. Publication-only changes are attributes/ignore policy, documentation links/status, curated evidence and provenance.

## Included and excluded tooling

Supported research commands use `experiments/run_step15.py`, the two research test modules and `research/analysis/analyze.py`. Historical report-generation, closure-verification and local orchestration helpers require private baselines/evidence and are archived privately rather than exposed as portable tools. The original reports remain available as public copies with corrected evidence links.

The six research-tooling tests are separate from the 336 collected simulator tests. FAST and STANDARD exclude the HEAVY gameplay smoke. Hosted GitHub Actions and cross-platform results must not be described as passed until they actually run. Existing historical test counts retain their original meanings.

## Publication boundary

The raw research results are immutable; reproduction should use a new output directory. Public evidence copies with sanitized paths are labeled in [the provenance manifest](evidence/provenance.json). Private archives, credentials, `.git` internals and internal checkpoint refs are not release assets. Push, PR, merge and tag operations require separate approval.

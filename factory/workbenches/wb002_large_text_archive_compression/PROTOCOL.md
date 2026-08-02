# WB-002 verification protocol v0.1

## Authority boundary

The Factory may classify a package as locally measured or reproduced. Only the
Hutter Prize committee can declare an official record or prize result.

## Official-compatible scope

The fixed public input is the extracted 1,000,000,000-byte `enwik9` corpus.
Before measurement, verify its published MD5 and SHA-1, then record a
factory-derived SHA-256. A claim fails closed unless all of these gates pass:

1. exact byte-for-byte restoration;
2. deterministic package accounting;
3. one permitted official packaging formula, with every required program,
   archive and option-string byte counted;
4. no undeclared file, dictionary, installation, network access or GPU;
5. each required executable independently satisfies the official time, RAM and
   temporary-disk rules;
6. counted size is below the frozen, dated official comparator;
7. artifact, source, toolchain, environment and commands are locked;
8. two different human-owned validators commit independent measurements before
   either sees the author's claimed score.

The corpus is deliberately public. Blindness applies to the claimed score and
validator conclusions, not to a fabricated hidden corpus.

## Packaging formulas

Primary self-extracting form:

`S = compressor package bytes + self-extracting archive bytes + required option bytes`

Separate compressor/decompressor form:

`S = compressor package bytes + 2 × decompressor package bytes + archive bytes + required option bytes`

When compressor and decompressor are the identical program, the official rules
may reduce the decompressor multiplier from two to one. The local entry runner
supports only this shared-program form and labels its score entry-only; it does
not claim official compatibility.

## Practical-utility scope

Official Hutter score and deployment value are separate outputs. The practical
scenario counts encoding, retained storage, retrieval/decode, egress, decoder
distribution and operations. A smaller Hutter package may legitimately fail
this economic gate and must not be advertised as a general deployment win.

## Disagreement

A failed rerun does not establish who is wrong. Preserve both packages and find
the first divergence in corpus identity, source/build, command, package
accounting, restoration, resource measurement or environment. A third run is
diagnostic only; deterministic disagreement requires human review and cannot be
majority-voted into promotion.

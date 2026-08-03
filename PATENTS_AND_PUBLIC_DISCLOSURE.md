# Patents and public disclosure

Status: **draft operating boundary, not patent advice**.

The Factory can preserve evidence and provenance. It cannot decide that an
invention is patentable, identify every inventor, guarantee ownership, or give
freedom-to-operate clearance.

## Stop before uploading patent-sensitive material

Publishing an invention before filing can destroy patent options in some
jurisdictions. If a contributor may want a patent, they must stop before opening
an issue, pull request, discussion, artifact upload or public evaluator run and
obtain appropriate professional advice. The current Factory has no confidential
or embargoed patent-intake service.

After any necessary filing, only a deliberately public, non-confidential
package may enter the repository. A `FILED_BEFORE_PUBLICATION` declaration is
the contributor's statement, not verification by the Factory.

UK IPO starting guidance:

- [Before applying for a patent](https://www.gov.uk/patent-your-invention/before-you-apply)
- [Right to apply for and obtain a patent](https://www.gov.uk/guidance/the-patent-act-1977/section-7-right-to-apply-for-and-obtain-a-patent)
- [Licensing intellectual property](https://www.gov.uk/guidance/licensing-intellectual-property)

## Patent-intent values

Every substantive submission uses one of these machine-readable values:

- `NONE` - no patent position is asserted by the submission;
- `OPEN_COMMONS` - the contributor intends the disclosed implementation to be
  available under the applicable open licence; or
- `FILED_BEFORE_PUBLICATION` - the contributor declares that relevant filing
  occurred before this public package was submitted.

These values do not prove validity, scope, ownership, inventorship or licence.
If the correct value is unknown, do not submit yet.

## Four checks for a derived invention

Before seeking a patent or commercial licence for work that builds on Factory
records, the applicant should document four independent checks:

1. **provenance and permission:** what earlier material was used and what do its
   licences permit;
2. **inventorship and entitlement:** which humans devised the claimed invention
   and whether employment, collaboration or assignment affects entitlement;
3. **novelty and patentability:** whether the proposed claims meet the law in
   the relevant jurisdiction; and
4. **freedom to operate:** whether making or selling the implementation may
   infringe rights held by other people.

Passing one check does not pass the others. In particular, permission to use
copyrighted code is not a finding of inventorship or freedom to operate.

## Joint work

A contributor must not claim sole invention merely because they submitted the
last patch or assembled the final proof package. The provenance ledger should
identify the material intellectual contribution of every person. Where joint
inventorship or entitlement may exist, publication, a patent application and a
commercial deal should wait until the interests are declared and any necessary
agreement, permission or professional advice is obtained.

The Factory, its repository owner and its maintainers claim no automatic share
of a patent. Validators also gain no automatic patent interest merely by
reproducing a result. Actual inventorship is a legal and factual question.

## Progress-Friendly Patent Pledge

Patent holders are invited, never required, to make a separate signed public
pledge offering progress-friendly terms. The submission field
`progress_friendly_patent_pledge` records only an expressed intention; it is not
itself a patent licence.

The suggested negotiating principles are:

- prefer non-exclusive licensing where practical;
- avoid a large up-front access toll as the default;
- prefer clearly defined per-unit, sales or revenue-based payments over profit
  or ROI formulas that are difficult to audit;
- use milestones, caps, floors or cost recovery where they genuinely enable
  development;
- preserve research, validation and reasonable humanitarian access where
  appropriate;
- publish the covered patent numbers, fields, territories, duration and
  termination terms; and
- negotiate with every relevant rightsholder rather than assuming the last
  contributor can license everybody's work.

No single royalty rate is imposed. Different technologies have different
capital, regulatory, manufacturing and market risks, and competition law still
applies. A patent holder who does not adopt the pledge remains eligible for the
same scientific process.

## What the Factory records

The structured declaration records:

- `patent_intent`;
- `rights_review_declared`;
- `joint_inventors_identified`;
- `institutional_interests_declared`;
- `third_party_rights_declared`;
- `material_ai_use_declared`;
- `progress_friendly_patent_pledge`; and
- `freedom_to_operate`.

`freedom_to_operate: NOT_ASSESSED` is an honest allowed value. The Factory will
never emit a `CLEARED` value because it has not performed a jurisdiction- and
claim-specific legal analysis.

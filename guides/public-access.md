# Public access and private evidence

The toolkit source, generic technical lessons and EngineeringTestSupport package are MIT
licensed and publicly readable. Python 3.9+ and Git suffice for its core tests and guidance.
Xcode is needed for Apple build and simulator lanes. Production libraries named in the
knowledge articles are separate private projects; none is a dependency of this toolkit.

## Contributor setup

Clone this repository beside the consumer with
`git clone https://github.com/vocaro/vocaro-engineering.git`. In the consumer, run
`python3 scripts/eng doctor`, `python3 scripts/eng instructions` and its documented lanes.
Set VOCARO_ENGINEERING_ROOT for a different checkout location. See
[adoption](adoption.md) for new projects and updates.

A public GitHub Actions workflow can use actions/checkout with repository:
vocaro/vocaro-engineering and persist-credentials: false. No custom SSH key or private-repository
secret is needed. Dispatching a workflow still requires permission on the consumer repository.
Fork owners set their own repository and hostedRepositories values in engineering.json before
dispatching their workflows; read-only local regression tests dispatch nothing.

## Account-specific queue enrollment

Public consumer configuration lists public repositories only. On a shared account that also
uses private hosted runners, enroll each additional repository locally with
`git config --local --add vocaroEngineering.hostedRepository OWNER/PRIVATE_REPO` from the
consumer checkout. The dispatcher adds these repositories to the committed list and checks
all of them. A configured repository whose queue cannot be read remains an error; it is never
silently ignored. Local enrollment does not grant repository access or spending permission.

## Evidence and provenance

Raw transcripts, private integration records, personal device identities and private payloads
stay in their private owning project or apple-engineering-evidence. Public subject articles
explain reusable methods and their measured limits. Links to private source records are
supplemental provenance and are labeled by the owning repository; readers do not need those
repositories to run the public tools. Preserve source and input identities when reproducing a
finding, and do not substitute a local regression for platform acceptance.

The original cross-project implementation record and display-state investigation retain their
complete bodies and comments in the private evidence repository. They are not redistributed
under this toolkit's MIT license. The original projects and the three production Swift
libraries retain their own visibility and licenses.

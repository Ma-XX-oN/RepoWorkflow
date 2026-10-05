# First-Use Workflow Ticket Audit

Status: repository-wide audit required by #303.

This audit covers **all 184 GitHub issues** present when regenerated
through GitHub issue search (pull requests excluded).  It classifies workflow
ownership, not whether a component merely has unit tests.

A supported public workflow is not proven because lower-level stores, adapters,
algorithms, or orchestration helpers are GREEN.  Its first-use scenario starts
from the minimum state promised to the caller and enters through the real
public boundary.

## Scenario status

| Scenario | Status | Owner / repair |
| --- | --- | --- |
| FU-BOOTSTRAP-HELP | covered | #299 / tests/test_bootstrap_cli.py |
| FU-ISSUE-READ | covered | #298-#301; follow-up #312 |
| FU-INIT | pending | #27 |
| FU-DEPS-LANES | gap | #305 |
| FU-SESSION | gap | #306 |
| FU-PUBLIC-ERRORS | gap | #307 |
| FU-WORK | gap | #308 |
| FU-LIFECYCLE | gap | #309 |
| FU-CONSUMER | gap | #313 |

"Gap" means component coverage exists but an assembled first-use test does not
yet prove the documented path.  "Pending" means the public feature itself is
not complete and its first-use test is part of completion.

## Ticket-by-ticket classification

| Ticket | State | Classification | Family | First-use disposition |
| ---: | --- | --- | --- | --- |
| #1 | closed | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #2 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #5 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #7 | closed | public first-use contributor | initialization | FU-INIT pending #27; consumer path #313 |
| #8 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #11 | closed | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #14 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #15 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #16 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #17 | open | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #18 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #19 | open | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #27 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #28 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #29 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #30 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #51 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #52 | closed | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #53 | open | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #54 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #55 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #56 | open | public first-use owner | issue-start/session | FU-WORK gap #308; identity #306 |
| #57 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #58 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #63 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #64 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #65 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #66 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #67 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #68 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #69 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #70 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #71 | open | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #72 | open | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #73 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #74 | open | public first-use contributor | initialization | FU-INIT pending #27; consumer path #313 |
| #75 | open | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #76 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #77 | closed | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #78 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #79 | closed | public first-use contributor | issue-start/session | FU-WORK gap #308; identity #306 |
| #80 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #81 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #82 | open | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #83 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #84 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #85 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #86 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #87 | open | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #88 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #89 | closed | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #90 | open | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #91 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #92 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #93 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #94 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #95 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #96 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #97 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #98 | open | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #99 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #100 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #101 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #102 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #103 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #104 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #105 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #106 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #107 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #108 | open | public first-use contributor | issue-start/session | FU-WORK gap #308; identity #306 |
| #109 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #110 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #111 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #112 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #113 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #114 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #115 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #116 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #117 | closed | public first-use contributor | issue-start/session | FU-WORK gap #308; identity #306 |
| #118 | closed | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #119 | open | public first-use owner | internal/core | internal-only; covered through public consumer + focused tests |
| #120 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #121 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #122 | open | public first-use contributor | issue-start/session | FU-WORK gap #308; identity #306 |
| #123 | open | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #124 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #125 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #127 | closed | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #129 | closed | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #131 | closed | public first-use contributor | internal/core | internal-only; covered through public consumer + focused tests |
| #133 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #135 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #136 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #137 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #138 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #139 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #140 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #141 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #142 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #143 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #144 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #145 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #153 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #155 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #159 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #163 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #164 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #169 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #172 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #185 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #186 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #187 | closed | public first-use owner | workspace | FU-WORK gap #308; identity #306 |
| #189 | closed | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #196 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #201 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #205 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #206 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #208 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #209 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #210 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #211 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #212 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #213 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #214 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #215 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #216 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #217 | closed | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #218 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #219 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #220 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #221 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #222 | open | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #223 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #224 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #225 | open | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #227 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #228 | closed | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #229 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #230 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #231 | open | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #232 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #233 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #234 | open | public first-use contributor | workspace | FU-WORK gap #308; identity #306 |
| #235 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #236 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #240 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #242 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #246 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #249 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #250 | closed | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #252 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #253 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #254 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #255 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #256 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #261 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #263 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #264 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #265 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #266 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #269 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #272 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #274 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #276 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #278 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #280 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #282 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #295 | closed | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #297 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #298 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #299 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #300 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #301 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #303 | open | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #304 | open | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #305 | open | public first-use owner | dependency-sync | FU-DEPS-LANES gap #305 |
| #306 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #307 | open | public first-use contributor | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #308 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #309 | open | public first-use owner | lanes | FU-DEPS-LANES gap #305; identity #306; diagnostics #307 |
| #310 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #311 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #312 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered; PR/type mismatch repair #312 |
| #313 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |

## Closure rule

For any ticket classified as a public first-use owner, closure requires either:

1. a covered scenario in `FIRST_USE_WORKFLOWS.json`; or
2. an explicit statement that the workflow is not yet supported, with an open
   implementation owner whose postconditions include the first-use scenario.

Contributors inherit the assembled scenario of their public owner but retain
focused unit/contract tests.  Internal-only tickets do not invent artificial
user workflows.  Experimental/obsolete/duplicate tickets are excluded from
supported behaviour.

The machine-readable registry is `FIRST_USE_WORKFLOWS.json`.

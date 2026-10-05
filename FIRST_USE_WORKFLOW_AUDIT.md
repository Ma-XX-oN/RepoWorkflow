# First-Use Workflow Ticket Audit

Status: repository-wide audit required by #303.

This audit covers **all 184 GitHub issues** present when regenerated
through GitHub issue search (pull requests excluded).  Tickets are classified by
their own title/scope first; cross-cutting historical umbrellas use explicit
family overrides where a keyword-only classification would be misleading.

A supported public workflow is not proven because lower-level stores, adapters,
algorithms, or orchestration helpers are GREEN.  Its first-use scenario starts
from the minimum state promised to the caller and enters through the real
public boundary.

## Scenario status

| Scenario | Status | Owner / repair |
| --- | --- | --- |
| FU-BOOTSTRAP-HELP | covered | #299 / tests/test_bootstrap_cli.py |
| FU-ISSUE-READ | covered | #298-#301 / #312 |
| FU-INIT | pending | #27 |
| FU-DEPS-LANES | covered | #305 / tests/test_first_use_lanes.py |
| FU-SESSION | covered | #306 / tests/test_first_use_lanes.py |
| FU-PUBLIC-ERRORS | covered | #307 / tests/test_bootstrap_cli.py |
| FU-WORK | gap | #308 |
| FU-LIFECYCLE | gap | #309 |
| FU-CONSUMER | gap | #313 |

"Gap" means component coverage exists but an assembled first-use test does not
yet prove the documented path.  "Pending" means the public feature itself is
not complete and its first-use test is part of completion.

## Ticket-by-ticket classification

| Ticket | State | Classification | Family | First-use disposition |
| ---: | --- | --- | --- | --- |
| #1 | closed | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #2 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #5 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #7 | closed | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #8 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #11 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #14 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #15 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #16 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #17 | open | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #18 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #19 | open | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #27 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #28 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #29 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #30 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #51 | open | public first-use contributor | public-workflow | covered only by its registered child scenarios; open children retain gaps |
| #52 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #53 | open | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #54 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #55 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #56 | open | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #57 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #58 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #63 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered |
| #64 | closed | public first-use owner | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #65 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #66 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #67 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #68 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #69 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #70 | open | public first-use contributor | ci-provider | FU-CONSUMER gap #313 |
| #71 | open | public first-use contributor | public-workflow | covered only by its registered child scenarios; open children retain gaps |
| #72 | open | public first-use contributor | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #73 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #74 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #75 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #76 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #77 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #78 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #79 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #80 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #81 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #82 | open | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #83 | open | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #84 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #85 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #86 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #87 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #88 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #89 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #90 | open | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #91 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #92 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #93 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #94 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #95 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #96 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #97 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |
| #98 | open | public first-use owner | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #99 | closed | public first-use contributor | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #100 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #101 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #102 | open | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #103 | open | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #104 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #105 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #106 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #107 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #108 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #109 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #110 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #111 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #112 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #113 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #114 | open | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #115 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #116 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #117 | closed | public first-use contributor | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #118 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #119 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #120 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #121 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #122 | open | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #123 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #124 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #125 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #127 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #129 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #131 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #133 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #135 | open | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #136 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #137 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #138 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #139 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #140 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #141 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #142 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #143 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #144 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #145 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #153 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #155 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #159 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #163 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #164 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #169 | closed | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #172 | closed | public first-use owner | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #185 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #186 | closed | public first-use owner | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #187 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #189 | closed | public first-use contributor | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #196 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #201 | closed | public first-use contributor | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #205 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #206 | closed | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #208 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #209 | closed | public first-use contributor | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #210 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #211 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #212 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #213 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #214 | closed | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #215 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #216 | closed | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #217 | closed | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #218 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #219 | closed | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #220 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #221 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #222 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #223 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #224 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #225 | open | public first-use contributor | integration-topology | pending until supported public integration/done path exists |
| #227 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #228 | closed | public first-use owner | integration-topology | pending until supported public integration/done path exists |
| #229 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered |
| #230 | open | public first-use owner | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #231 | open | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #232 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #233 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #234 | open | public first-use contributor | workspace | FU-WORK gap #308; runtime identity covered by #306 |
| #235 | open | public first-use owner | public-workflow | covered only by its registered child scenarios; open children retain gaps |
| #236 | closed | public first-use contributor | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #240 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #242 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #246 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #249 | open | public first-use owner | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
| #250 | closed | public first-use contributor | lanes | FU-DEPS-LANES covered by #305/#306; diagnostics covered by #307 |
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
| #280 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #282 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #295 | closed | public first-use owner | initialization | FU-INIT pending #27; consumer path #313 |
| #297 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #298 | closed | public first-use owner | public-workflow | covered only by its registered child scenarios; open children retain gaps |
| #299 | closed | internal-only | internal/core | internal-only; covered through public consumer + focused tests |
| #300 | closed | public first-use owner | issue-query | FU-ISSUE-READ covered |
| #301 | closed | public first-use contributor | issue-query | FU-ISSUE-READ covered |
| #303 | open | internal policy/audit | audit/meta | governed by #303/#304 registry and audit gate |
| #304 | open | internal policy/audit | audit/meta | governed by #303/#304 registry and audit gate |
| #305 | open | public first-use owner | dependency-sync | FU-DEPS-LANES covered by #305/#306 |
| #306 | open | public first-use contributor | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #307 | open | internal policy/audit | audit/meta | governed by #303/#304 registry and audit gate |
| #308 | open | public first-use owner | issue-start/session | FU-WORK gap #308; runtime identity covered by #306 |
| #309 | open | public first-use owner | lifecycle-validation | FU-LIFECYCLE gap #309 |
| #310 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #311 | closed | experimental/obsolete/duplicate | experimental/obsolete | exempt from supported first-use coverage |
| #312 | open | public first-use contributor | issue-query | FU-ISSUE-READ covered |
| #313 | open | public first-use owner | ci-provider | FU-CONSUMER gap #313 |

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

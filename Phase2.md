
# 8. PHASE 2 — USABLE BACKEND PLATFORM

## 8.1 Main Goal

Phase 2 transforms the core into a backend framework that feels productive for real application development.

Phase 1 proves the architecture.
Phase 2 makes it practical.

By the end of Phase 2, a user should be able to build a serious internal tool or SaaS backend with:

- auth
- permissions
- jobs
- cache
- better docs
- migrations support
- better developer ergonomics

## 8.2 Phase 2 Scope Summary

### Must Have
- auth foundation
- permissions model
- token/session contracts
- jobs runtime (local/single-node)
- cache abstraction
- migration integration/wrapper
- improved HTTP ergonomics
- OpenAPI / docs generation baseline
- better error rendering
- project templates/starter improvements
- richer CLI
- validation polish around msgspec integration
- pagination and filtering primitives
- module config improvements

### Nice to Have
- email abstraction
- settings diagnostics UI/CLI
- admin/internal panel groundwork
- code generation for common patterns
- better repository helpers

### Out of scope still
- distributed event bus
- full RPC transport
- multi-node worker coordination
- service mesh features
- plugin marketplace at scale

---

## 8.3 Phase 2 Detailed Components

### 8.3.1 Auth Foundation

#### Goal
Add a first-class authentication layer without overloading the framework with every auth style at once.

#### Phase 2 should include
- identity abstraction
- principal/current user contract
- auth backend interface
- bearer token support at minimum
- session support optional if still manageable
- dependency and middleware integration

#### Why Phase 2
Auth is essential for real apps, but too heavy for Phase 1 core.

#### Success criteria
- developers can protect handlers and access current principal cleanly

---

### 8.3.2 Permissions / Authorization

#### Goal
Add a predictable way to enforce access rules.

#### Needed features
- permission abstraction
- route/handler-level permission declaration
- current principal integration
- role/policy hooks

#### Design philosophy
Keep the core small.
Do not build a giant enterprise policy language in this phase.

#### Success criteria
- protected handlers can be implemented cleanly with clear failure modes

---

### 8.3.3 Jobs Runtime (Single-Node / Local)

#### Goal
Introduce asynchronous work execution without full distributed complexity yet.

#### Use cases
- send email
- recalculate stats
- deferred side effects
- retryable background work

#### Needed components
- `Job` contract
- job dispatcher
- local worker runtime
- retry model
- delay support
- failure state handling

#### Why this matters
A service framework needs more than HTTP request handling.

#### Success criteria
- jobs can be defined and executed outside HTTP flow

---

### 8.3.4 Cache Abstraction

#### Goal
Introduce a cache layer usable by services and handlers.

#### Features
- cache interface
- in-memory cache implementation
- Redis implementation later in this phase if realistic
- TTL support
- invalidation hooks

#### Design rule
Do not make cache mandatory for the framework.

#### Success criteria
- services can use cache without hard dependency on a concrete backend

---

### 8.3.5 Migration Integration / Wrapper

#### Goal
Provide a consistent migration experience without writing a migration engine from scratch.

#### Likely strategy
- wrap Alembic
- provide framework-aware config and CLI hooks

#### Needed features
- migration CLI integration
- environment wiring
- project template support

#### Success criteria
- developers can run migrations from framework CLI predictably

---

### 8.3.6 Improved HTTP Ergonomics

#### Goal
Make the HTTP adapter pleasant rather than merely functional.

#### Additions
- better route declaration API
- response helpers
- exception rendering polish
- validation error formatting improvements
- standardized pagination responses

#### Keep in mind
HTTP still remains a transport, not the center of the framework.

#### Success criteria
- HTTP usage feels smooth without distorting the architecture

---

### 8.3.7 OpenAPI / Docs Baseline

#### Goal
Provide reasonable API documentation generation.

#### Challenge
With msgspec-first architecture, docs generation will require custom translation work.

#### Needed features
- schema introspection path
- request/response mapping
- route documentation generation
- docs endpoint optional

#### Risks
- trying to implement too much OpenAPI sophistication too early

#### Success criteria
- API surface can be documented and explored by developers

---

### 8.3.8 Pagination / Filtering / List Primitives

#### Goal
Support the most common read-side patterns.

#### Needed pieces
- page/result types
- list query conventions
- filter object conventions
- sorting conventions

#### Success criteria
- list endpoints and list queries have a standard framework style

---

### 8.3.9 Richer CLI

#### Goal
Evolve CLI into a central developer tool.

#### Suggested commands
- create project
- create module
- runserver
- config inspect
- migrations commands
- jobs commands
- environment diagnostics

#### Success criteria
- CLI becomes the default entry point for framework operations

---

### 8.3.10 Better Project Templates and Starters

#### Goal
Reduce friction for new users and for your own future development.

#### Starter types
- API service starter
- internal tool starter
- worker-enabled starter later if ready

#### Success criteria
- a meaningful starter app can be generated quickly

---

### 8.3.11 Validation and Serialization Polish

#### Goal
Strengthen the msgspec-based schema integration.

#### Areas to improve
- custom validation hooks if needed
- better field error representation
- schema metadata support
- serialization control for HTTP/docs

#### Success criteria
- msgspec-first design feels mature enough for real-world use

---

### 8.3.12 Module-Level DX Improvements

#### Goal
Make modules easier to organize as projects grow.

#### Features
- module config support
- module import/export story
- module diagnostics
- improved testing helpers per module

#### Success criteria
- medium-sized projects remain organized and understandable

---

## 8.4 Phase 2 Exit Criteria

Phase 2 is complete when:

- a protected HTTP API can be built with auth and permissions
- jobs can run outside request flow
- migrations are manageable through framework tooling
- cache can be used through a stable abstraction
- docs/OpenAPI are usable
- project templates feel practical
- medium-sized applications feel productive rather than experimental

---
